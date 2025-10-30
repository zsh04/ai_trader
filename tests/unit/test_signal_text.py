import os
from importlib import reload
from app.sources.text import signal_text

def test_signal_text_parsing(monkeypatch):
    monkeypatch.delenv("SIGNAL_SAMPLE_SYMBOLS", raising=False)
    reload(signal_text)
    assert signal_text.get_symbols() == []

    monkeypatch.setenv("SIGNAL_SAMPLE_SYMBOLS", "aapl, msft, aapl, nvda")
    reload(signal_text)
    assert signal_text.get_symbols(max_symbols=2) == ["AAPL", "MSFT"]

    monkeypatch.setenv("SIGNAL_SAMPLE_SYMBOLS", "  tsla,oklo, Tsla , , oklo ")
    reload(signal_text)
    assert signal_text.get_symbols() == ["TSLA", "OKLO"]