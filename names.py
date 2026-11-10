"""Company names for tickers, from Yahoo Finance via yfinance (no AI needed)."""

# Over-the-counter markets, where foreign shares like NOKBF trade.
OTC = {"PNK", "OQB", "OQX", "OTC", "OEM"}

def tidy(name):
    n = " ".join((name or "").split())
    if n.isupper():
        n = n.title()
    return n[:60]

def company_info(tickers):
    """{ticker: {"name": ..., "exchange": ...}} for the tickers Yahoo knows. Never raises."""
    try:
        import yfinance as yf
    except Exception:
        return {}
    out, misses = {}, 0
    for tk in tickers:
        try:
            info = yf.Ticker(tk.replace(".", "-")).info or {}
            name = tidy(info.get("shortName") or info.get("longName"))
            if not name:
                raise ValueError("no name")
            out[tk] = {"name": name, "exchange": info.get("exchange")}
            misses = 0
        except Exception as e:
            misses += 1
            print("no company name for", tk, type(e).__name__)
            if misses >= 8:  # Yahoo is probably refusing us; stop instead of waiting on every ticker
                print("Too many misses, skipping the rest of the company names.")
                break
    return out
