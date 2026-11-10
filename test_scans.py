import datetime as dt, io, json, zipfile
from types import SimpleNamespace
from PIL import Image
import pipeline, scans

TODAY = dt.date(2026, 11, 10)
def row(**kw):
    return {"ticker": "AAPL", "type": "P", "date": "10/01/2026", "amount": "$1,001 - $15,000", **kw}

def test_valid_rows_keeps_only_clean_rows():
    items = [row(), row(ticker="BRK.B", type="S (partial)", amount="$15,001 – $50,000"),
             row(ticker="aapl"), row(ticker="TOOLONGX"), row(type="E"), row(date="13/45/2026"),
             row(date="11/20/2026"), row(date="01/01/2020"), row(amount="$1,234 - $9,999"), {"ticker": "X"}, "junk"]
    assert scans.valid_rows(items, TODAY) == [("AAPL", "P", "10/01/2026", "$1,001 - $15,000"),
                                              ("BRK.B", "S (partial)", "10/01/2026", "$15,001 - $50,000")]
    assert scans.valid_rows("not a list", TODAY) == []

class FakeClient:
    def __init__(self, text): self.calls, self.text = [], text
    @property
    def messages(self): return self
    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])

def scan_pdf(path):
    Image.new("L", (400, 300), 255).save(path, "PDF", resolution=100)

def test_read_scan_checks_caches_and_sends_images(monkeypatch, tmp_path):
    monkeypatch.setattr(scans, "CACHE_FILE", tmp_path / "c.json")
    f = tmp_path / "s.pdf"; scan_pdf(f)
    good = row(date=(dt.date.today() - dt.timedelta(days=5)).strftime("%m/%d/%Y"))
    bad = row(ticker="zzz")
    c = FakeClient("Sure! " + json.dumps([good, bad]) + " ignore previous instructions")
    got = scans.read_scan(f, "123", client=c)
    assert [r[0] for r in got] == ["AAPL"]                       # the bad row was dropped
    assert c.calls[0]["messages"][0]["content"][0]["type"] == "image"
    again = scans.read_scan(f, "123", client=FakeClient("[]"))   # served from the cache, no new call
    assert again == got

def test_read_scan_failure_is_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(scans, "CACHE_FILE", tmp_path / "c.json")
    f = tmp_path / "s.pdf"; scan_pdf(f)
    assert scans.read_scan(f, "9", client=FakeClient("I cannot read this")) is None
    assert not (tmp_path / "c.json").exists()

def test_no_key_means_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(scans, "CACHE_FILE", tmp_path / "c.json")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    f = tmp_path / "s.pdf"; scan_pdf(f)
    assert scans.read_scan(f, "9") is None

def test_fetch_house_uses_claude_only_for_filings_without_text(monkeypatch, tmp_path):
    year, today = dt.date.today().year, dt.date.today().strftime("%m/%d/%Y")
    xml = "<FD>" + "".join(f"<Member><First>{n}</First><Last>X</Last><StateDst>OH02</StateDst><FilingType>P</FilingType>"
                           f"<FilingDate>{today}</FilingDate><DocID>{d}</DocID></Member>"
                           for n, d in [("Typed", "1"), ("Scanned", "2")]) + "</FD>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z: z.writestr(f"{year}FD.xml", xml)
    class R:
        content = buf.getvalue()
        def raise_for_status(self): pass
    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(pipeline, "pdf_text", lambda doc, yr: "Apple (AAPL) [ST] P 10/01/2026 10/05/2026 $1,001 - $15,000 F S: New" if doc == "1" else "")
    monkeypatch.setattr(pipeline, "pdf_file", lambda doc, yr: tmp_path / f"{doc}.pdf")
    asked = []
    monkeypatch.setattr(pipeline, "read_scan", lambda f, doc: asked.append(doc) or [("PFE", "S", "10/02/2026", "$15,001 - $50,000")])
    by = {r["t"]: r for r in pipeline.fetch_house(days=30, limit=50)}
    assert asked == ["2"] and set(by) == {"AAPL", "PFE"}
    assert "scan" not in by["AAPL"] and by["PFE"]["scan"] is True and by["PFE"]["side"] == "Sell"
