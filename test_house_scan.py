import datetime as dt, io, shutil, zipfile
import pytest
from PIL import Image, ImageDraw, ImageFont
import pipeline

@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_fetch_house_ocrs_only_filings_without_text(monkeypatch, tmp_path):
    year = dt.date.today().year
    today = dt.date.today().strftime("%m/%d/%Y")
    xml = "<FinancialDisclosure>" + "".join(
        f"<Member><First>{n}</First><Last>X</Last><StateDst>OH02</StateDst><FilingType>P</FilingType>"
        f"<FilingDate>{today}</FilingDate><DocID>{d}</DocID></Member>" for n, d in [("Typed", "1"), ("Scanned", "2")]
    ) + "</FinancialDisclosure>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{year}FD.xml", xml)
    class R:
        content = buf.getvalue()
        def raise_for_status(self): pass
    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(pipeline, "CACHE", tmp_path)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    typed = lambda doc, yr: "Apple (AAPL) [ST] P 10/01/2026 10/05/2026 $1,001 - $15,000 F S: New"
    monkeypatch.setattr(pipeline, "pdf_text", lambda doc, yr: typed(doc, yr) if doc == "1" else "")
    img = Image.new("L", (2000, 200), 255)
    ImageDraw.Draw(img).text((40, 40), "Pfizer Inc. (PFE) [ST] S 10/02/2026 10/06/2026 $15,001 - $50,000", fill=0,
                             font=ImageFont.load_default(size=34))
    img.save(tmp_path / "2.pdf", "PDF", resolution=200)
    rows = pipeline.fetch_house(days=30, limit=50)
    by = {r["t"]: r for r in rows}
    assert set(by) == {"AAPL", "PFE"}
    assert "scan" not in by["AAPL"] and by["PFE"]["scan"] is True
