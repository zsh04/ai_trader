# app/wiring/telegram_router.py
from __future__ import annotations

import hmac
import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple, Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.adapters.notifiers.telegram import TelegramClient, format_watchlist_message
from app.scanners.watchlist_builder import build_watchlist
from app.utils import env as ENV

log = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

# ------------------------------------------------------------------------------
# Telegram client singleton
# ------------------------------------------------------------------------------
_client: Optional[TelegramClient] = None


def _sanitize(value: Optional[str]) -> str:
    """Trim quotes/whitespace; normalize None to empty string."""
    return (value or "").strip().strip('"').strip("'")


def get_telegram() -> TelegramClient:
    """Single place to construct the client from env."""
    token = _sanitize(ENV.TELEGRAM_BOT_TOKEN)
    return TelegramClient(token)


def TelegramDep() -> TelegramClient:
    """FastAPI dependency that returns a singleton Telegram client."""
    global _client
    if _client:
        return _client
    bot_token = _sanitize(ENV.TELEGRAM_BOT_TOKEN)
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    _client = TelegramClient(bot_token=bot_token)
    return _client


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
# --- Normalization: turn fancy dashes/quotes into plain CLI-friendly ones ---
_FANCY_DASHES = {"\u2013", "\u2014", "\u2212"}  # en dash, em dash, minus
_QUOTES_MAP = {
    "\u201c": '"',
    "\u201d": '"',  # curly double
    "\u201e": '"',
    "\u201f": '"',
    "\u00ab": '"',
    "\u00bb": '"',  # guillemets
    "\u2018": "'",
    "\u2019": "'",  # curly single
    "\u2032": "'",
    "\u2033": '"',  # primes sometimes appear
}


def _normalize_cli(s: str) -> str:
    # Unicode compatibility and normalization
    s = unicodedata.normalize("NFKC", s or "")
    # Replace fancy dashes with double-dash (flag) form
    for d in _FANCY_DASHES:
        s = s.replace(d, "--")
    # Replace curly quotes with straight quotes
    for k, v in _QUOTES_MAP.items():
        s = s.replace(k, v)
    # Normalize optional spaces around '='
    s = re.sub(r"\s*=\s*", "=", s)
    # Handle more exotic mobile punctuation
    s = s.replace("—", "--").replace("–", "--")  # em/en dash
    s = s.replace("‘", "'").replace("’", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("`", "'")  # backtick
    return s.strip()


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


def _parse_watchlist_args(args: List[str]) -> Dict[str, Any]:
    import shlex

    opts = {
        "symbols": [],
        "limit": None,
        "session_hint": None,
        "title": None,
        "include_filters": None,
    }

    # Use shlex for robust parsing (handles quotes)
    parts = shlex.split(" ".join(args))
    for a in parts:
        if a.startswith("--limit="):
            try:
                opts["limit"] = int(a.split("=", 1)[1])
            except ValueError:
                pass
        elif a.startswith("--session="):
            opts["session_hint"] = a.split("=", 1)[1]
        elif a.startswith("--title="):
            opts["title"] = a.split("=", 1)[1].strip('"').strip("'")
        elif a in ("--filters", "--no-filters"):
            opts["include_filters"] = a == "--filters"
        elif not a.startswith("--"):
            opts["symbols"].append(a.upper())

    return opts


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
    _reply(
        tg,
        chat_id,
        "*Commands*\n"
        "• `/ping` — health check\n"
        "• `/watchlist` — build watchlist using default config\n"
        "• `/watchlist <SYMS...>` — on-demand list using provided symbols (space-separated or comma-separated)\n"
        '• Flags: `--no-filters`, `--filters`, `--limit=15`, `--session=pre|regular|after`, `--title="Custom"`\n'
        "• `/help` — this menu",
    )


def cmd_ping(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    _reply(tg, chat_id, "pong ✅")


def cmd_watchlist(tg: TelegramClient, chat_id: int, args: List[str]) -> None:
    try:
        opts = _parse_watchlist_args(args)
        symbols = opts["symbols"] or None
        include_filters = opts["include_filters"]
        title = opts["title"] or "AI Trader • Watchlist"

        wl = build_watchlist(
            symbols=symbols,
            include_filters=(
                True
                if include_filters is None and not symbols
                else bool(include_filters)
            ),
            passthrough=False,
            include_ohlcv=True,
        )

        items = wl.get("items", []) if isinstance(wl, dict) else []
        session = wl.get("session", "regular") if isinstance(wl, dict) else "regular"
        text = format_watchlist_message(session, items, title=title)
        _reply(tg, chat_id, text or "_(empty)_")
    except Exception as e:
        _reply(tg, chat_id, f"⚠️ *Failed to build watchlist:*\n`{e}`")


COMMANDS: Dict[str, Callable[[TelegramClient, int, List[str]], None]] = {
    "/start": cmd_start,
    "/help": cmd_help,
    "/ping": cmd_ping,
    "/watchlist": cmd_watchlist,
}


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
    env_secret = _sanitize(ENV.TELEGRAM_WEBHOOK_SECRET)
    hdr_secret = _sanitize(x_secret_primary or x_secret_legacy)

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
    text = msg.get("text") or ""
    cmd, args = _parse_command(text)

    handler = COMMANDS.get(cmd)
    if handler:
        handler(tg, int(chat), args)
        return {"ok": True, "cmd": cmd}

    # Treat free text as `/watchlist <text>` fallback (optional)
    if text and not text.startswith("/"):
        try_syms = [
            t.strip().upper()
            for t in text.replace(",", " ").split()
            if t.strip().isalpha()
        ]
        if try_syms:
            cmd_watchlist(tg, int(chat), try_syms)
            return {"ok": True, "cmd": "/watchlist", "implicit": True}

    # Default help
    cmd_help(tg, int(chat), [])
    return {"ok": True, "cmd": "/help"}
