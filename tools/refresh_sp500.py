"""Refresh the S&P 500 constituent list (current + point-in-time membership).

The S&P 500 reconstitutes throughout the year (quarterly + ad-hoc M&A driven
changes). This job keeps two files current:

  src/data/symbols/sp500.csv             current list (Symbol,Series header)
  src/data/symbols/sp500_membership.csv  PIT membership (symbol,start_date,end_date)

Behavior (idempotent — safe to re-run any number of times per day):
  1. Fetch the CURRENT S&P 500 constituents. Source order (offline-resilient):
       a. Wikipedia "List of S&P 500 companies" table via pandas.read_html
       b. fja05680/sp500 GitHub current-constituents CSV
     On ANY failure (no network, parse error, suspiciously small list) the
     existing files are LEFT UNTOUCHED and the script exits non-zero.
  2. Rewrite sp500.csv with the current tickers (Symbol,Series=EQ header).
  3. Update sp500_membership.csv:
       - NEW ticker not currently open  -> append (start_date=today, end_date=OPEN)
       - open member NOT in the new list -> close it (end_date=today)
     "OPEN" end_date is written as 2099-12-31 to match the existing file format
     and tools/shared/us_index_membership.eligible_at (which parses end_date as a
     real ISO date; an empty string would break it).

Ticker normalization: tickers are normalized to the DASH form (BRK-B, not BRK.B)
consistent with tools/shared/us_index_membership._norm and the price DB /
universe CSVs, so membership intersections with the panel just work.

Usage:
    python3 tools/refresh_sp500.py
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYM_DIR = ROOT / "src" / "data" / "symbols"
SP500_CSV = SYM_DIR / "sp500.csv"
MEMBERSHIP_CSV = SYM_DIR / "sp500_membership.csv"

OPEN_END = "2099-12-31"   # sentinel "still a member" end_date (matches existing file)
MIN_EXPECTED = 480        # sanity floor — the index is ~503 names; refuse a tiny list

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
GITHUB_CSV = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes(current).csv"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _norm(sym: str) -> str:
    """Canonical DASH form (BRK.B -> BRK-B), upper, trimmed."""
    return sym.strip().upper().replace(".", "-")


def _fetch_wikipedia() -> list[str]:
    """Current S&P 500 tickers from the Wikipedia constituents table."""
    import pandas as pd
    import requests

    resp = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    for tbl in tables:
        cols = {str(c).strip().lower() for c in tbl.columns}
        if "symbol" in cols:
            col = next(c for c in tbl.columns if str(c).strip().lower() == "symbol")
            return [_norm(str(s)) for s in tbl[col].tolist() if str(s).strip()]
    raise ValueError("Wikipedia: no table with a 'Symbol' column found")


def _fetch_github() -> list[str]:
    """Current S&P 500 tickers from the fja05680/sp500 current-components CSV.

    That CSV's last row holds the latest constituent set as a comma-joined list
    in the 'tickers' column.
    """
    import requests

    resp = requests.get(GITHUB_CSV, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    if not rows:
        raise ValueError("GitHub CSV: empty")
    last = rows[-1]
    tickers_field = last.get("tickers") or last.get("Tickers") or ""
    syms = [_norm(s) for s in tickers_field.split(",") if s.strip()]
    if not syms:
        raise ValueError("GitHub CSV: no tickers in last row")
    return syms


def fetch_current_constituents() -> list[str]:
    """Try Wikipedia, then GitHub. Raise if both fail or the list is too small."""
    errors = []
    for name, fn in (("wikipedia", _fetch_wikipedia), ("github", _fetch_github)):
        try:
            syms = fn()
            # Dedup PRESERVING source order (Wikipedia lists by company name, not
            # alphabetically) — keeps sp500.csv diffs minimal on each refresh.
            seen: set = set()
            uniq = [s for s in syms if not (s in seen or seen.add(s))]
            if len(uniq) < MIN_EXPECTED:
                raise ValueError(
                    f"{name}: only {len(uniq)} tickers (<{MIN_EXPECTED}); "
                    "refusing to overwrite with a suspect list"
                )
            print(f"Fetched {len(uniq)} S&P 500 constituents from {name}.")
            return uniq
        except Exception as e:  # noqa: BLE001 — try the next source
            print(f"  source '{name}' failed: {e}", file=sys.stderr)
            errors.append(f"{name}: {e}")
    raise RuntimeError("All constituent sources failed:\n  " + "\n  ".join(errors))


def _write_sp500_csv(symbols: list[str]) -> None:
    """Rewrite sp500.csv with Symbol,Series=EQ rows (matches existing format).

    Writes atomically (temp file + replace) so a crash can't corrupt the file.
    """
    tmp = SP500_CSV.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Symbol", "Series"])
        for s in symbols:
            w.writerow([s, "EQ"])
    tmp.replace(SP500_CSV)


def _load_membership_rows() -> list[dict]:
    if not MEMBERSHIP_CSV.exists():
        return []
    with open(MEMBERSHIP_CSV, newline="") as f:
        return list(csv.DictReader(f))


def _is_open(end_date: str) -> bool:
    """An interval is open if end_date is empty or the OPEN sentinel."""
    e = (end_date or "").strip()
    return e == "" or e >= OPEN_END


def _update_membership(new_syms: list[str], today: str) -> tuple[int, int]:
    """Update the PIT membership file. Returns (added, closed) counts.

    Atomic write. Idempotent: if a ticker is already open it is left as-is; if a
    ticker is already closed (and absent) nothing happens.
    """
    rows = _load_membership_rows()
    new_set = set(new_syms)

    # currently-open members (normalized) -> their row index
    open_idx: dict[str, int] = {}
    for i, r in enumerate(rows):
        sym = _norm(r.get("symbol", ""))
        if sym and _is_open(r.get("end_date", "")):
            open_idx[sym] = i

    added = 0
    closed = 0

    # Close any open member that is NOT in the new list.
    for sym, i in open_idx.items():
        if sym not in new_set:
            rows[i]["end_date"] = today
            closed += 1

    # Append any new ticker that is not currently open.
    for sym in new_syms:
        if sym not in open_idx:
            rows.append({"symbol": sym, "start_date": today, "end_date": OPEN_END})
            added += 1

    # Normalize symbols on write (keep dotted->dash consistent going forward).
    tmp = MEMBERSHIP_CSV.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "start_date", "end_date"])
        w.writeheader()
        for r in rows:
            w.writerow({
                "symbol": _norm(r.get("symbol", "")),
                "start_date": (r.get("start_date") or "").strip(),
                "end_date": (r.get("end_date") or OPEN_END).strip() or OPEN_END,
            })
    tmp.replace(MEMBERSHIP_CSV)
    return added, closed


def main() -> int:
    SYM_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    try:
        new_syms = fetch_current_constituents()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not refresh S&P 500 (files left untouched): {e}",
              file=sys.stderr)
        return 1

    try:
        _write_sp500_csv(new_syms)
        added, closed = _update_membership(new_syms, today)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: write failed: {e}", file=sys.stderr)
        return 1

    print(f"sp500.csv: {len(new_syms)} current tickers.")
    print(f"sp500_membership.csv: +{added} added (start={today}), "
          f"{closed} closed (end={today}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
