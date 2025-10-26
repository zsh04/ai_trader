from __future__ import annotations

from typing import Any, List
import sys
import types

# Provide stub for optional notifier module imported inside telegram_router.
if "app.adapters.notifiers.telegram_notifier" not in sys.modules:
    stub = types.ModuleType("app.adapters.notifiers.telegram_notifier")

    class TelegramNotifier:  # pragma: no cover - test helper
        ...

    stub.TelegramNotifier = TelegramNotifier
    sys.modules["app.adapters.notifiers.telegram_notifier"] = stub

from app.wiring import telegram_router as router


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: List[dict[str, Any]] = []

    def smart_send(
        self,
        chat_id: int,
        text: str,
        mode: str | None = None,
        chunk_size: int | None = None,
        retries: int | None = None,
    ) -> None:
        self.calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "mode": mode,
                "chunk_size": chunk_size,
                "retries": retries,
            }
        )


def test_cmd_summary_uses_latest_watchlist_meta(monkeypatch):
    router._watchlist_meta.update(
        {"count": 7, "session": "pre", "asof_utc": "2024-01-01T09:30:00Z"}
    )
    fake = FakeTelegram()

    router.cmd_summary(fake, chat_id=123, args=[])

    assert fake.calls, "Expected summary to send a Telegram message"
    call = fake.calls[0]
    assert call["chat_id"] == 123
    assert call["mode"] == "Markdown"
    assert call["chunk_size"] == 3500
    assert "Watchlist Summary" in call["text"]
    assert "Session: `pre`" in call["text"]
    assert "Symbols tracked: *7*" in call["text"]


def test_cmd_ping_replies(monkeypatch):
    fake = FakeTelegram()
    router.cmd_ping(fake, chat_id=9, args=[])
    assert fake.calls[0]["text"] == "pong ✅"


def test_cmd_help_lists_commands():
    fake = FakeTelegram()
    router.cmd_help(fake, chat_id=5, args=[])
    assert "/summary" in fake.calls[0]["text"]
    assert "/watchlist" in fake.calls[0]["text"]


def test_cmd_watchlist_uses_kv_flags(monkeypatch):
    router._watchlist_meta.update({"count": 0, "session": "regular", "asof_utc": None})

    build_calls = []

    def fake_build_watchlist(**kwargs):
        build_calls.append(kwargs)
        return {
            "items": [{"symbol": "AAPL", "last": 1.0, "price_source": "trade", "ohlcv": {}}],
            "session": "regular",
            "asof_utc": "2024-01-01T00:00:00Z",
        }

    monkeypatch.setattr(router, "build_watchlist", fake_build_watchlist)
    monkeypatch.setattr(router, "format_watchlist_message", lambda session, items, title: f"{title}:{len(items)}")

    fake = FakeTelegram()
    args = ["AAPL", "—limit=“2”", "--filters=false", '--title=“Edge”']

    router.cmd_watchlist(fake, chat_id=1, args=args)

    assert build_calls, "build_watchlist should be invoked"
    call = build_calls[0]
    assert call["limit"] == 2
    assert call["symbols"] == ["AAPL"]
    assert call["include_filters"] is False

    assert fake.calls[-1]["text"] == "Edge:1"
