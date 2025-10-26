# app/wiring/telegram_router.py
from __future__ import annotations

import hmac
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.adapters.notifiers.telegram import TelegramClient, format_watchlist_message
from app.scanners.watchlist_builder import build_watchlist
from app.utils import env as ENV
from app.utils.normalize import (
    normalize_quotes_and_dashes,
    parse_kv_flags,
    parse_watchlist_args,
)
from app.wiring.telegram import TelegramDep

log = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_watchlist_meta: Dict[str, Any] = {
    "count": 0,
    "session": "regular",
    "asof_utc": None,
}


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
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


def _safe_reply(tg: TelegramClient, chat_id: int | str, msg: str, exc: Exception | None = None) -> None:
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
    flags = "`--no-filters`, `--filters`, `--limit=15`, `--session=pre|regular|after`, `--title=\"Custom\"`"
    text = (
        "*Commands*\n"
        "• `/ping` — health check\n"
        "• `/watchlist` — build watchlist using defaults\n"
        "• `/watchlist <SYMS...>` — manual symbols (comma or space separated)\n"
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
    payload: Dict[str, Any],
    tg: Annotated[TelegramClient, Depends(TelegramDep)],
    # Accept both the official and legacy header names
    x_secret_primary: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
    x_secret_legacy: Optional[str] = Header(None, alias="X-Telegram-Secret-Token"),
):
    # --- Secret validation ---
    env_secret = _quote_trim(ENV.TELEGRAM_WEBHOOK_SECRET)
    hdr_secret = _quote_trim(x_secret_primary or x_secret_legacy)

    def _mask(s: str) -> str:
        return (
            f"{s[:4]}…{s[-4:]}" if len(s) >= 8 else ("(empty)" if not s else "(short)")
        )

    log.info(
        "[tg] webhook secret check env(len=%d,mask=%s) header(len=%d,mask=%s)",
        len(env_secret),
        _mask(env_secret),
        len(hdr_secret),
        _mask(hdr_secret),
    )

    if env_secret and not hmac.compare_digest(env_secret, hdr_secret):
        raise HTTPException(status_code=401, detail="bad secret")

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
        try_syms = [
            t.strip().upper()
            for t in normalized_text.replace(",", " ").split()
            if t.strip().isalpha()
        ]
        if try_syms:
            _run_command("/watchlist", cmd_watchlist, tg, int(chat), try_syms)
            return {"ok": True, "cmd": "/watchlist", "implicit": True}

    # Default help
    _run_command("/help", cmd_help, tg, int(chat), [])
    return {"ok": True, "cmd": "/help"}
