from __future__ import annotations

from app.utils.normalize import normalize_quotes_and_dashes, parse_kv_flags


def test_normalize_quotes_and_dashes_mobile_text():
    raw = "“AI”—said ‘Trader’ — let’s go!"
    normalized = normalize_quotes_and_dashes(raw)
    assert normalized == '"AI"--said \'Trader\' -- let\'s go!'


def test_parse_kv_flags_with_smart_quotes():
    raw = '--title=“AI Trader” --mode=‘fast’ --limit=15 --note="ready"'
    flags = parse_kv_flags(raw)
    assert flags == {
        "title": "AI Trader",
        "mode": "fast",
        "limit": "15",
        "note": "ready",
    }
