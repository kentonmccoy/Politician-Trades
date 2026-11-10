import json
import run

def tr(t, side, who, size="$1,001–$15,000", iso="2026-10-20"):
    return {"t": t, "side": side, "size": size, "who": who, "iso": iso, "date": "Oct 20"}

def test_hot_ranks_more_buyers_first():
    trades = [tr("ONE", "Buy", "A", "$50,001–$100,000"), tr("TWO", "Buy", "A"), tr("TWO", "Buy", "B"),
              tr("SOLD", "Buy", "A"), tr("SOLD", "Sell", "B", "$15,001–$50,000")]
    hot = run.hot_stocks(trades)
    assert [h["t"] for h in hot] == ["TWO", "ONE"]
    assert hot[0]["buyers"] == 2 and hot[0]["sellers"] == 0

def test_main_end_to_end(monkeypatch, tmp_path):
    trades = [tr("NOKBF", "Buy", "A"), tr("DIS", "Buy", "A"), tr("DIS", "Buy", "B"),
              tr("PG", "Buy", "C"), tr("PG", "Buy", "C")]  # PG twice: same person, same trade -> one row
    seen = {}
    monkeypatch.setattr(run, "OUT", tmp_path / "docs")
    monkeypatch.setattr(run, "fetch_house", lambda days, limit: seen.update(house=(days, limit)) or trades)
    monkeypatch.setattr(run, "fetch_senate", lambda days: seen.update(senate=days) or [])
    monkeypatch.setattr(run, "volume_both", lambda tickers: ([{"t": "DIS", "x": 2.0}], [{"t": "DIS", "x": 1.5}]))
    monkeypatch.setattr(run, "company_info", lambda ts: {
        "NOKBF": {"name": "Nokia Oyj", "exchange": "PNK"},
        "DIS": {"name": "Walt Disney Co", "exchange": "NYQ"},
        "PG": {"name": "Procter & Gamble Co", "exchange": "NYQ"}})
    monkeypatch.setattr(run, "fetch_news", lambda ts: {})
    monkeypatch.setattr(run, "news_blurbs", lambda ts, news: {
        t: {"name": "AI Name" if t == "PG" else t, "does": "Details unavailable.", "why": "x", "weigh": "y"} for t in ts})
    run.main()
    d = json.loads((tmp_path / "docs" / "data.json").read_text())
    assert seen["house"] == (90, 400) and seen["senate"] == 90 and d["window_days"] == 90
    assert [h["t"] for h in d["hot"]] == ["DIS", "PG"]            # NOKBF (over the counter) dropped
    assert d["stocks"]["DIS"]["name"] == "Walt Disney Co"         # Yahoo name fills the gap
    assert d["stocks"]["PG"]["name"] == "AI Name"                 # AI name wins when present
    assert len([t for t in d["trades"] if t["t"] == "PG"]) == 1   # duplicates removed
