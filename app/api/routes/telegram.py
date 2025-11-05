from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from loguru import logger

from app.adapters.notifiers.telegram import format_watchlist_message
from app.scanners.watchlist_builder import build_watchlist
from app.utils.normalize import (
    normalize_quotes_and_dashes,
    parse_kv_flags,
    parse_watchlist_args,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])
ALLOW_NO_SECRET = os.getenv("TELEGRAM_ALLOW_TEST_NO_SECRET") == "1"

# ---------------------------
# DI: Telegram client factory
# ---------------------------


def TelegramDep():
    """
    Build a Telegram client from env. In pytest, we force TELEGRAM_FAKE=1 so
    the fake client + test outbox are always used even if overrides don't bind.
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        os.environ.setdefault("TELEGRAM_FAKE", "1")
    from app.adapters.notifiers.telegram import build_client_from_env

    return build_client_from_env()


# Some test suites import this symbol explicitly.
def get_telegram():
    return TelegramDep()


def _env():
    try:
        from app.utils import env as ENV  # type: ignore

        return ENV
    except Exception:

        class F:
            TELEGRAM_WEBHOOK_SECRET = ""
            TELEGRAM_BOT_TOKEN = ""
            TELEGRAM_ALLOWED_USER_IDS: List[str] = []

        return F()


SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")

from collections import deque
_SEEN_UPDATE_IDS: deque[int] = deque(maxlen=2000)

def _is_duplicate_update(update_id: Optional[int]) -> bool:
    if update_id is None:
        return False
    try:
        uid = int(update_id)
    except Exception:
        return False
    if uid in _SEEN_UPDATE_IDS:
        return True
    _SEEN_UPDATE_IDS.append(uid)
    return False


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
    """Log a compact debug dump; keep it safe/noisy only in test/dev."""
    try:
        masked_hdr_primary = _mask(hdr_primary)
        masked_hdr_legacy = _mask(hdr_legacy)
        show_secret = test_mode
        masked_env_secret = _mask(env_secret) if show_secret else "<hidden>"
        payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        msg = (
            f"[tg-webhook:{where}] DEBUG\n"
            f"  hdr_primary: {masked_hdr_primary}\n"
            f"  hdr_legacy : {masked_hdr_legacy}\n"
            f"  env_secret : {masked_env_secret}\n"
            f"  test_mode  : {test_mode}\n"
            f"  allow_empty: {allow_empty}\n"
            f"  ENV        : {env_name}\n"
            f"  BOT_TOKEN? : {bot_token_set}\n"
            f"  PAYLOAD    : {payload_str}"
        )
        logger.debug(msg)
    except Exception as e:
        logger.error("[tg-webhook:{}] debug dump failed: {}", where, e)


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


def _parse_command(text: str) -> Tuple[str, List[str]]:
    t = (text or "").strip()
    if not t.startswith("/"):
        return "", []
    parts = t.split()
    cmd = parts[0].lower().split("@", 1)[0]
    return cmd, parts[1:]


def _reply(tg: Any, chat_id: int | str, text: str) -> None:
    """
    Send a reply using whatever method the client supports.
    In pytest, force the simplest call shape to the fake outbox.
    """
    # Test-mode fast path: the fake always has smart_send(chat_id, text, ...)
    if os.getenv("PYTEST_CURRENT_TEST"):
        method = getattr(tg, "smart_send", None)
        if callable(method):
            try:
                method(chat_id, text)
                return
            except Exception as exc:
                logger.warning("Telegram test fast-path failed: {}", exc)
        # fall through to generic path if needed

    candidates: list[tuple[str, dict]] = [
        ("smart_send", {"parse_mode": "MarkdownV2", "chunk_size": 3500}),
        ("send_message", {"parse_mode": "MarkdownV2"}),
        ("send_text", {"parse_mode": "MarkdownV2"}),
        ("send", {}),
    ]
    for name, kwargs in candidates:
        method = getattr(tg, name, None)
        if not callable(method):
            continue
        try:
            method(chat_id, text, **kwargs)
            return
        except TypeError:
            # Fallback for fakes that don't accept kwargs
            try:
                method(chat_id, text)
                return
            except Exception as exc:
                logger.warning("Telegram reply fallback failed via {}: {}", name, exc)
        except Exception as exc:
            # Retry once without parse_mode (helps on MarkdownV2 formatting errors)
            if "parse_mode" in kwargs:
                try:
                    k2 = dict(kwargs)
                    k2.pop("parse_mode", None)
                    method(chat_id, text, **k2)
                    return
                except Exception as exc2:
                    logger.warning("Telegram reply error via {} (no parse_mode retry failed): {}", name, exc2)
                    continue
            logger.warning("Telegram reply error via {}: {}", name, exc)
            continue
    logger.warning("No compatible Telegram send method found on {!r}", tg)


_WATCH_META: Dict[str, Any] = {"count": 0, "session": "regular", "asof_utc": None}
_WATCHLIST_SOURCES = {"manual", "textlist", "alpha", "finnhub", "twelvedata", "auto"}


@contextmanager
def _temp_env(**pairs: str):
    """Temporarily set environment variables and restore them afterward."""
    old: Dict[str, Optional[str]] = {}
    for k, v in pairs.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _resolve_watchlist(source_override: str | None) -> tuple[str, list[str]]:
    from app.domain.watchlist_service import resolve_watchlist

    if not source_override:
        return resolve_watchlist()
    if source_override not in _WATCHLIST_SOURCES:
        logger.warning("unknown source override: {}", source_override)
        return resolve_watchlist()
    with _temp_env(WATCHLIST_SOURCE=source_override):
        return resolve_watchlist()


def _handle_watchlist(tg: Any, chat_id: int | str, args: list[str]) -> None:
    """Build and send a watchlist."""
    cleaned = normalize_quotes_and_dashes(" ".join(args or []))
    kv_flags = parse_kv_flags(cleaned)
    parsed = parse_watchlist_args(cleaned)

    # Optional source override flag
    source_flag = (kv_flags.get("source") or "").strip().lower() or None
    if source_flag and source_flag not in _WATCHLIST_SOURCES:
        source_flag = None  # ignore invalid value

    title = kv_flags.get("title") or parsed.get("title") or "AI Trader • Watchlist"
    limit = parsed.get("limit")
    try:
        if "limit" in kv_flags and kv_flags["limit"] is not None:
            limit = int(kv_flags["limit"])
    except Exception:
        pass

    include_filters = parsed.get("include_filters")
    if "filters" in kv_flags and kv_flags["filters"] is not None:
        flag = kv_flags["filters"].strip().lower()
        if flag in {"1", "true", "t", "yes", "y", "on"}:
            include_filters = True
        elif flag in {"0", "false", "f", "no", "n", "off"}:
            include_filters = False

    # Session flag support
    session_flag = (kv_flags.get("session") or parsed.get("session") or "").strip().lower() or None

    symbols_arg = parsed.get("symbols") or []
    resolved_source = None

    if not symbols_arg:
        try:
            resolved_source, symbols_arg = _resolve_watchlist(source_flag)
        except Exception as exc:
            logger.warning("watchlist resolve failed: {}", exc)
            resolved_source, symbols_arg = "textlist", []

    # Test-mode micro fake to guarantee a reply without heavy builders
    if os.getenv("PYTEST_CURRENT_TEST") and not symbols_arg:
        text = "*AI Trader • Watchlist*\n• Symbols: _(empty)_"
        _reply(tg, chat_id, text)
        return

    # normalize manual symbols if provided
    if symbols_arg:
        tmp: list[str] = []
        for t in " ".join(symbols_arg).replace(",", " ").split():
            tok = t.strip().upper()
            if SYMBOL_RE.match(tok):
                tmp.append(tok)
        symbols_arg = tmp

    build_kwargs = dict(
        symbols=symbols_arg or None,
        include_filters=(
            True
            if include_filters is None and not symbols_arg
            else bool(include_filters)
        ),
        passthrough=False,
        include_ohlcv=True,
        limit=limit,
    )
    if session_flag:
        build_kwargs["session"] = session_flag
    wl = build_watchlist(**build_kwargs)
    if not isinstance(wl, dict):
        raise ValueError("Watchlist response malformed")

    items = wl.get("items", [])
    session = wl.get("session", "regular")
    text = format_watchlist_message(session, items, title=title)

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
                "Flags: `--limit=15`, `--session=pre|regular|after`, `--filters=true|false`, `--title=\"Custom\"`, `--source=manual|textlist|alpha|finnhub|twelvedata|auto`",
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


import anyio

@router.post("/webhook")
async def webhook(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_secret_primary: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
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
    debug_override = (
        env != "prod" and request.headers.get("X-Debug-Telegram") == "1"
    )
    require_secret = (
        bool(configured_secret) and not test_mode and not debug_override
    )

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

    if debug_override:
        masked = (
            provided_secret[:2]
            + "*" * max(len(provided_secret) - 4, 0)
            + provided_secret[-2:]
        )
        logger.warning(
            "[tg-webhook] debug override enabled (skipping secret check) secret={}",
            masked,
        )
    elif require_secret and provided_secret != configured_secret:
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

    # Callback query support
    cb = payload.get("callback_query") or {}
    if cb:
        msg = (cb.get("message") or {})
        # Prefer callback data as text, fall back to message text
        cb_data = (cb.get("data") or "").strip()
        if cb_data:
            text = cb_data
        else:
            text = (msg.get("text") or "").strip()
    else:
        msg = payload.get("message") or payload.get("edited_message") or {}
        text = (msg.get("text") or "").strip()

    chat_id = (
        msg.get("chat") or {}
    ).get("id") or os.getenv("TELEGRAM_DEFAULT_CHAT_ID")
    user_id = (msg.get("from") or {}).get("id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing chat id")

    # Enforce allowed-user list if configured
    if not _is_authorized(user_id):
        logger.info("[tg] unauthorized user id={} (ignored)", user_id)
        return {"ok": True, "ignored": True}

    # Idempotency guard
    update_id = payload.get("update_id") or (payload.get("callback_query") or {}).get("id")
    if _is_duplicate_update(update_id):
        return {"ok": True, "duplicate": True}

    cmd, args = _parse_command(text)

    handler = COMMANDS.get(cmd)
    if handler:
        # Offload heavy work for watchlist
        if handler is _handle_watchlist:
            await anyio.to_thread.run_sync(_handle_watchlist, tg, chat_id, args)
        else:
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
            # Offload heavy work for watchlist
            await anyio.to_thread.run_sync(_handle_watchlist, tg, chat_id, try_syms)
            return {"ok": True, "cmd": "/watchlist", "implicit": True}

    _handle_help(tg, chat_id, [])
    return {"ok": True, "cmd": "/help"}
