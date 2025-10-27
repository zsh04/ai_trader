# debug_webhook_call.py
import os
from dotenv import load_dotenv
from starlette.testclient import TestClient

# Load .env and force bypass ON to match test’s expectation
load_dotenv(override=True)
os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")

import app.main as main_module  # noqa: E402

client = TestClient(main_module.app)

payload = {"message": {"chat": {"id": 1}, "text": "/ping"}}

resp = client.post(
    "/telegram/webhook",
    json=payload,
    headers={
        # Try empty header to use bypass
        #"X-Telegram-Bot-Api-Secret-Token": "",
        # Or uncomment to test secret path:
        "X-Telegram-Bot-Api-Secret-Token": os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
    },
)

print("status:", resp.status_code)
print("body  :", resp.text)