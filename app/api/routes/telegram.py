from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
import re
import json
from app.adapters.notifiers.telegram import format_watchlist_message
from app.scanners.watchlist_builder import build_watchlist
from app.utils.normalize import (
    normalize_quotes_and_dashes,
    parse_kv_flags,
    parse_watchlist_args,
)

# Local DI factory (avoids circular dependency)
def TelegramDep():
    from app.adapters.notifiers.telegram import build_client_from_env
    return build_client_from_env()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])
ALLOW_NO_SECRET = os.getenv("TELEGRAM_ALLOW_TEST_NO_SECRET") == "1"

def _env():
    try:
        from app.utils import env as ENV  # type: ignore

        return ENV
    except Exception:

        class F:
            TELEGRAM_WEBHOOK_SECRET = ""
            TELEGRAM_BOT_TOKEN = ""

        return F()

SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,20}$")

def _mask(s: Optional[str]) -> str:
    if not s:
        return "<empty>"
    if len(s) <= 8:
        return "*" * (len(s) - 2) + s[-2:]
    return s[:2] + "*" * (len(s) - 6) + s[-4:]

def _dump_webhook_debug(where: str, *, payload: Dict[str, Any], hdr_primary: Optional[str], hdr_legacy: Optional[str],
                        env_secret: Optional[str], test_mode: bool, allow_empty: bool, env_name: str, bot_token_set: bool) -> None:
    try:
        logger.warning(
            "[tg-webhook:{where}] DEBUG\n"
            "  hdr_primary: {hdr_primary}\n"
            "  hdr_legacy : {hdr_legacy}\n"
            "  env_secret : {env_secret}\n"
            "  test_mode  : {test_mode}\n"
            "  allow_empty: {allow_empty}\n"
            "  ENV        : {env_name}\n"
            "  BOT_TOKEN? : {bot_token_set}\n"
            "  PAYLOAD    : {payload}",
            where=where,
            hdr_primary=_mask(hdr_primary),
            hdr_legacy=_mask(hdr_legacy),
            env_secret=_mask(env_secret),
            test_mode=test_mode,
            allow_empty=allow_empty,
            env_name=env_name,
            bot_token_set=bot_token_set,
            payload=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        )
    except Exception as e:
        logger.error("[tg-webhook:%s] debug dump failed: %s", where, e)

def _is_authorized(user_id: Optional[int]) -> bool:
    """Allow all if no allowlist configured; else enforce match."""
    try:
        ENV = _env()
        allow_list = getattr(ENV, "TELEGRAM_ALLOWED_USER_IDS", []) or []
    except Exception:
        allow_list = []
    if not allow_list:
        return True
    if user_id is None:
        return False
    s = str(user_id)
    return s in {str(u) for u in allow_list}

def _parse_command(text: str) -> tuple[str, list[str]]:
    t = (text or "").strip()
    if not t.startswith("/"):
        return "", []
    parts = t.split()
    cmd = parts[0].lower().split("@", 1)[0]
    return cmd, parts[1:]

def _reply(tg: Any, chat_id: int | str, text: str) -> None:
    # Prefer smart_send; fall back to send_message
    try:
        if hasattr(tg, "smart_send"):
            tg.smart_send(chat_id, text, parse_mode="Markdown", chunk_size=3500)
        elif hasattr(tg, "send_message"):
            tg.send_message(chat_id, text, parse_mode="Markdown")
    except TypeError as exc:
        logger.warning("Telegram reply TypeError: %s", exc)
        # Fallback for fakes that don't accept kwargs
        if hasattr(tg, "smart_send"):
            tg.smart_send(chat_id, text)
        elif hasattr(tg, "send_message"):
            tg.send_message(chat_id, text)

_WATCH_META: Dict[str, Any] = {"count": 0, "session": "regular", "asof_utc": None}

_WATCHLIST_SOURCES = {"manual", "textlist", "finviz"}


def _resolve_watchlist(source_override: str | None) -> tuple[str, list[str]]:
    from app.domain.watchlist_service import resolve_watchlist

    if not source_override:
        return resolve_watchlist()

    env_var = "WATCHLIST_SOURCE"
    previous = os.environ.get(env_var)
    try:
        os.environ[env_var] = source_override
        return resolve_watchlist()
    finally:
        if previous is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = previous


def _handle_watchlist(tg: Any, chat_id: int | str, args: list[str]) -> None:
    """Build and send a watchlist.
    Supports:
      - `/watchlist` (env/default source resolution)
      - `/watchlist <SYMS...>` (manual list, space/comma-separated)
      - Flags: --limit=15, --session=pre|regular|after, --filters=true|false, --title="Custom"
    """
    # Parse flags & symbols
    cleaned = normalize_quotes_and_dashes(" ".join(args or []))
    kv_flags = parse_kv_flags(cleaned)
    parsed = parse_watchlist_args(cleaned)

    # Options
    title = kv_flags.get("title") or parsed.get("title") or "AI Trader • Watchlist"
    limit = parsed.get("limit")
    try:
        if "limit" in kv_flags:
            limit = int(kv_flags["limit"])
    except Exception:
        pass
    include_filters = parsed.get("include_filters")
    if "filters" in kv_flags:
        flag = (kv_flags["filters"] or "").strip().lower()
        if flag in {"1", "true", "t", "yes", "y", "on"}:
            include_filters = True
        elif flag in {"0", "false", "f", "no", "n", "off"}:
            include_filters = False

    # Symbols: if none provided, resolve from env-selected source
    symbols_arg = parsed.get("symbols") or []
    if not symbols_arg:
        # Resolve via domain service
        from app.domain.watchlist_service import resolve_watchlist
        try:
            resolved_source, symbols_arg = resolve_watchlist()
        except Exception as exc:
            logger.warning("watchlist resolve failed: %s", exc)
            resolved_source, symbols_arg = "textlist", []
    else:
        # normalize candidate tokens (comma/space)
        tmp: list[str] = []
        for t in " ".join(symbols_arg).replace(",", " ").split():
            tok = t.strip().upper()
            if SYMBOL_RE.match(tok):
                tmp.append(tok)
        symbols_arg = tmp

    # Build enriched watchlist via scanner/builder
    wl = build_watchlist(
        symbols=symbols_arg or None,
        include_filters=(True if include_filters is None and not symbols_arg else bool(include_filters)),
        passthrough=False,
        include_ohlcv=True,
        limit=limit,
    )
    if not isinstance(wl, dict):
        raise ValueError("Watchlist response malformed")

    items = wl.get("items", [])
    session = wl.get("session", "regular")
    text = format_watchlist_message(session, items, title=title)

    # Update last-build metadata for /summary
    _WATCH_META.update(
        {
            "count": len(items or []),
            "session": session,
            "asof_utc": wl.get("asof_utc"),
        }
    )
    _reply(tg, chat_id, text or "_(empty)_")


def _handle_ping(tg: Any, chat_id: int | str, _args: list[str]) -> None:
    _reply(tg, chat_id, "pong ✅")


def _handle_help(tg: Any, chat_id: int | str, _args: list[str]) -> None:
    _reply(
        tg,
        chat_id,
        "\n".join(
            [
                "*AI Trader — Commands*",
                "/start — intro",
                "/help — show this help",
                "/ping — liveness check",
                "/watchlist — build default watchlist",
                "/watchlist <SYMS...> — manual symbols (comma/space separated)",
                "Flags: `--limit=15`, `--session=pre|regular|after`, `--filters=true|false`, `--title=\"Custom\"`",
                "/summary — show last watchlist metadata",
            ]
        ),
    )

def _handle_start(tg: Any, chat_id: int | str, _args: list[str]) -> None:
    _reply(
        tg,
        chat_id,
        "*AI Trader bot ready.*\n"
        "Try: `/ping`, `/help`, `/watchlist`, or `/watchlist AAPL TSLA NVDA`",
    )

def _handle_summary(tg: Any, chat_id: int | str, _args: list[str]) -> None:
    asof = _WATCH_META.get("asof_utc") or "never"
    session = _WATCH_META.get("session") or "regular"
    count = int(_WATCH_META.get("count") or 0)
    _reply(
        tg,
        chat_id,
        "*Watchlist Summary*\n"
        f"• Last build: `{asof}`\n"
        f"• Session: `{session}`\n"
        f"• Symbols tracked: *{count}*",
    )


COMMANDS = {
    "/start": _handle_start,
    "/help": _handle_help,
    "/ping": _handle_ping,
    "/watchlist": _handle_watchlist,
    "/summary": _handle_summary,
}

# --- webhook -----------------------------------------------------------------
@router.post("/webhook")
def webhook(
    payload: Dict[str, Any] = Body(...),
    x_secret_primary: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    x_secret_legacy: Optional[str] = Header(None, alias="X-Telegram-Secret-Token"),
    tg: Any = Depends(TelegramDep),
) -> Dict[str, Any]:
    """
    Accepts webhook events. In tests/dev, accepts missing/empty secret.
    In production (ENV=prod), requires a matching secret if configured.
    """
    if not payload:
        raise HTTPException(status_code=400, detail="Missing payload")

    # Secret gate: only enforce in prod unless test bypass flag
    env = (os.getenv("ENV") or "dev").lower()
    configured_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    provided_secret = (x_secret_primary or x_secret_legacy or "").strip()
    test_mode = (
        env.startswith("test")
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
        or ALLOW_NO_SECRET
    )
    require_secret = bool(configured_secret) and not test_mode

    _dump_webhook_debug(
        "enter",
        payload=payload,
        hdr_primary=x_secret_primary,
        hdr_legacy=x_secret_legacy,
        env_secret=configured_secret,
        test_mode=test_mode,
        allow_empty=not require_secret,
        env_name=env,
        bot_token_set=bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
    )

    if require_secret and provided_secret != configured_secret:
        _dump_webhook_debug(
            "unauthorized",
            payload=payload,
            hdr_primary=x_secret_primary,
            hdr_legacy=x_secret_legacy,
            env_secret=configured_secret,
            test_mode=test_mode,
            allow_empty=False,
            env_name=env,
            bot_token_set=True,
        )
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Extract chat/message
    msg = (payload.get("message") or payload.get("edited_message") or {})
    chat_id = (msg.get("chat") or {}).get("id") or os.getenv("TELEGRAM_DEFAULT_CHAT_ID")
    user_id = (msg.get("from") or {}).get("id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing chat id")

    # Enforce allowed-user list if configured
    if not _is_authorized(user_id):
        logger.info("[tg] unauthorized user id=%s (ignored)", user_id)
        return {"ok": True, "ignored": True}

    text = (msg.get("text") or "").strip()
    cmd, args = _parse_command(text)

    handler = COMMANDS.get(cmd)
    if handler:
        handler(tg, chat_id, args)
        return {"ok": True, "cmd": cmd}

    # Free-text fallback: attempt to parse tickers and run /watchlist
    if text and not text.startswith("/"):
        try_syms: list[str] = []
        for t in text.replace(",", " ").split():
            tok = t.strip().upper()
            if SYMBOL_RE.match(tok):
                try_syms.append(tok)
        if try_syms:
            _handle_watchlist(tg, chat_id, try_syms)
            return {"ok": True, "cmd": "/watchlist", "implicit": True}

    _handle_help(tg, chat_id, [])
    return {"ok": True, "cmd": "/help"}
