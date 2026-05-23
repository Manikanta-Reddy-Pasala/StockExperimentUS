"""Refresh the cached Nifty 100 list from NSE archives.

Usage:
    venv/bin/python tools/refresh_nifty100.py

Writes to ``src/data/symbols/nifty100.csv`` (overwrites in place). Fetches
through standard ``requests`` with a browser-style ``User-Agent`` (the NSE
endpoint blocks the default urllib agent).
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

NSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "text/csv,*/*;q=0.9",
}

OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "symbols" / "nifty100.csv"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {NSE_URL} ...")
    r = requests.get(NSE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    body = r.text
    if "Symbol" not in body.splitlines()[0]:
        print("Unexpected response (no Symbol header). Aborting.", file=sys.stderr)
        return 1
    OUT.write_text(body)
    line_count = body.count("\n")
    print(f"Saved {line_count - 1} symbols to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
