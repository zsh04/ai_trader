# tests/unit/test_watchlist_utils.py
from app.domain.watchlist_utils import normalize_symbols

def test_normalize_symbols_basic():
    raw = [" aapl ", "msft", "AAPL", "", " nvda", "nvda ", "  spy "]
    out = normalize_symbols(raw)
    assert out == ["AAPL", "MSFT", "NVDA", "SPY"]

def test_normalize_symbols_all_empty():
    assert normalize_symbols([" ", "", "   "]) == []