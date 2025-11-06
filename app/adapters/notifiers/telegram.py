from __future__ import annotations

import os
import time
from html import escape as html_escape
from typing import Any, Dict, Iterable, List, Optional, Set

import requests
from loguru import logger

from app.settings import get_telegram_settings
from app.utils import env as ENV
from app.utils.http import compute_backoff_delay

API_BASE = "https://api.telegram.org"

# ---------------------------
# Test-only in-memory outbox
# ---------------------------
_TEST_OUTBOX: List[Dict[str, Any]] = []


def test_outbox() -> List[Dict[str, Any]]:
    """
    Returns a shallow copy of the in-memory outbox for tests.

    Returns:
        List[Dict[str, Any]]: A list of messages in the outbox.
    """
    return list(_TEST_OUTBOX)


def test_outbox_clear() -> None:
    """Clears the in-memory outbox for tests."""
    _TEST_OUTBOX.clear()


MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def escape_mdv2(text: str) -> str:
    if not text:
        return ""
    # Escape backslash first, then specials
    text = text.replace("\\", "\\\\")
    for ch in MDV2_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text


class FakeTelegramClient:
    """
    A test double for the TelegramClient.

    Captures messages into an in-memory outbox for inspection during tests.
    """

    def __init__(self) -> None:
        """Initializes the FakeTelegramClient."""
        self.allowed: Set[int] = set()
        self.secret = ""
        self.timeout = 1

    def smart_send(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: Optional[str] = None,
        mode: Optional[str] = None,
        chunk_size: int = 3500,
        retries: int = 0,
        **_ignore,
    ) -> bool:
        """
        Sends a message, splitting it into chunks if necessary.
        """
        for part in _split_chunks(text, limit=chunk_size):
            _TEST_OUTBOX.append(
                {
                    "chat_id": chat_id,
                    "text": part,
                    "parse_mode": parse_mode or mode or "MarkdownV2",
                }
            )
        return True

    def send_message(
        self, chat_id: int | str, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """
        Sends a message.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            parse_mode (Optional[str]): The parse mode for the message.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        return self.smart_send(chat_id, text, parse_mode=parse_mode)

    def send_text(
        self, chat_id: int | str, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """
        Sends a message.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            parse_mode (Optional[str]): The parse mode for the message.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        return self.smart_send(chat_id, text, parse_mode=parse_mode)

    def send(self, chat_id: int | str, text: str) -> bool:
        """
        Sends a message.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        return self.smart_send(chat_id, text)

    def ping(self) -> bool:
        """
        Pings the Telegram API.

        Returns:
            bool: True.
        """
        return True


def _coerce_chat_id(cid: Optional[str | int]) -> Optional[str | int]:
    """
    Coerces a chat ID to an integer if possible.

    Args:
        cid (Optional[str | int]): The chat ID.

    Returns:
        Optional[str | int]: The coerced chat ID.
    """
    if cid is None:
        return None
    try:
        return int(str(cid))
    except Exception:
        return str(cid)


def _split_chunks(text: str, limit: int = 3500) -> list[str]:
    """
    Splits text into chunks under a given limit.

    Args:
        text (str): The text to split.
        limit (int): The maximum chunk size.

    Returns:
        list[str]: A list of text chunks.
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

    for ln in text.splitlines(True):
        while len(ln) > limit:
            head, ln = ln[:limit], ln[limit:]
            if len(buf) + len(head) > limit:
                flush()
            buf += head
            flush()
        if len(buf) + len(ln) > limit:
            flush()
        buf += ln

    flush()
    return chunks


class TelegramClient:
    """A client for the Telegram Bot API."""

    def __init__(
        self,
        bot_token: str,
        allowed_users: Set[int] | None = None,
        webhook_secret: str | None = None,
        timeout: int | None = None,
        retries: Optional[int] = None,
        backoff: Optional[float] = None,
    ) -> None:
        """
        Initializes the TelegramClient.

        Args:
            bot_token (str): The Telegram bot token.
            allowed_users (Set[int] | None): A set of allowed user IDs.
            webhook_secret (str | None): The webhook secret.
            timeout (int): The request timeout.
            retries (Optional[int]): Max retry attempts for outbound HTTP.
            backoff (Optional[float]): Backoff factor between retries.
        """
        self.base = f"{API_BASE}/bot{bot_token}" if bot_token else ""
        self.allowed = allowed_users or set()
        self.secret = webhook_secret or ""
        settings = get_telegram_settings()
        default_timeout = timeout if timeout is not None else settings.timeout_secs
        self.timeout = int(default_timeout)
        self.retries = (
            int(retries) if retries is not None else getattr(ENV, "HTTP_RETRIES", 2)
        )
        self.backoff = (
            float(backoff) if backoff is not None else getattr(ENV, "HTTP_BACKOFF", 1.5)
        )

    def is_allowed(self, chat_id: int | str) -> bool:
        """
        Checks if a user is allowed to interact with the bot.

        Args:
            chat_id (int | str): The user's chat ID.

        Returns:
            bool: True if the user is allowed, False otherwise.
        """
        if not self.allowed:
            return True
        try:
            return int(str(chat_id)) in self.allowed
        except Exception:
            return False

    def verify_webhook(self, header_secret: Optional[str]) -> bool:
        """
        Verifies a webhook request.

        Args:
            header_secret (Optional[str]): The webhook secret from the request header.

        Returns:
            bool: True if the secret is valid, False otherwise.
        """
        return (header_secret or "") == self.secret

    def send_text(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: Optional[str] = None,
        disable_preview: bool = True,
    ) -> bool:
        """
        Sends a text message.
        """
        return self._send(
            chat_id, text, parse_mode=parse_mode, disable_preview=disable_preview
        )

    def send_markdown(
        self, chat_id: int | str, text: str, disable_preview: bool = True
    ) -> bool:
        """
        Sends a Markdown message.
        """
        return self._send(
            chat_id, text, parse_mode="MarkdownV2", disable_preview=disable_preview
        )

    def send_html(
        self, chat_id: int | str, text: str, disable_preview: bool = True
    ) -> bool:
        """
        Sends an HTML message.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            disable_preview (bool): Whether to disable the link preview.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        return self._send(
            chat_id, text, parse_mode="HTML", disable_preview=disable_preview
        )

    def send_document(
        self, chat_id: int | str, file_path: str, caption: Optional[str] = None
    ) -> bool:
        """
        Sends a document.

        Args:
            chat_id (int | str): The chat ID to send the document to.
            file_path (str): The path to the document.
            caption (Optional[str]): The document caption.

        Returns:
            bool: True if the document was sent successfully, False otherwise.
        """
        if not self.base:
            logger.warning("[Telegram] Missing bot token; skipping document send")
            return False
        try:
            with open(file_path, "rb") as doc:
                files = {"document": doc}
                data: Dict[str, Any] = {"chat_id": _coerce_chat_id(chat_id)}
                if caption:
                    data["caption"] = caption
                resp = self._request(
                    "POST",
                    "sendDocument",
                    data=data,
                    files=files,
                )
            if not resp:
                return False
            if 200 <= resp.status_code < 300:
                logger.info("[Telegram] Document sent to {}: {}", chat_id, file_path)
                return True
            logger.warning(
                "[Telegram] Failed to send document: {} {}",
                resp.status_code,
                resp.text,
            )
        except Exception as e:
            logger.error("[Telegram] Error sending document: {}", e)
        return False

    def smart_send(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: Optional[str] = None,
        mode: Optional[str] = None,
        chunk_size: int = 3500,
        retries: Optional[int] = None,
        **_ignore,
    ) -> bool:
        """
        Sends a long message in chunks.
        """
        eff_mode = parse_mode or mode or "MarkdownV2"
        ok = True
        chunk_retries = max(0, self.retries if retries is None else int(retries))
        for part in _split_chunks(text, limit=chunk_size):
            for attempt in range(chunk_retries + 1):
                if self._send(chat_id, part, parse_mode=eff_mode):
                    break
                if attempt < chunk_retries:
                    delay = compute_backoff_delay(attempt, self.backoff, None)
                    logger.warning(
                        "[Telegram] Retry {} sending chunk to {} in {:.1f}s",
                        attempt + 1,
                        chat_id,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    ok = False
        return ok

    def ping(self) -> bool:
        """
        Pings the Telegram API.

        Returns:
            bool: True if the ping is successful, False otherwise.
        """
        if not self.base:
            logger.warning("[Telegram] Missing bot token; cannot ping")
            return False
        try:
            resp = self._request("GET", "getMe")
            if not resp:
                return False
            if 200 <= resp.status_code < 300:
                data = (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                result = (data or {}).get("result") or {}
                username = result.get("username") or "unknown"
                bot_id = result.get("id") or "?"
                logger.info("[Telegram] Bot OK: @{} id={}", username, bot_id)
                return True
            logger.warning(
                "[Telegram] Ping failed HTTP {}: {}", resp.status_code, resp.text
            )
        except Exception as e:
            logger.error("[Telegram] Ping error: {}", e)
        return False

    def _send(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: Optional[str] = None,
        disable_preview: bool = True,
    ) -> bool:
        """
        Sends a message to the Telegram API.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            parse_mode (Optional[str]): The parse mode for the message.
            disable_preview (bool): Whether to disable the link preview.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        if not self.base:
            logger.warning("[Telegram] Missing bot token; skipping send")
            return False
        if len(text) > 4096:
            text = text[:4096]
        payload: Dict[str, Any] = {
            "chat_id": _coerce_chat_id(chat_id),
            "text": text,
            "disable_web_page_preview": disable_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = self._request("POST", "sendMessage", json=payload)
            if resp is None:
                return False
            # Non-2xx: log and bail (429 handled below)
            if not (200 <= resp.status_code < 300):
                if resp.status_code == 429:
                    try:
                        retry_after = int(resp.headers.get("Retry-After", "2"))
                    except Exception:
                        retry_after = 2
                    logger.warning(
                        "[Telegram] Rate-limited (429). Sleeping {}s", retry_after
                    )
                    time.sleep(max(0, retry_after))
                    return False
                logger.warning("[Telegram] HTTP {}: {}", resp.status_code, resp.text)
                return False
            # 2xx but Telegram-level error (ok:false)
            try:
                if resp.headers.get("content-type", "").startswith("application/json"):
                    body = resp.json() or {}
                    if body.get("ok") is False:
                        logger.warning(
                            "[Telegram] API error {}: {}",
                            body.get("error_code"),
                            body.get("description"),
                        )
                        return False
            except Exception:
                pass
            logger.debug("[Telegram] Sent {} chars to {}", len(text), chat_id)
            return True
        except Exception as e:
            logger.error("[Telegram] Send error: {}", e)
        return False

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        retries: Optional[int] = None,
        backoff: Optional[float] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Optional[requests.Response]:
        if not self.base:
            logger.warning("[Telegram] Missing bot token; cannot make request")
            return None

        attempt_retries = int(retries) if retries is not None else max(0, self.retries)
        backoff_factor = float(backoff) if backoff is not None else float(self.backoff)
        timeout_value = float(timeout) if timeout is not None else float(self.timeout)

        url = f"{self.base}/{endpoint}"
        last_exc: Exception | None = None

        for attempt in range(attempt_retries + 1):
            try:
                resp = requests.request(
                    method.upper(),
                    url,
                    timeout=timeout_value,
                    **kwargs,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < attempt_retries:
                    delay = compute_backoff_delay(attempt, backoff_factor, None)
                    logger.warning(
                        "[Telegram] HTTP {} {} exception {}; retrying in {:.2f}s ({}/{})",
                        method.upper(),
                        endpoint,
                        exc,
                        delay,
                        attempt + 1,
                        attempt_retries,
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    "[Telegram] HTTP {} {} failed after retries: {}",
                    method.upper(),
                    endpoint,
                    exc,
                )
                return None

            retryable = resp.status_code in {408, 425, 429, 500, 502, 503, 504}
            if retryable and attempt < attempt_retries:
                delay = compute_backoff_delay(
                    attempt, backoff_factor, resp.headers.get("Retry-After")
                )
                logger.warning(
                    "[Telegram] HTTP {} {} -> {} retrying in {:.2f}s ({}/{})",
                    method.upper(),
                    endpoint,
                    resp.status_code,
                    delay,
                    attempt + 1,
                    attempt_retries,
                )
                time.sleep(delay)
                continue

            return resp

        if last_exc:
            logger.error(
                "[Telegram] HTTP {} {} exhausted retries: {}",
                method.upper(),
                endpoint,
                last_exc,
            )
        return None


def build_client_from_env() -> TelegramClient | FakeTelegramClient:
    """
    Builds a Telegram client from environment variables.

    Returns:
        TelegramClient | FakeTelegramClient: A Telegram client.
    """
    settings = get_telegram_settings()

    if os.getenv("PYTEST_CURRENT_TEST") or settings.fake_mode:
        logger.info("[Telegram] Using FakeTelegramClient (test mode)")
        return FakeTelegramClient()

    token = settings.bot_token or ""
    allowed = set(settings.allowed_user_ids)
    secret = settings.webhook_secret or ""
    timeout = settings.timeout_secs

    if not token:
        logger.warning(
            "[Telegram] TELEGRAM_BOT_TOKEN is not set — sending will be disabled"
        )
    if not secret:
        logger.info(
            "[Telegram] TELEGRAM_WEBHOOK_SECRET not configured (webhook auth disabled)"
        )
    if allowed:
        logger.info("[Telegram] Allowed users configured: {}", len(allowed))

    return TelegramClient(
        bot_token=token,
        allowed_users=allowed,
        webhook_secret=secret,
        timeout=timeout,
        retries=getattr(ENV, "HTTP_RETRIES", 2),
        backoff=getattr(ENV, "HTTP_BACKOFF", 1.5),
    )


def format_watchlist_message(
    session: str, items: Iterable[dict], title: str = "AI Trader • Watchlist"
) -> str:
    """
    Formats a watchlist message for MarkdownV2, escaping dynamic fields.
    """
    header = f"*{escape_mdv2(title)}* — _{escape_mdv2(session)}_\n\n"
    lines = []
    for it in items:
        sym = escape_mdv2(str(it.get("symbol", "?")))
        last = it.get("last")
        src = escape_mdv2(str(it.get("price_source", "")))
        vol = (it.get("ohlcv") or {}).get("v")
        last_s = f"${last:,.2f}" if isinstance(last, (int, float)) and last else "$0.00"
        vol_s = f"{vol:,}" if isinstance(vol, int) and vol is not None else "0"
        suffix = f"  {src}" if src else ""
        lines.append(f"{sym:<6} {last_s:>10}  vol {vol_s}{suffix}")
    return header + ("\n".join(lines) if lines else "_No candidates._")


# HTML-safe version for Telegram to avoid MarkdownV2 parsing issues
def format_watchlist_message_html(
    session: str, items: Iterable[dict], title: str = "AI Trader • Watchlist"
) -> str:
    """
    HTML-safe version that uses <pre> to avoid MarkdownV2 entity parsing issues.
    """
    header = f"<b>{html_escape(title)}</b> — <i>{html_escape(session)}</i>\n"
    lines: List[str] = []
    for it in items:
        sym = html_escape(str(it.get("symbol", "?")))
        last = it.get("last")
        src = html_escape(str(it.get("price_source", "")))
        vol = (it.get("ohlcv") or {}).get("v")
        last_s = (
            f"${last:,.2f}"
            if isinstance(last, (int, float)) and last is not None
            else "$0.00"
        )
        vol_s = f"{vol:,}" if isinstance(vol, int) and vol is not None else "0"
        suffix = f"  {src}" if src else ""
        lines.append(f"{sym:<6} {last_s:>10}  vol {vol_s}{suffix}")
    body = "\n".join(lines) if lines else "No candidates."
    return header + "<pre>" + html_escape(body) + "</pre>"


def send_watchlist(
    session: str,
    items: Iterable[dict],
    *,
    chat_id: Optional[str | int] = None,
    title: str = "AI Trader • Watchlist",
) -> bool:
    """
    Sends a watchlist to a Telegram chat.

    Args:
        session (str): The trading session.
        items (Iterable[dict]): A list of watchlist items.
        chat_id (Optional[str | int]): The chat ID to send the watchlist to.
        title (str): The message title.

    Returns:
        bool: True if the watchlist was sent successfully, False otherwise.
    """
    target = (
        _coerce_chat_id(chat_id)
        if chat_id is not None
        else _coerce_chat_id(ENV.TELEGRAM_DEFAULT_CHAT_ID)
    )
    if target is None:
        logger.warning(
            "[Telegram] No chat_id (arg or TELEGRAM_DEFAULT_CHAT_ID). Skipping send."
        )
        return False
    client = build_client_from_env()
    # Use HTML + &lt;pre&gt; to avoid MarkdownV2 parse errors on decimals and punctuation.
    msg = format_watchlist_message_html(session, items, title=title)
    return client.smart_send(target, msg, mode="HTML", chunk_size=3500, retries=2)
