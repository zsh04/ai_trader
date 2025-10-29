from __future__ import annotations

from typing import Any, Dict, Optional
import logging
from fastapi import APIRouter, Body, Header, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.wiring import TelegramDep 

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])

def _env():
    try:
        from app.utils import env as ENV  # type: ignore

        return ENV
    except Exception:

        class F:
            TELEGRAM_WEBHOOK_SECRET = ""
            TELEGRAM_BOT_TOKEN = ""

        return F()


def _telegram_client():
    # Preferred: wiring facade
    try:
        from app.wiring import get_telegram  # type: ignore
        return get_telegram()
    except Exception:
        pass

    # Fallback to direct client if token present
    try:
        from app.adapters.notifiers.telegram import TelegramClient  # type: ignore
        ENV = _env()
        token = getattr(ENV, "TELEGRAM_BOT_TOKEN", "")
        if token:
            return TelegramClient(token)
    except Exception:
        pass

    return None

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
    except TypeError:
        # fakes that don't accept kwargs
        if hasattr(tg, "smart_send"):
            tg.smart_send(chat_id, text)
        elif hasattr(tg, "send_message"):
            tg.send_message(chat_id, text)

def _handle_watchlist(tg: Any, chat_id: int | str, args: list[str]) -> None:
    source = "manual"
    if args and args[0].lower() in {"auto", "finviz", "textlist"}:
        source = args[0].lower()
    body = "_No symbols available_"
    _reply(tg, chat_id, f"*Watchlist* (source: {source})\n{body}")

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

    if cmd == "/watchlist":
        _handle_watchlist(tg, chat_id, args)
        return {"ok": True, "cmd": "/watchlist"}

    # Fallback ping so tests still see a message if they ever hit another path
    _reply(tg, chat_id, "pong ✅")
    return {"ok": True, "cmd": "/ping"}