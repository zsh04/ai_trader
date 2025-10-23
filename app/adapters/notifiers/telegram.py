from __future__ import annotations
from typing import Optional, Set
import requests

class TelegramClient:
    def __init__(self, bot_token: str, allowed_users: Set[int], webhook_secret: str):
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.allowed = allowed_users
        self.secret = webhook_secret

    def is_allowed(self, chat_id: int) -> bool:
        return chat_id in self.allowed

    def verify_webhook(self, header_secret: Optional[str]) -> bool:
        return (header_secret or "") == self.secret

    def send_markdown(self, chat_id: int, text: str, disable_preview: bool = True) -> bool:
        url = f"{self.base}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": disable_preview
        }, timeout=10)
        return 200 <= resp.status_code < 300

    def send_long_markdown(self, chat_id: int, text: str, chunk_size: int = 3900) -> bool:
        ok = True
        for i in range(0, len(text), chunk_size):
            part = text[i:i+chunk_size]
            if not self.send_markdown(chat_id, part):
                ok = False
        return ok