from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(tags=["telegram"])


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
    # Preferred: dependency wrapper if present
    try:
        from app.wiring.telegram_router import TelegramDep  # type: ignore

        return TelegramDep()
    except Exception:
        # Fallback to direct client
        try:
            from app.adapters.notifiers.telegram import TelegramClient  # type: ignore

            ENV = _env()
            if getattr(ENV, "TELEGRAM_BOT_TOKEN", None):
                return TelegramClient(ENV.TELEGRAM_BOT_TOKEN)
        except Exception:
            pass
    return None


@router.post("/telegram/webhook")
def telegram_webhook(
    payload: Dict[str, Any] = Body(...),
    x_telegram_secret: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
):
    ENV = _env()
    expected = getattr(ENV, "TELEGRAM_WEBHOOK_SECRET", "") or ""
    if expected and (x_telegram_secret or "") != expected:
        raise HTTPException(status_code=401, detail="bad secret")

    # Delegate to wiring if available
    try:
        from app.wiring.telegram_router import process_update  # type: ignore

        tg = _telegram_client()
        result = process_update(tg, payload)  # type: ignore
        return JSONResponse(
            {"ok": True, "result": result} if result is not None else {"ok": True}
        )
    except Exception:
        # Simple built-in ping for smoke-test
        msg = (payload or {}).get("message") or {}
        text = (msg.get("text") or "").strip().lower()
        if text.startswith("/ping"):
            chat_id = (msg.get("chat") or {}).get("id")
            tg = _telegram_client()
            if tg and chat_id:
                try:
                    tg.send_text(chat_id, "pong")  # type: ignore
                except Exception:
                    pass
            return {"ok": True, "pong": True}
        return {"ok": True}
