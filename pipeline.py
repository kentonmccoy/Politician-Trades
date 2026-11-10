"""Capitol Guide data pipeline.
Downloads recent House stock-trade filings (PTRs), measures unusual trading volume,
asks Claude for plain-English blurbs, and writes docs/data.json for the website."""
import datetime as dt, io, json, os, re, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

OUT, CACHE = Path("docs"), Path("cache")
MODEL = "claude-haiku-5-5"   # cheap and fast; change if you like
HOUSE = "https://disclosures-clerk.house.gov/public_disc"
HEADERS = {"User-Agent": "capitol-guide/0.1 (personal project)"}
WATCH = "AAPL MSFT NVDA TSLA AMZN GOOGL META AMD NFLX JPM XOM PFE LMT BA DIS COIN PLTR".split()
ROW = re.compile(r"\(([A-Z][A-Z.\-]{0,5})\)\s*\[ST\]\s+(P|S(?: \(partial\))?)\s+"
                 r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\$[\d,]+\s*-\s*\$[\d,]+|Over \$[\d,]+)")
PROMPT = ("You explain stocks to complete beginners. Reply with ONLY a JSON object with keys "
          "name, does, why, weigh. 'does': what the company does. 'why': general reasons a stock like "
          "this often has heavy trading (you have no live news, so never claim a specific cause today). "
          "'weigh': one honest risk or caution. Plain words, max 25 words per field. "
          "Never say to buy or sell. The user message is a ticker symbol.")

TICK = re.compile(r"\(([A-Z][A-Z.\-]{0,5})\)")
FIELDS = re.compile(r"\b(P|S(?: \(partial\))?)\s+(\d{2}/\d{2}/\d{4})\s+\d{2}/\d{2}/\d{4}\s+"
                    r"(\$[\d,]+\s*-\s*\$[\d,]+|Over \$[\d,]+)")

def _row(tk, kind, tdate, amt):
    d = dt.datetime.strptime(tdate, "%m/%d/%Y")
    return {"t": tk, "side": "Buy" if kind == "P" else "Sell",
            "size": re.sub(r"\s*-\s*", "–", amt), "date": d.strftime("%b ") + str(d.day),
            "iso": d.date().isoformat()}

def parse_ptr_text(text):
    """Pull stock transactions out of the text of one House PTR filing.
    Filings lay the columns out in different orders (the ticker can sit before or after the
    type, dates and amount, and the amount can be split by the ticker), so besides the plain
    pattern we also read each row on its own: rows end at the 'F S: New' marker."""
    text = re.sub(r"\s+", " ", text.replace("\x00", ""))
    rows, seen = [], set()
    def add(r):
        k = (r["t"], r["side"], r["iso"], r["size"])
        if k not in seen:
            seen.add(k); rows.append(r)
    for tk, kind, tdate, _notified, amt in ROW.findall(text):
        add(_row(tk, kind, tdate, amt))
    for chunk in re.split(r"\bF\s+S:\s*\w+", text):
        if chunk.count("[ST]") != 1 or len(re.findall(r"\[[A-Z]{2}\]", chunk)) != 1:
            continue
        before = chunk[:chunk.index("[ST]")]
        ticks = TICK.findall(before)
        if not ticks:
            continue
        clean = re.sub(r"\s+", " ", TICK.sub(" ", chunk).replace("[ST]", " "))
        found = FIELDS.findall(clean)
        if found:
            kind, tdate, amt = found[-1]
            add(_row(ticks[-1], kind[0], tdate, amt))
    return rows

def pdf_text(doc, year):
    import pdfplumber
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{doc}.pdf"
    if not f.exists():
        r = requests.get(f"{HOUSE}/ptr-pdfs/{year}/{doc}.pdf", headers=HEADERS, timeout=60)
        r.raise_for_status()
        f.write_bytes(r.content)
        time.sleep(0.5)  # be polite to the server
    with pdfplumber.open(f) as pdf:
        return " ".join((p.extract_text() or "") for p in pdf.pages)

def diagnose(text, rows, who):
    """Print how well the parser did on one filing, so gaps are visible in the run log."""
    flat = re.sub(r"\s+", " ", text)
    found = len(re.findall(r"\[ST\]", flat))
    if not flat.strip():
        return "no_text"          # usually a scanned/image PDF
    if found > len(rows):
        covered = [mm.span() for mm in ROW.finditer(flat)]
        # show the first stock line the parser did not match
        for m in re.finditer(r"\[ST\]", flat):
            if not any(a <= m.start() < b for a, b in covered):
                print(f"  MISSED in {who}: {flat[max(0, m.start() - 60): m.start() + 110]!r}")
                break
        return "partial"
    return "ok"

def fetch_house(days=60, limit=80):
    year = dt.date.today().year
    r = requests.get(f"{HOUSE}/financial-pdfs/{year}FD.zip", headers=HEADERS, timeout=120)
    r.raise_for_status()
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(r.content)).read(f"{year}FD.xml"))
    cutoff = dt.date.today() - dt.timedelta(days=days)
    filings = []
    for m in root.iter("Member"):
        if (m.findtext("FilingType") or "").strip() != "P":
            continue
        try:
            filed = dt.datetime.strptime(m.findtext("FilingDate").strip(), "%m/%d/%Y").date()
        except (ValueError, AttributeError):
            continue
        if filed >= cutoff:
            filings.append((filed, m))
    trades, stats = [], {"ok": 0, "partial": 0, "no_text": 0, "error": 0}
    print(f"House: {len(filings)} filings in the last {days} days")
    for filed, m in sorted(filings, key=lambda x: x[0], reverse=True):
        sd = re.match(r"([A-Z]{2})(\d+)", (m.findtext("StateDst") or "").strip())
        place = "" if not sd else f" ({sd.group(1)}-{int(sd.group(2))})" if int(sd.group(2)) else f" ({sd.group(1)})"
        who = f"Rep. {(m.findtext('First') or '').strip()} {(m.findtext('Last') or '').strip()}{place}"
        try:
            text = pdf_text(m.findtext("DocID").strip(), year)
            rows = parse_ptr_text(text)
        except Exception as e:
            stats["error"] += 1
            print("skipped a filing:", type(e).__name__, e); continue
        stats[diagnose(text, rows, who)] += 1
        trades += [{**row, "who": who} for row in rows]
        if len(trades) >= limit:
            break
    print("House filing results:", stats)
    return trades[:limit]

def volume_leaders(tickers):
    import yfinance as yf
    df = yf.download(sorted(tickers), period="3mo", progress=False, group_by="ticker", auto_adjust=True)
    res = []
    for tk in tickers:
        try:
            v = df[tk]["Volume"].dropna()
        except KeyError:
            continue
        if len(v) > 20:
            res.append({"t": tk, "x": round(float(v.iloc[-1] / v.iloc[-31:-1].mean()), 1)})
    return sorted(res, key=lambda r: -r["x"])[:8]

def blurbs(tickers):
    path = CACHE / "blurbs.json"
    have = json.loads(path.read_text()) if path.exists() else {}
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()
        for tk in [t for t in tickers if t not in have]:
            try:
                msg = client.messages.create(model=MODEL, max_tokens=400, system=PROMPT,
                                             messages=[{"role": "user", "content": tk}])
                have[tk] = json.loads(msg.content[0].text)
            except Exception as e:
                print("no blurb for", tk, e)
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(have, indent=1))
    fallback = {"does": "Details unavailable.", "why": "Heavy trading can follow news or earnings reports.",
                "weigh": "Single stocks are riskier than funds that hold many."}
    return {t: have.get(t) or {"name": t, **fallback} for t in tickers}

def main():
    from senate import fetch_senate
    try:
        senate = fetch_senate()
    except Exception as e:
        print("Senate failed:", e)
        senate = []
    seen, trades = set(), []
    for t in sorted(fetch_house() + senate, key=lambda t: t["iso"], reverse=True):
        key = (t["who"], t["t"], t["side"], t["size"], t["iso"])
        if key not in seen:
            seen.add(key)
            trades.append(t)
    trades = trades[:100]

    vol = volume_leaders(sorted({t["t"] for t in trades} | set(WATCH)))
    needed = {t["t"] for t in trades} | {v["t"] for v in vol}
    OUT.mkdir(exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(
        {"sample": False, "updated": dt.date.today().strftime("%b %d, %Y"),
         "trades": trades, "vol": vol, "stocks": blurbs(sorted(needed))}, indent=1))
    print(f"Wrote docs/data.json with {len(trades)} trades.")

if __name__ == "__main__":
    main()
