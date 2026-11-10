from pipeline import parse_ptr_text
def test_parse():
    t = "SP Apple Inc. (AAPL) [ST] P 01/15/2026 01/20/2026 $1,001 - $15,000  F S: New  Pfizer (PFE) [ST] S (partial) 02/03/2026 02/05/2026 $15,001 - $50,000 Some Bond (XYZ) [CS] P 01/01/2026 01/02/2026 $1,001 - $15,000"
    r = parse_ptr_text(t)
    assert [x["t"] for x in r] == ["AAPL", "PFE"]
    assert r[0]["side"] == "Buy" and r[1]["side"] == "Sell"
    assert r[0]["size"] == "$1,001–$15,000" and r[0]["date"] == "Jan 15"

N = "\x00" * 5
def test_other_column_orders():
    # Real layouts seen in the House filings: type/dates/amount before the ticker, or the amount split by it.
    t = (f"Fidelity Retail Account A Common Stock (WBD) [ST] S 10/07/2026 10/12/2026 $1,001 - $15,000 F{N} S{N}: New "
         f"S{N} O{N}: Fidelity Retail Account * For the complete list of asset type abbreviations "
         f"SP Alphabet Common Stock (AAPL) P 08/13/2026 08/14/2026 $1,001 - $15,000 [ST] F{N} S{N}: New O{N}: Morgan Stanley "
         f"Trust One SP Abbott Laboratories Common Stock S 10/02/2026 10/05/2026 $50,001 - (ABT) [ST] $100,000 F{N} S{N}: New "
         f"Nvidia Stock S (partial) 09/25/2026 10/14/2026 $1,001 - $15,000 (NVDA) [ST] F{N} S{N}: New")
    r = parse_ptr_text(t)
    assert [(x["t"], x["side"], x["size"], x["iso"]) for x in r] == [
        ("WBD", "Sell", "$1,001–$15,000", "2026-10-07"),
        ("AAPL", "Buy", "$1,001–$15,000", "2026-08-13"),
        ("ABT", "Sell", "$50,001–$100,000", "2026-10-02"),
        ("NVDA", "Sell", "$1,001–$15,000", "2026-09-25")]
