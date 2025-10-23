# app/utils/telegram.py
import os, requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_message(text: str, parse_mode: str | None = "Markdown"):
    if not BOT_TOKEN or not CHAT_ID:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN/CHAT_ID missing"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text[:4096]}
    if parse_mode:
        data["parse_mode"] = parse_mode
        data["disable_web_page_preview"] = True
    r = requests.post(url, json=data, timeout=10)
    return {"ok": r.ok, "status": r.status_code, "resp": r.text[:500]}