"""Refresh nasdaq500.csv = top 500 Nasdaq-listed stocks by market cap.

Mirrors nifty500.csv in the Indian repo (the broad ADV-rankable pool).
Source: nasdaq.com screener API (needs a browser User-Agent).
Usage: python tools/refresh_nasdaq500.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "symbols" / "nasdaq500.csv"
API = ("https://api.nasdaq.com/api/screener/stocks"
       "?tableonly=true&limit=6000&exchange=nasdaq")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nasdaq.com/",
}


def _mktcap(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def _sanitize(t: str) -> str:
    return t.strip().upper().replace(".", "-").replace("/", "-")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(API, headers=HEADERS, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["table"]["rows"]
    clean = [(_sanitize(x["symbol"]), _mktcap(x.get("marketCap")))
             for x in rows
             if x.get("symbol") and all(c not in x["symbol"] for c in "^~")]
    clean = [(s, m) for s, m in clean if m > 0]
    clean.sort(key=lambda t: t[1], reverse=True)
    top = clean[:500]
    with open(OUT, "w") as f:
        f.write("Symbol,Series\n")
        for s, _ in top:
            f.write(f"{s},EQ\n")
    print(f"Saved {len(top)} symbols to {OUT} (largest: {top[0][0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
