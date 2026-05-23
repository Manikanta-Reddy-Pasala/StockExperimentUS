"""Refresh nasdaq100.csv (real Nasdaq-100 constituents) from Wikipedia.

Usage: python tools/refresh_nasdaq100.py
Writes src/data/symbols/nasdaq100.csv with columns: Symbol,Series
(Series='EQ' kept for parity with the India nifty100.csv loader.)
Mirrors the role of nifty100.csv in the Indian repo.
"""
from __future__ import annotations
import sys
from io import StringIO
from pathlib import Path
import pandas as pd
import requests

OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "symbols" / "nasdaq100.csv"
URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _sanitize(t: str) -> str:
    # yfinance uses '-' for class shares (BRK.B -> BRK-B)
    return t.strip().upper().replace(".", "-").replace("/", "-")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = requests.get(URL, headers=HEADERS, timeout=30).text
    tables = pd.read_html(StringIO(html))
    comp = None
    for t in tables:
        cols = {str(c).lower() for c in t.columns}
        if "ticker" in cols or "symbol" in cols:
            comp = t
            break
    if comp is None:
        print("Could not find constituents table", file=sys.stderr)
        return 1
    col = "Ticker" if "Ticker" in comp.columns else "Symbol"
    syms = sorted({_sanitize(s) for s in comp[col].astype(str) if s and s.lower() != "nan"})
    with open(OUT, "w") as f:
        f.write("Symbol,Series\n")
        for s in syms:
            f.write(f"{s},EQ\n")
    print(f"Saved {len(syms)} symbols to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
