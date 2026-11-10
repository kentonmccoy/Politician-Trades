"""Capitol Guide data pipeline.
Downloads recent House stock-trade filings (PTRs), measures unusual trading volume,
asks Claude for plain-English blurbs, and writes docs/data.json for the website."""
import datetime as dt, io, json, os, re, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from scans import read_scan

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
TAG = re.compile(r"\[[A-Z]{2}\]")
AMT = r"\$[\d,]+\s*-\s*[^$]{0,80}?\$[\d,]+|Over \$[\d,]+|\$[\d,]+\.\d\d"
FIELDS = re.compile(r"\b(P|S(?: \(partial\))?)\s+(\d{2}/\d{2}/\d{4})\s+\d{2}/\d{2}/\d{4}\s+(" + AMT + ")")

def _row(tk, kind, tdate, amt):
    d = dt.datetime.strptime(tdate, "%m/%d/%Y")
    m = re.findall(r"\$[\d,]+(?:\.\d\d)?", amt)
    size = f"{m[0]}–{m[-1]}" if len(m) > 1 else (m[0] if m else amt)
    return {"t": tk, "side": "Buy" if kind == "P" else "Sell", "size": size,
            "date": d.strftime("%b ") + str(d.day), "iso": d.date().isoformat()}

def parse_ptr_text(text, misses=None):
    """Pull stock transactions out of the text of one House PTR filing.
    Filings lay the columns out in different orders (the ticker can sit before or after the
    type, dates and amount, and the amount can be split by the ticker or asset name), so besides
    the plain pattern we read each [ST] row on its own. Lines we could not read go in `misses`."""
    text = re.sub(r"\s+", " ", text.replace("\x00", ""))
    rows, seen = [], set()
    def add(r):
        k = (r["t"], r["side"], r["iso"], r["size"])
        if k not in seen:
            seen.add(k); rows.append(r)
    for tk, kind, tdate, _notified, amt in ROW.findall(text):
        add(_row(tk, kind, tdate, amt))
    prev = 0
    for m in TAG.finditer(text):
        start, prev = prev, m.end()
        ends = list(re.finditer(r"\bF\s+S:\s*\w+", text[start:m.start()]))
        if ends:
            start += ends[-1].end()   # a row's fields never start before the previous row's end marker
        region = text[start:m.end() + 20]
        if m.group() != "[ST]":
            continue
        ticks = TICK.findall(text[start:m.start()])
        clean = re.sub(r"\s+", " ", TICK.sub(" ", region).replace("[ST]", " "))
        found = FIELDS.findall(clean)
        if ticks and found:
            kind, tdate, amt = found[-1]
            add(_row(ticks[-1], kind[0], tdate, amt))
        elif misses is not None and not any(r["t"] in text[start:m.end()] for r in rows):
            misses.append(text[max(0, m.start() - 120): m.end() + 60])
    return rows

def pdf_file(doc, year):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{doc}.pdf"
    if not f.exists():
        r = requests.get(f"{HOUSE}/ptr-pdfs/{year}/{doc}.pdf", headers=HEADERS, timeout=60)
        r.raise_for_status()
        f.write_bytes(r.content)
        time.sleep(0.5)  # be polite to the server
    return f

def pdf_text(doc, year):
    import pdfplumber
    with pdfplumber.open(pdf_file(doc, year)) as pdf:
        return " ".join((p.extract_text() or "") for p in pdf.pages)

def diagnose(text, rows, who, misses):
    """Say how well the parser did on one filing, so gaps are visible in the run log."""
    flat = re.sub(r"\s+", " ", text.replace("\x00", ""))
    if not flat.strip():
        return "no_text"          # usually a scanned/image PDF
    if misses:
        print(f"  MISSED in {who}: {misses[0]!r}")
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
    trades, stats = [], {"ok": 0, "partial": 0, "no_text": 0, "error": 0, "scan_read": 0, "scan_empty": 0, "scan_failed": 0}
    print(f"House: {len(filings)} filings in the last {days} days")
    for filed, m in sorted(filings, key=lambda x: x[0], reverse=True):
        sd = re.match(r"([A-Z]{2})(\d+)", (m.findtext("StateDst") or "").strip())
        place = "" if not sd else f" ({sd.group(1)}-{int(sd.group(2))})" if int(sd.group(2)) else f" ({sd.group(1)})"
        who = f"Rep. {(m.findtext('First') or '').strip()} {(m.findtext('Last') or '').strip()}{place}"
        try:
            doc = m.findtext("DocID").strip()
            text = pdf_text(doc, year)
            misses, scan = [], not text.strip()
            if scan:                      # image-only filing: have Claude read the page images
                got = read_scan(pdf_file(doc, year), doc)
                rows = [{**_row(tk, k[0], d, a), "scan": True} for tk, k, d, a in (got or [])]
                status = "scan_failed" if got is None else "scan_read" if rows else "scan_empty"
            else:
                rows = parse_ptr_text(text, misses)
        except Exception as e:
            stats["error"] += 1
            print("skipped a filing:", type(e).__name__, e); continue
        if scan:
            stats[status] += 1
            print(f"  SCAN {who}: {status.replace('_', ' ')} ({len(rows)} rows)")
        else:
            stats[diagnose(text, rows, who, misses)] += 1
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
