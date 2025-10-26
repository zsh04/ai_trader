from app.sources import dedupe_merge

def test_merge_order():
    res = dedupe_merge(["AAPL", "TSLA"], ["tsla", "MSFT"])
    assert res == ["AAPL", "TSLA", "MSFT"]