from pipeline import parse_ptr_text
def test_parse():
    t = "SP Apple Inc. (AAPL) [ST] P 01/15/2026 01/20/2026 $1,001 - $15,000  F S: New  Pfizer (PFE) [ST] S (partial) 02/03/2026 02/05/2026 $15,001 - $50,000 Some Bond (XYZ) [CS] P 01/01/2026 01/02/2026 $1,001 - $15,000"
    r = parse_ptr_text(t)
    assert [x["t"] for x in r] == ["AAPL", "PFE"]
    assert r[0]["side"] == "Buy" and r[1]["side"] == "Sell"
    assert r[0]["size"] == "$1,001–$15,000" and r[0]["date"] == "Jan 15"
