"""Senate stock trades from Bargo's free Congress API (https://www.bargo.ai/free-apis/congress).
Non-commercial hobby use. Bargo requires a visible credit link on the page, and the page adds one."""
import datetime as dt, os, re, time
import requests

URL = "https://www.bargo.ai/free-apis/congress/v1/trades"
HEADERS = {"User-Agent": "capitol-guide/0.2 (personal hobby project)"}
PAGE = 100  # largest page that works without a key

def clean_name(name, state):
    n = re.sub(r"^(hon\.?|sen\.?|senator|rep\.?)\s+", "", (name or "").strip(), flags=re.I).strip()
    return f"Sen. {n} ({state})" if state else f"Sen. {n}"

def convert(row):
    """One Bargo row -> one trade in the site's format, or None if it isn't a stock buy/sell."""
    tk = (row.get("ticker") or "").strip().upper()
    kind = (row.get("type") or "").strip().lower()
    if (row.get("chamber") or "").lower() != "senate" or not re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", tk):
        return None
    if kind.startswith("purchase"):
        side = "Buy"
    elif kind.startswith("sale") or kind.startswith("sell"):
        side = "Sell"
    else:
        return None
    try:
        d = dt.datetime.strptime(row["transaction_date"][:10], "%Y-%m-%d")
    except (KeyError, TypeError, ValueError):
        return None
    amt = (row.get("amount_range") or "").strip()
    if not amt or not row.get("member"):
        return None
    return {"t": tk, "side": side, "size": re.sub(r"\s*-\s*", "–", amt),
            "date": d.strftime("%b ") + str(d.day), "iso": d.date().isoformat(),
            "who": clean_name(row["member"], row.get("state"))}

def fetch_senate(days=60, pages=3):
    key = os.environ.get("BARGO_API_KEY", "").strip()
    # The docs I could see don't say how to send the key, so try the common ways in turn.
    tries = [({"Authorization": "Bearer " + key, "X-API-Key": key}, {}), ({}, {"token": key}), ({}, {})] if key else [({}, {})]
    labels = ["key in header", "key in link", "no key (lower daily limits)"] if key else ["no key (lower daily limits)"]
    i, out = 0, []
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    for page in range(pages):
        params = {"chamber": "senate", "from": since, "limit": PAGE, "page": page}
        try:
            while True:
                hdr, extra = tries[i]
                r = requests.get(URL, params={**params, **extra}, headers={**HEADERS, **hdr}, timeout=30)
                if r.status_code in (401, 403) and i < len(tries) - 1:
                    i += 1
                    continue
                break
            if r.status_code == 429:
                print("Bargo daily limit reached; keeping what was loaded.")
                break
            r.raise_for_status()
            rows = r.json().get("trades", [])
        except Exception as e:
            print("Bargo stopped:", type(e).__name__)
            break
        out += [t for t in map(convert, rows) if t]
        if len(rows) < PAGE:
            break
        time.sleep(1)
    print(f"Bargo: {len(out)} Senate trades ({labels[i]}).")
    return out
