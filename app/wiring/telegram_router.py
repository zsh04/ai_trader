# app/wiring/telegram_router.py
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Header, HTTPException
from loguru import logger
from app.domain.watchlist_service import resolve_watchlist
from app.adapters.notifiers.telegram import TelegramClient, format_watchlist_message
from app.scanners.watchlist_builder import build_watchlist
from app.utils import env as ENV
from app.utils.normalize import (
    normalize_quotes_and_dashes,
    parse_kv_flags,
    parse_watchlist_args,
)
from app.wiring.telegram import get_telegram

log = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_watchlist_meta: Dict[str, Any] = {
    "count": 0,
    "session": "regular",
    "asof_utc": None,
}


def _quote_trim(s: Optional[str]) -> str:
    if not s:
        return ""
    return str(s).strip().strip('"').strip("'")


SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,20}$")


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _mask(s: Optional[str]) -> str:
    if not s:
        return "<empty>"
    if len(s) <= 8:
        return "*" * (len(s) - 2) + s[-2:]
    return s[:2] + "*" * (len(s) - 6) + s[-4:]


def _dump_webhook_debug(
    where: str,
    *,
    payload: Dict[str, Any],
    hdr_primary: Optional[str],
    hdr_legacy: Optional[str],
    env_secret: Optional[str],
    test_mode: bool,
    allow_empty: bool,
    env_name: str,
    bot_token_set: bool,
) -> None:
    try:
        logger.warning(
            "[tg-webhook:{where}] DEBUG DUMP\n"
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
        logger.error("[tg-webhook:{where}] debug dump failed: {}", where, e)


def _is_authorized(user_id: Optional[int]) -> bool:
    """Allow all if no allowed list configured; else enforce match."""
    allow_list = ENV.TELEGRAM_ALLOWED_USER_IDS or []
    if not allow_list:
        return True
    if user_id is None:
        return False
    s = str(user_id)
    return s in {str(u) for u in allow_list}


def _extract_message(update: Dict[str, Any]) -> Dict[str, Any]:
    """Handles message and edited_message; we only care about text."""
    return update.get("message") or update.get("edited_message") or {}


def _reply(tg: TelegramClient, chat_id: int | str, text: str) -> None:
    tg.smart_send(chat_id, text, mode="Markdown", chunk_size=3500, retries=1)


def _safe_reply(
    tg: TelegramClient, chat_id: int | str, msg: str, exc: Exception | None = None
) -> None:
    note = f"⚠️ {msg}"
    if exc:
        log.warning("[tg] %s: %s", msg, exc)
    else:
        log.warning("[tg] %s", msg)
    _reply(tg, chat_id, note)


def _parse_command(text: str) -> Tuple[str, List[str]]:
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", []
    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]
    # strip bot suffix like /watchlist@YourBot
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    return cmd, args


def _watchlist_summary_text() -> str:
    """Format summary text using the latest watchlist metadata."""
    asof = _watchlist_meta.get("asof_utc") or "never"
    session = _watchlist_meta.get("session") or "regular"
    count = int(_watchlist_meta.get("count") or 0)
    return (
        "*Watchlist Summary*\n"
        f"• Last build: `{asof}`\n"
        f"• Session: `{session}`\n"
        f"• Symbols tracked: *{count}*"
    )


# ------------------------------------------------------------------------------
# Command handlers
# ------------------------------------------------------------------------------
def cmd_start(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    _reply(
        tg,
        chat_id,
        "*AI Trader bot ready.*\n"
        "Try: `/ping`, `/help`, `/watchlist`, or `/watchlist AAPL TSLA NVDA`",
    )


def cmd_help(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    flags = '`--no-filters`, `--filters`, `--limit=15`, `--session=pre|regular|after`, `--title="Custom"`'
    text = (
        "*Commands*\n"
        "• `/ping` — health check\n"
        "• `/watchlist` — build watchlist using defaults\n"
        "• `/watchlist <SYMS...>` — manual symbols (comma or space separated)\n"
        "• `/watchlist [source] [scanner] [limit] [sort]` — dynamic source mode\n"
        f"  • source: `auto|finviz|textlist`\n"
        f"  • scanner: source-specific (optional)\n"
        f"  • limit: integer cap (optional)\n"
        f"  • sort: `alpha` (optional)\n"
        f"• Flags: {flags}\n"
        "• `/summary` — last watchlist metadata\n"
        "• `/help` — this menu"
    )
    _reply(tg, chat_id, text)


def cmd_ping(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    _reply(tg, chat_id, "pong ✅")


def _bool_from_text(value: str) -> Optional[bool]:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "off"}:
        return False
    return None


def cmd_watchlist(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    # Positional dynamic form: /watchlist [source] [scanner] [limit] [sort]
    if args and args[0].lower() in {"auto", "finviz", "textlist"}:
        src = args[0].lower()
        scanner = None
        limit = None
        sort = None
        if len(args) >= 2 and not args[1].startswith("--"):
            scanner = args[1]
        if len(args) >= 3 and not args[2].startswith("--"):
            try:
                limit = int(args[2])
            except ValueError:
                limit = None
        if len(args) >= 4 and not args[3].startswith("--"):
            sort = args[3].lower()
        try:
            # resolve_watchlist is expected to accept these optional hints
            source, symbols = resolve_watchlist(source=src, scanner=scanner, limit=limit, sort=sort)  # type: ignore
            body = ", ".join(symbols) if symbols else "_No symbols available_"
            _reply(tg, chat_id, f"*Watchlist* (source: {source})\n{body}")
        except Exception as exc:
            _safe_reply(tg, chat_id, "watchlist (dynamic) failed", exc)
        return

    if not args:
        source, symbols = resolve_watchlist()
        if symbols:
            body = ", ".join(symbols)
        else:
            body = "_No symbols available_"
        text = f"*Watchlist* (source: {source})\n{body}"
        _reply(tg, chat_id, text)
        return

    cleaned = normalize_quotes_and_dashes(" ".join(args))
    opts = parse_watchlist_args(cleaned)
    kv_flags = parse_kv_flags(cleaned)
    if "title" in kv_flags:
        opts["title"] = kv_flags["title"]
    if "limit" in kv_flags:
        try:
            opts["limit"] = int(kv_flags["limit"])
        except ValueError:
            pass
    if "filters" in kv_flags:
        flag = _bool_from_text(kv_flags["filters"])
        if flag is not None:
            opts["include_filters"] = flag
    if "session" in kv_flags:
        opts["session_hint"] = kv_flags["session"]

    symbols = opts["symbols"] or None
    include_filters = opts["include_filters"]
    title = opts["title"] or "AI Trader • Watchlist"

    wl = build_watchlist(
        symbols=symbols,
        include_filters=(
            True if include_filters is None and not symbols else bool(include_filters)
        ),
        passthrough=False,
        include_ohlcv=True,
        limit=opts.get("limit"),
    )
    if not isinstance(wl, dict):
        raise ValueError("Watchlist response malformed")

    items = wl.get("items", [])
    session = wl.get("session", "regular")
    text = format_watchlist_message(session, items, title=title)
    _watchlist_meta.update(
        {
            "count": len(items or []),
            "session": session,
            "asof_utc": wl.get("asof_utc"),
        }
    )
    _reply(tg, chat_id, text or "_(empty)_")


def cmd_summary(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    """Summarize last watchlist build metadata."""
    text = _watchlist_summary_text()
    _reply(tg, chat_id, text)


COMMANDS: Dict[str, Callable[[TelegramClient, int, List[str]], None]] = {
    "/start": cmd_start,
    "/help": cmd_help,
    "/ping": cmd_ping,
    "/watchlist": cmd_watchlist,
    "/summary": cmd_summary,
}


def _run_command(
    cmd_name: str,
    handler: Callable[[TelegramClient, int, List[str]], None],
    tg: TelegramClient,
    chat_id: int,
    args: List[str],
) -> None:
    try:
        handler(tg, chat_id, args)
    except Exception as exc:
        label = cmd_name or "command"
        _safe_reply(tg, chat_id, f"{label} failed", exc)


# ------------------------------------------------------------------------------
# Webhook
# ------------------------------------------------------------------------------
@router.post("/webhook")
def webhook(
    payload: Dict[str, Any] = Body(...),
    x_secret_primary: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
    x_secret_legacy: Optional[str] = Header(None, alias="X-Telegram-Secret-Token"),
) -> Dict[str, Any]:
    tg: TelegramClient = get_telegram()

    # --- read secrets/flags dynamically so pytest monkeypatch works ---
    env_secret = _quote_trim(
        os.getenv(
            "TELEGRAM_WEBHOOK_SECRET", getattr(ENV, "TELEGRAM_WEBHOOK_SECRET", "")
        )
    )
    hdr_secret = _quote_trim(x_secret_primary or x_secret_legacy)
    raw_env = os.getenv("ENV") or getattr(ENV, "ENV", "")
    if isinstance(raw_env, str):
        env_name = raw_env.lower()
    else:
        env_name = str(raw_env).lower() if raw_env else ""

    test_mode = (
        env_name.startswith("test")
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
        or (os.getenv("TELEGRAM_ALLOW_TEST_NO_SECRET") in ("1", "true", "True"))
        or bool(getattr(ENV, "TELEGRAM_ALLOW_TEST_NO_SECRET", False))
    )

    # require secret only when we *have one* and we are not in test/bypass
    require_secret = bool(env_secret) and not test_mode

    _dump_webhook_debug(
        "enter",
        payload=payload,
        hdr_primary=x_secret_primary,
        hdr_legacy=x_secret_legacy,
        env_secret=env_secret,
        test_mode=test_mode,
        allow_empty=not require_secret,
        env_name=env_name,
        bot_token_set=bool(
            os.getenv("TELEGRAM_BOT_TOKEN", getattr(ENV, "TELEGRAM_BOT_TOKEN", ""))
        ),
    )

    if require_secret:
        if not hdr_secret or hdr_secret != env_secret:
            _dump_webhook_debug(
                "unauthorized",
                payload=payload,
                hdr_primary=x_secret_primary,
                hdr_legacy=x_secret_legacy,
                env_secret=env_secret,
                test_mode=test_mode,
                allow_empty=False,
                env_name=env_name,
                bot_token_set=True,
            )
            raise HTTPException(status_code=401, detail="bad secret")
    else:
        logger.warning("[tg] accepting webhook without secret (non-prod/test)")

    # --- Parse update ---
    msg = _extract_message(payload)
    chat = (msg.get("chat") or {}).get("id") or ENV.TELEGRAM_DEFAULT_CHAT_ID
    user = (msg.get("from") or {}).get("id")

    if not chat:
        raise HTTPException(status_code=400, detail="missing chat id")

    # --- Authorization ---
    if not _is_authorized(user):
        log.info("[tg] unauthorized user id=%s (ignored)", user)
        return {"ok": True, "ignored": True}

    # --- Command dispatch ---
    raw_text = msg.get("text") or ""
    normalized_text = normalize_quotes_and_dashes(raw_text)
    cmd, args = _parse_command(normalized_text)

    handler = COMMANDS.get(cmd)
    if handler:
        _run_command(cmd, handler, tg, int(chat), args)
        return {"ok": True, "cmd": cmd}

    # Treat free text as `/watchlist <text>` fallback (optional)
    if normalized_text and not normalized_text.startswith("/"):
        try_syms: List[str] = []
        for t in normalized_text.replace(",", " ").split():
            tok = t.strip().upper()
            if SYMBOL_RE.match(tok):
                try_syms.append(tok)
        if try_syms:
            _run_command("/watchlist", cmd_watchlist, tg, int(chat), try_syms)
            return {"ok": True, "cmd": "/watchlist", "implicit": True}

    # Default help
    _run_command("/help", cmd_help, tg, int(chat), [])
    return {"ok": True, "cmd": "/help"}
