"""Senate stock trades from the Senate eFD site (efdsearch.senate.gov).
HOBBY / NON-COMMERCIAL USE ONLY: this code clicks the site's "I understand the
prohibitions" agreement for you. That agreement bars commercial use of the reports."""
import datetime as dt, re, time
import requests
from bs4 import BeautifulSoup

BASE = "https://efdsearch.senate.gov"
HEADERS = {"User-Agent": "capitol-guide/0.1 (personal hobby project)"}
TICKER = re.compile(r"[A-Z][A-Z.\-]{0,5}")

def parse_ptr_html(html):
    rows = []
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(c) < 8 or "stock" not in c[5].lower() or not TICKER.fullmatch(c[3]):
            continue
        kind = c[6].lower()
        if not (kind.startswith("purchase") or kind.startswith("sale")):
            continue
        try:
            d = dt.datetime.strptime(c[1], "%m/%d/%Y")
        except ValueError:
            continue
        rows.append({"t": c[3], "side": "Buy" if kind.startswith("purchase") else "Sell",
                     "size": re.sub(r"\s*-\s*", "–", c[7]), "date": d.strftime("%b ") + str(d.day),
                     "iso": d.date().isoformat()})
    return rows

def parse_results(data):
    out = []
    for row in data:
        link = next((BeautifulSoup(x, "html.parser").find("a") for x in row if "<a" in x), None)
        if not link or "/ptr/" not in link.get("href", ""):
            continue
        name = f"{row[0].strip()} {row[1].strip()}"
        title = "Sen. " if any("senator" in x.lower() for x in row) else ""
        out.append((title + name, link["href"]))
    return out

def _session():
    s = requests.Session()
    s.headers.update(HEADERS)
    home = f"{BASE}/search/home/"
    r = s.get(home, timeout=60); r.raise_for_status()
    token = BeautifulSoup(r.text, "html.parser").find("input", {"name": "csrfmiddlewaretoken"})["value"]
    r = s.post(home, data={"prohibition_agreement": "1", "csrfmiddlewaretoken": token},
               headers={"Referer": home}, timeout=60)
    r.raise_for_status()
    return s

def fetch_senate(days=60, limit=80):
    s = _session()
    start_date = (dt.date.today() - dt.timedelta(days=days)).strftime("%m/%d/%Y") + " 00:00:00"
    results, start = [], 0
    while start < 300:
        r = s.post(f"{BASE}/search/report/data/", timeout=60,
                   headers={"Referer": f"{BASE}/search/", "X-CSRFToken": s.cookies.get("csrftoken", "")},
                   data={"start": str(start), "length": "100", "report_types": "[11]", "filer_types": "[]",
                         "submitted_start_date": start_date, "submitted_end_date": "",
                         "candidate_state": "", "senator_state": "", "office_id": "",
                         "first_name": "", "last_name": "",
                         "csrfmiddlewaretoken": s.cookies.get("csrftoken", "")})
        r.raise_for_status()
        page = r.json().get("data", [])
        results += parse_results(page)
        if len(page) < 100:
            break
        start += 100
    trades = []
    for who, href in results:
        try:
            page = s.get(BASE + href, timeout=60)
            page.raise_for_status()
            trades += [{**row, "who": who} for row in parse_ptr_html(page.text)]
        except Exception as e:
            print("skipped a Senate filing:", e)
        time.sleep(0.5)
        if len(trades) >= limit:
            break
    return trades[:limit]
