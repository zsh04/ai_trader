from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, Optional, Set, List

import requests
from loguru import logger

from app.utils import env as ENV

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

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            parse_mode (Optional[str]): The parse mode for the message.
            mode (Optional[str]): The parse mode for the message.
            chunk_size (int): The maximum chunk size.
            retries (int): The number of retries.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        for part in _split_chunks(text, limit=chunk_size):
            _TEST_OUTBOX.append(
                {
                    "chat_id": chat_id,
                    "text": part,
                    "parse_mode": parse_mode or mode or "Markdown",
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
        timeout: int = 10,
    ) -> None:
        """
        Initializes the TelegramClient.

        Args:
            bot_token (str): The Telegram bot token.
            allowed_users (Set[int] | None): A set of allowed user IDs.
            webhook_secret (str | None): The webhook secret.
            timeout (int): The request timeout.
        """
        self.base = f"{API_BASE}/bot{bot_token}" if bot_token else ""
        self.allowed = allowed_users or set()
        self.secret = webhook_secret or ""
        self.timeout = timeout

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
        parse_mode: Optional[str] = "Markdown",
        disable_preview: bool = True,
    ) -> bool:
        """
        Sends a text message.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            parse_mode (Optional[str]): The parse mode for the message.
            disable_preview (bool): Whether to disable the link preview.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        return self._send(
            chat_id, text, parse_mode=parse_mode, disable_preview=disable_preview
        )

    def send_markdown(
        self, chat_id: int | str, text: str, disable_preview: bool = True
    ) -> bool:
        """
        Sends a Markdown message.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            disable_preview (bool): Whether to disable the link preview.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        return self._send(
            chat_id, text, parse_mode="Markdown", disable_preview=disable_preview
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
        url = f"{self.base}/sendDocument"
        try:
            with open(file_path, "rb") as doc:
                files = {"document": doc}
                data: Dict[str, Any] = {"chat_id": _coerce_chat_id(chat_id)}
                if caption:
                    data["caption"] = caption
                resp = requests.post(
                    url, data=data, files=files, timeout=self.timeout
                )
            if 200 <= resp.status_code < 300:
                logger.info(
                    "[Telegram] Document sent to {}: {}", chat_id, file_path
                )
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
        retries: int = 2,
        **_ignore,
    ) -> bool:
        """
        Sends a long message in chunks.

        Args:
            chat_id (int | str): The chat ID to send the message to.
            text (str): The message text.
            parse_mode (Optional[str]): The parse mode for the message.
            mode (Optional[str]): The parse mode for the message.
            chunk_size (int): The maximum chunk size.
            retries (int): The number of retries.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        eff_mode = parse_mode or mode or "Markdown"
        ok = True
        for part in _split_chunks(text, limit=chunk_size):
            for attempt in range(retries + 1):
                if self._send(chat_id, part, parse_mode=eff_mode):
                    break
                if attempt < retries:
                    delay = 1.5 * (attempt + 1)
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
        url = f"{self.base}/getMe"
        try:
            resp = requests.get(url, timeout=self.timeout)
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
                logger.debug(
                    "[Telegram] Sent {} chars to {}", len(text), chat_id
                )
                return True
            if resp.status_code == 429:
                try:
                    retry_after = int(resp.headers.get("Retry-After", "2"))
                except Exception:
                    retry_after = 2
                logger.warning(
                    "[Telegram] Rate-limited (429). Sleeping {}s", retry_after
                )
                time.sleep(retry_after)
                return False
            logger.warning("[Telegram] HTTP {}: {}", resp.status_code, resp.text)
        except Exception as e:
            logger.error("[Telegram] Send error: {}", e)
        return False


def build_client_from_env() -> TelegramClient | FakeTelegramClient:
    """
    Builds a Telegram client from environment variables.

    Returns:
        TelegramClient | FakeTelegramClient: A Telegram client.
    """
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TELEGRAM_FAKE") == "1":
        logger.debug("[Telegram] Using FakeTelegramClient (test mode)")
        return FakeTelegramClient()

    token = ENV.TELEGRAM_BOT_TOKEN
    allowed = ENV.TELEGRAM_ALLOWED_USER_IDS
    secret = ENV.TELEGRAM_WEBHOOK_SECRET
    timeout = ENV.TELEGRAM_TIMEOUT_SECS

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
    )


def format_watchlist_message(
    session: str, items: Iterable[dict], title: str = "AI Trader • Watchlist"
) -> str:
    """
    Formats a watchlist message.

    Args:
        session (str): The trading session.
        items (Iterable[dict]): A list of watchlist items.
        title (str): The message title.

    Returns:
        str: The formatted message.
    """
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
    msg = format_watchlist_message(session, items, title=title)
    return client.smart_send(target, msg, mode="Markdown", chunk_size=3500, retries=2)
