from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Header, HTTPException, Depends
from fastapi.responses import JSONResponse

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
    source_arg = args[0].lower() if args else None
    if source_arg not in _WATCHLIST_SOURCES:
        source_arg = None

    resolved_source = source_arg or "textlist"
    symbols: list[str] = []
    try:
        resolved_source, symbols = _resolve_watchlist(source_arg)
    except Exception as exc:
        logger.warning("watchlist resolve failed: %s", exc)

    body = "\n".join(symbols) if symbols else "_No symbols available_"
    _reply(tg, chat_id, f"*Watchlist* (source: {resolved_source})\n{body}")


def _handle_ping(tg: Any, chat_id: int | str, _args: list[str]) -> None:
    _reply(tg, chat_id, "pong ✅")


def _handle_help(tg: Any, chat_id: int | str, _args: list[str]) -> None:
    _reply(
        tg,
        chat_id,
        "\n".join(
            [
                "*AI Trader — Commands*",
                "/help — show this help",
                "/ping — liveness check",
                "/watchlist [manual|textlist|finviz] — show watchlist",
            ]
        ),
    )


COMMANDS = {
    "/help": _handle_help,
    "/ping": _handle_ping,
    "/watchlist": _handle_watchlist,
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

    # Secret gate: only enforce in prod
    env = os.getenv("ENV", "dev").lower()
    running_tests = bool(os.getenv("PYTEST_CURRENT_TEST"))
    configured_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

    provided_secret = (x_secret_primary or x_secret_legacy or "").strip()

    if env == "prod" and configured_secret:
        if provided_secret != configured_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")

    # Extract chat/message
    msg = (payload.get("message") or payload.get("edited_message") or {})
    chat_id = (msg.get("chat") or {}).get("id") or os.getenv("TELEGRAM_DEFAULT_CHAT_ID")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing chat id")

    text = msg.get("text") or ""
    cmd, args = _parse_command(text)

    handler = COMMANDS.get(cmd)
    if handler:
        handler(tg, chat_id, args)
        return {"ok": True, "cmd": cmd}
    _handle_help(tg, chat_id, [])
    return {"ok": True, "cmd": "/help"}
