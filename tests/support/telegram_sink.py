from __future__ import annotations

from typing import Any, Dict, List

_FAKE_TG_SINK: List[Dict[str, Any]] = []
_HTTP_OUTBOX: List[Dict[str, Any]] = []


def sink_clear() -> None:
    """Clear all captured Telegram messages."""
    _FAKE_TG_SINK.clear()


def sink_snapshot() -> List[Dict[str, Any]]:
    """Return a shallow copy of the captured Telegram sink."""
    return list(_FAKE_TG_SINK)


def sink_append(chat_id: int | str, text: str, parse_mode: str | None) -> None:
    """Add a message to the sink."""
    _FAKE_TG_SINK.append(
        {
            "chat_id": chat_id,
            "text": text or "",
            "parse_mode": parse_mode,
        }
    )


def http_append(chat_id: int | str, text: str, parse_mode: str | None) -> None:
    """Record a Telegram HTTP payload (e.g., via requests.post)."""
    _HTTP_OUTBOX.append(
        {
            "chat_id": chat_id,
            "text": text or "",
            "parse_mode": parse_mode,
        }
    )


def http_clear() -> None:
    """Clear captured HTTP payloads."""
    _HTTP_OUTBOX.clear()


def merged_outbox(adapter_messages: List[Dict[str, Any]]) -> List[str]:
    """Aggregate sink, adapter, and HTTP payloads into a unified list of messages."""
    sink_msgs = [m.get("text", "") for m in _FAKE_TG_SINK]
    adapter_msgs = [m.get("text", "") for m in adapter_messages]
    http_msgs = [m.get("text", "") for m in _HTTP_OUTBOX]
    return sink_msgs + adapter_msgs + http_msgs


__all__ = [
    "sink_clear",
    "sink_snapshot",
    "sink_append",
    "http_append",
    "http_clear",
    "merged_outbox",
]
