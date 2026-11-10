import shutil
import pytest
from PIL import Image, ImageDraw, ImageFont
from pipeline import fix_ocr, ocr_text, parse_ptr_text

def test_fix_ocr():
    assert fix_ocr("Apple (AAPL) (ST] P 10/01/2026 10/05/2026 $1,001 – $15,000") == \
        "Apple (AAPL) [ST] P 10/01/2026 10/05/2026 $1,001 - $15,000"
    assert "[ST]" in fix_ocr("Tesla (TSLA) [S T] S 10/01/2026")

@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_scanned_pdf_is_read(tmp_path):
    lines = ["SP Apple Inc. - Common Stock (AAPL) [ST] P 10/01/2026 10/05/2026 $1,001 - $15,000",
             "F S: New",
             "Pfizer Inc. - Common Stock (PFE) [ST] S 10/02/2026 10/06/2026 $15,001 - $50,000",
             "F S: New"]
    img = Image.new("L", (2000, 400), 255)
    d = ImageDraw.Draw(img); font = ImageFont.load_default(size=34)
    for i, line in enumerate(lines):
        d.text((40, 40 + i * 80), line, fill=0, font=font)
    f = tmp_path / "scan.pdf"
    img.save(f, "PDF", resolution=200)           # image only: no text layer, like a real scan
    rows = parse_ptr_text(ocr_text(f))
    assert [(r["t"], r["side"], r["size"], r["iso"]) for r in rows] == [
        ("AAPL", "Buy", "$1,001–$15,000", "2026-10-01"), ("PFE", "Sell", "$15,001–$50,000", "2026-10-02")]
