import sys, types
import names

def test_tidy():
    assert names.tidy("WALT DISNEY CO") == "Walt Disney Co"
    assert names.tidy("  Apple   Inc. ") == "Apple Inc."
    assert names.tidy(None) == ""
    assert len(names.tidy("x" * 100)) == 60

def fake_yf(table):
    class T:
        def __init__(self, tk): self.tk = tk
        @property
        def info(self):
            if self.tk not in table: raise RuntimeError("nope")
            return table[self.tk]
    return types.SimpleNamespace(Ticker=T)

def test_company_info(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf({
        "DIS": {"shortName": "WALT DISNEY CO", "exchange": "NYQ"},
        "NOKBF": {"longName": "Nokia Oyj", "exchange": "PNK"}}))
    out = names.company_info(["DIS", "NOKBF", "ZZZZ"])
    assert out == {"DIS": {"name": "Walt Disney Co", "exchange": "NYQ"},
                   "NOKBF": {"name": "Nokia Oyj", "exchange": "PNK"}}
    assert "PNK" in names.OTC

def test_gives_up_after_many_misses(monkeypatch):
    seen = []
    class T:
        def __init__(self, tk): seen.append(tk)
        @property
        def info(self): raise RuntimeError("blocked")
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=T))
    assert names.company_info([f"T{i}" for i in range(20)]) == {}
    assert len(seen) == 8
