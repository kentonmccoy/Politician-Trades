"""Builds docs/data.json: recent House and Senate trades, busy stocks (latest day + past month),
a ranking of stocks politicians are net buying, plus headlines and plain-English notes."""
import datetime as dt, json, re
from pipeline import OUT, WATCH, fetch_house
from news import fetch_news, news_blurbs
from bargo import fetch_senate
from names import company_info, OTC

WINDOW = 90  # days of trades to look at

def dollars(size):
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", size)]
    return sum(nums) / len(nums) if nums else 0

def hot_stocks(trades, top=10):
    stats = {}
    for t in trades:
        s = stats.setdefault(t["t"], {"buyers": set(), "sellers": set(), "buy": 0, "sell": 0})
        if t["side"] == "Buy":
            s["buyers"].add(t["who"]); s["buy"] += dollars(t["size"])
        else:
            s["sellers"].add(t["who"]); s["sell"] += dollars(t["size"])
    rows = [{"t": k, "buyers": len(v["buyers"]), "sellers": len(v["sellers"]),
             "buy": round(v["buy"]), "sell": round(v["sell"])} for k, v in stats.items()
            if v["buy"] > v["sell"]]
    rows.sort(key=lambda r: (r["buyers"] - r["sellers"], r["buy"] - r["sell"]), reverse=True)
    return rows[:top]

def volume_both(tickers):
    import yfinance as yf
    df = yf.download(sorted(tickers), period="6mo", progress=False, group_by="ticker", auto_adjust=True)
    day, month = [], []
    for tk in tickers:
        try:
            v = df[tk]["Volume"].dropna()
        except KeyError:
            continue
        if len(v) < 90:
            continue
        day.append({"t": tk, "x": round(float(v.iloc[-1] / v.iloc[-31:-1].mean()), 1)})
        month.append({"t": tk, "x": round(float(v.iloc[-21:].mean() / v.iloc[-84:-21].mean()), 1)})
    top = lambda rows: sorted(rows, key=lambda r: -r["x"])[:8]
    return top(day), top(month)

def main():
    seen, trades = set(), []
    try:
        senate = fetch_senate(days=WINDOW)
    except Exception as e:
        print("Senate failed:", type(e).__name__)
        senate = []
    for t in sorted(fetch_house(days=WINDOW, limit=400) + senate, key=lambda t: t["iso"], reverse=True):
        key = (t["who"], t["t"], t["side"], t["size"], t["iso"])
        if key not in seen:
            seen.add(key)
            trades.append(t)
    day, month = volume_both(sorted({t["t"] for t in trades} | set(WATCH)))
    hot_all = hot_stocks(trades, top=30)
    shown = trades[:100]
    candidates = sorted({t["t"] for t in shown} | {v["t"] for v in day + month} | {h["t"] for h in hot_all})
    info = company_info(candidates)
    # Drop over-the-counter foreign shares (like NOKBF) from the Hot list; keep a stock if Yahoo doesn't know it.
    hot = [h for h in hot_all if info.get(h["t"], {}).get("exchange") not in OTC][:10]
    tickers = sorted({t["t"] for t in shown} | {v["t"] for v in day + month} | {h["t"] for h in hot})
    news = fetch_news(tickers)
    stocks = news_blurbs(tickers, news)
    for tk, s in stocks.items():  # use Yahoo's company name when the AI notes aren't on
        if s.get("name") in (None, "", tk) and tk in info:
            s["name"] = info[tk]["name"]
    OUT.mkdir(exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(
        {"sample": False, "updated": dt.date.today().strftime("%b %d, %Y"), "window_days": WINDOW,
         "trades": shown, "hot": hot, "vol": day, "vol_month": month, "news": news,
         "stocks": stocks}, indent=1))
    print(f"Wrote docs/data.json: {len(shown)} trades, {len(hot)} hot stocks, headlines for {len(news)} tickers.")

if __name__ == "__main__":
    main()
