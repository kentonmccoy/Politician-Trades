# Capitol Guide

Plain-English guide to politicians' disclosed stock trades. `pipeline.py` builds `docs/data.json`; `docs/index.html` shows it.

## 1. See it work (no accounts needed)
1. Install Python 3.10+ from python.org.
2. In a terminal inside this folder: `python -m http.server -d docs 8000`
3. Open http://localhost:8000 (shows sample data).

## 2. Run it on real data
1. `pip install -r requirements.txt`
2. Optional, for AI blurbs: get a key at console.anthropic.com and run `export ANTHROPIC_API_KEY=your-key` (Windows: `set ANTHROPIC_API_KEY=your-key`). Without it you get generic blurbs.
3. `python pipeline.py`, then reload the page.

## 3. Put it online and refresh daily (free)
1. Create a GitHub repo and upload this folder.
2. Settings > Pages: deploy from branch `main`, folder `/docs`.
3. Settings > Secrets > Actions: add `ANTHROPIC_API_KEY`.
4. The workflow in `.github/workflows` refreshes the data every weekday.

## Known limits
- House filings only so far; Senate comes next.
- The House file formats were written from their documented layout and have not been tested against live data yet. If the run prints "skipped a filing" or finds 0 trades, that is the first thing to fix (Claude Code can help).
- Volume leaders come from a fixed watchlist plus stocks politicians traded, not the whole market.
- AI blurbs have no live news, so "why it may be active" is general, not a claim about today.
- Disclosures lag by up to 45 days. Educational only, not financial advice.
