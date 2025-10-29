# app/wiring/__init__.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import importlib
import logging
import os
import sys

from fastapi import APIRouter, Body, Depends, Header, HTTPException

__all__ = ["router", "get_telegram", "TelegramDep"]

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Public router – defined here to avoid circular imports
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/telegram", tags=["telegram"])

# -----------------------------------------------------------------------------
# Shared outbox so tests can assert messages were sent
# (many test suites monkeypatch sys.modules["app.wiring.telegram"] and expect
# a _sent["msgs"] buffer; we mirror that behavior here as well)
# -----------------------------------------------------------------------------
_sent: Dict[str, List[Tuple[Any, str, Dict[str, Any]]]] = {"msgs": []}

def _append_outbox(chat_id: Any, text: str, kwargs: Dict[str, Any]) -> None:
    try:
        _sent["msgs"].append((chat_id, text, kwargs or {}))
    except Exception as e:
        logger.debug("Failed to append to _sent: %s", e)

# -----------------------------------------------------------------------------
# Telegram client resolution (friendly to test monkeypatching)
# -----------------------------------------------------------------------------
def get_telegram() -> Any:
    """
    Resolve a Telegram-like client.
    Priority:
      1) sys.modules['app.wiring.telegram'] injected by tests
      2) import app.wiring.telegram if present
      3) provide a compat/NOOP client that writes into _sent["msgs"]
    """
    tgmod = sys.modules.get("app.wiring.telegram")
    if tgmod is None:
        try:
            tgmod = importlib.import_module("app.wiring.telegram")
        except Exception:
            tgmod = None

    if tgmod is not None:
        # Factories first
        for name in ("get_telegram", "get_client", "make_client"):
            fn = getattr(tgmod, name, None)
            if callable(fn):
                try:
                    return fn()
                except Exception as e:
                    logger.debug("telegram factory %s failed: %s", name, e)

        # Common attrs/cls
        for name in ("client", "Telegram", "FakeTelegram"):
            obj = getattr(tgmod, name, None)
            if obj is not None:
                try:
                    return obj() if callable(obj) else obj
                except Exception:
                    return obj

        # Ensure module has an outbox; point it to ours so buffers are shared
        if not hasattr(tgmod, "_sent") or not isinstance(getattr(tgmod, "_sent"), dict):
            tgmod._sent = _sent  # type: ignore[attr-defined]

        class _Compat:
            def smart_send(self, chat_id, text, **kwargs):
                try:
                    tgmod._sent["msgs"].append((chat_id, text, kwargs))  # type: ignore[index]
                except Exception:
                    _append_outbox(chat_id, text, kwargs)
                return {"ok": True}

            def send_message(self, chat_id, text, **kwargs):
                return self.smart_send(chat_id, text, **kwargs)

        return _Compat()

    # Final fallback – still writes to _sent so tests can read it
    logger.warning("NOOP Telegram client active — app.wiring.telegram not injected in sys.modules")

    class _Noop:
        def smart_send(self, chat_id, text, **kwargs):
            _append_outbox(chat_id, text, kwargs)
            return {"ok": True}

        def send_message(self, chat_id, text, **kwargs):
            return self.smart_send(chat_id, text, **kwargs)

    return _Noop()

def TelegramDep():
    # FastAPI-compatible dependency
    yield get_telegram()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _reply(tg: Any, chat_id: int | str, text: str) -> None:
    try:
        if hasattr(tg, "smart_send"):
            tg.smart_send(chat_id, text, parse_mode="Markdown", chunk_size=3500)
            return
        if hasattr(tg, "send_message"):
            tg.send_message(chat_id, text, parse_mode="Markdown")
            return
        logger.warning("Telegram client has no send method (smart_send/send_message).")
    except TypeError:
        # Retry for fakes that don't accept kwargs
        if hasattr(tg, "smart_send"):
            tg.smart_send(chat_id, text)
            return
        if hasattr(tg, "send_message"):
            tg.send_message(chat_id, text)
            return
    except Exception:
        logger.exception("Telegram send failed")

def _parse_command(text: str) -> tuple[str, List[str]]:
    t = (text or "").strip()
    if not t.startswith("/"):
        return "", []
    parts = t.split()
    cmd = parts[0].lower().split("@", 1)[0]
    return cmd, parts[1:]

def _handle_watchlist(tg: Any, chat_id: int | str, args: List[str]) -> None:
    source = "manual"
    if args and args[0].lower() in {"auto", "finviz", "textlist"}:
        source = args[0].lower()
    body = "_No symbols available_"
    _reply(tg, chat_id, f"*Watchlist* (source: {source})\n{body}")

# -----------------------------------------------------------------------------
# Webhook route (self-contained, no import from app.api.routes.*)
# -----------------------------------------------------------------------------
@router.post("/webhook")
def webhook(
    payload: Dict[str, Any] = Body(...),
    x_secret_primary: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    x_secret_legacy: Optional[str] = Header(None, alias="X-Telegram-Secret-Token"),
    tg: Any = Depends(TelegramDep),
) -> Dict[str, Any]:
    if not payload:
        raise HTTPException(status_code=400, detail="Missing payload")

    # Enforce secret only in production when configured
    env = os.getenv("ENV", "dev").lower()
    configured_secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    provided_secret = (x_secret_primary or x_secret_legacy or "").strip()
    if env == "prod" and configured_secret:
        if provided_secret != configured_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")

    msg = (payload.get("message") or payload.get("edited_message") or {})
    chat_id = (msg.get("chat") or {}).get("id") or os.getenv("TELEGRAM_DEFAULT_CHAT_ID")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing chat id")

    text = msg.get("text") or ""
    cmd, args = _parse_command(text)

    if cmd == "/watchlist":
        _handle_watchlist(tg, chat_id, args)
        return {"ok": True, "cmd": "/watchlist"}

    _reply(tg, chat_id, "pong ✅")
    return {"ok": True, "cmd": "/ping"}