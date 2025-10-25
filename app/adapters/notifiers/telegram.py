from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, Optional, Set

import requests

from app.utils import env as ENV

log = logging.getLogger(__name__)
API_BASE = "https://api.telegram.org"


def _coerce_chat_id(cid: Optional[str | int]) -> Optional[str | int]:
    if cid is None:
        return None
    try:
        # Telegram accepts strings; keep numeric if convertible
        return int(str(cid))
    except Exception:
        return str(cid)


def _split_chunks(text: str, limit: int = 3500) -> list[str]:
    """Split text conservatively under Telegram's 4096 cap (room for formatting).

    If a single line exceeds `limit`, hard-wrap that line.
    """
    if not text:
        return ["(empty)"]
    if limit < 1:
        limit = 1

    chunks: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            chunks.append(buf)
            buf = ""

    for ln in text.splitlines(True):  # keepends=True
        # If an individual line is too large, hard-wrap it into slices
        while len(ln) > limit:
            head, ln = ln[:limit], ln[limit:]
            if len(buf) + len(head) > limit:
                flush()
            buf += head
            flush()
        # Now ln is <= limit
        if len(buf) + len(ln) > limit:
            flush()
        buf += ln

    flush()
    return chunks


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        allowed_users: Set[int] | None = None,
        webhook_secret: str | None = None,
        timeout: int = 10,
    ) -> None:
        self.base = f"{API_BASE}/bot{bot_token}" if bot_token else ""
        self.allowed = allowed_users or set()
        self.secret = webhook_secret or ""
        self.timeout = timeout

    # --- Auth Helpers ---
    def is_allowed(self, chat_id: int | str) -> bool:
        if not self.allowed:
            # permissive if no allowlist configured
            return True
        try:
            return int(str(chat_id)) in self.allowed
        except Exception:
            return False

    def verify_webhook(self, header_secret: Optional[str]) -> bool:
        return (header_secret or "") == self.secret

    # --- Message Sending ---
    def send_text(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        disable_preview: bool = True,
    ) -> bool:
        return self._send(
            chat_id, text, parse_mode=parse_mode, disable_preview=disable_preview
        )

    def send_markdown(
        self, chat_id: int | str, text: str, disable_preview: bool = True
    ) -> bool:
        return self._send(
            chat_id, text, parse_mode="Markdown", disable_preview=disable_preview
        )

    def send_html(
        self, chat_id: int | str, text: str, disable_preview: bool = True
    ) -> bool:
        return self._send(
            chat_id, text, parse_mode="HTML", disable_preview=disable_preview
        )

    def send_document(
        self, chat_id: int | str, file_path: str, caption: Optional[str] = None
    ) -> bool:
        if not self.base:
            log.warning("[Telegram] Missing bot token; skipping document send")
            return False
        url = f"{self.base}/sendDocument"
        try:
            with open(file_path, "rb") as doc:
                files = {"document": doc}
                data: Dict[str, Any] = {"chat_id": _coerce_chat_id(chat_id)}
                if caption:
                    data["caption"] = caption
                resp = requests.post(url, data=data, files=files, timeout=self.timeout)
            if 200 <= resp.status_code < 300:
                log.info("[Telegram] Document sent to %s: %s", chat_id, file_path)
                return True
            log.warning(
                "[Telegram] Failed to send document: %s %s", resp.status_code, resp.text
            )
        except Exception as e:
            log.error("[Telegram] Error sending document: %s", e)
        return False

    def smart_send(
        self,
        chat_id: int | str,
        text: str,
        mode: str = "Markdown",
        chunk_size: int = 3500,
        retries: int = 2,
    ) -> bool:
        ok = True
        for part in _split_chunks(text, limit=chunk_size):
            for attempt in range(retries + 1):
                if self._send(chat_id, part, parse_mode=mode):
                    break
                if attempt < retries:
                    delay = 1.5 * (attempt + 1)
                    log.warning(
                        "[Telegram] Retry %s sending chunk to %s in %.1fs",
                        attempt + 1,
                        chat_id,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    ok = False
        return ok

    def ping(self) -> bool:
        """Lightweight sanity check using getMe."""
        if not self.base:
            log.warning("[Telegram] Missing bot token; cannot ping")
            return False
        url = f"{self.base}/getMe"
        try:
            resp = requests.get(url, timeout=self.timeout)
            if 200 <= resp.status_code < 300:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                result = (data or {}).get("result") or {}
                username = result.get("username") or "unknown"
                bot_id = result.get("id") or "?"
                log.info("[Telegram] Bot OK: @%s id=%s", username, bot_id)
                return True
            log.warning("[Telegram] Ping failed HTTP %s: %s", resp.status_code, resp.text)
        except Exception as e:
            log.error("[Telegram] Ping error: %s", e)
        return False

    # --- Internal HTTP ---
    def _send(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: Optional[str] = None,
        disable_preview: bool = True,
    ) -> bool:
        if not self.base:
            log.warning("[Telegram] Missing bot token; skipping send")
            return False
        # Defensive: Telegram hard limit is 4096 chars; trim if somehow exceeded
        if len(text) > 4096:
            text = text[:4096]
        url = f"{self.base}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": _coerce_chat_id(chat_id),
            "text": text,
            "disable_web_page_preview": disable_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if 200 <= resp.status_code < 300:
                log.debug("[Telegram] Sent %d chars to %s", len(text), chat_id)
                return True
            log.warning("[Telegram] HTTP %s: %s", resp.status_code, resp.text)
        except Exception as e:
            log.error("[Telegram] Send error: %s", e)
        return False


# --- Module-level helpers -------------------------------------------------------


def build_client_from_env() -> TelegramClient:
    token = ENV.TELEGRAM_BOT_TOKEN
    allowed = ENV.TELEGRAM_ALLOWED_USER_IDS
    secret = ENV.TELEGRAM_WEBHOOK_SECRET
    timeout = ENV.TELEGRAM_TIMEOUT_SECS

    if not token:
        log.warning("[Telegram] TELEGRAM_BOT_TOKEN is not set — sending will be disabled")
    if not secret:
        log.info("[Telegram] TELEGRAM_WEBHOOK_SECRET not configured (webhook auth disabled)")
    if allowed:
        log.info("[Telegram] Allowed users configured: %d", len(allowed))

    return TelegramClient(
        bot_token=token,
        allowed_users=allowed,
        webhook_secret=secret,
        timeout=timeout,
    )


def format_watchlist_message(
    session: str, items: Iterable[dict], title: str = "AI Trader • Watchlist"
) -> str:
    header = f"*{title}* — _{session}_\n"
    lines = []
    for it in items:
        sym = it.get("symbol", "?")
        last = it.get("last")
        src = it.get("price_source", "")
        vol = (it.get("ohlcv") or {}).get("v")
        last_s = f"${last:,.2f}" if isinstance(last, (int, float)) and last else "$0.00"
        vol_s = f"{vol:,}" if isinstance(vol, int) and vol is not None else "0"
        suffix = f"  `{src}`" if src else ""
        lines.append(f"{sym:<6} {last_s:>10}  vol {vol_s}{suffix}")
    return header + ("\n".join(lines) if lines else "_No candidates._")


def send_watchlist(
    session: str,
    items: Iterable[dict],
    *,
    chat_id: Optional[str | int] = None,
    title: str = "AI Trader • Watchlist",
) -> bool:
    # Prefer explicit chat_id argument; fallback to env default
    target = _coerce_chat_id(chat_id) if chat_id is not None else _coerce_chat_id(ENV.TELEGRAM_DEFAULT_CHAT_ID)
    if target is None:
        log.warning("[Telegram] No chat_id (arg or TELEGRAM_DEFAULT_CHAT_ID). Skipping send.")
        return False
    client = build_client_from_env()
    msg = format_watchlist_message(session, items, title=title)
    return client.smart_send(target, msg, mode="Markdown", chunk_size=3500, retries=2)
