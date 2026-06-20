"""US market-cap segment classification (large / mid / small / other).

India used true point-in-time NSE index membership (Nifty 100 / Midcap-150 /
Smallcap-250) with Wayback-built history. The US repo has NO historical index
reconstitution data, so this is a CURRENT-SNAPSHOT classification (best-effort,
NOT true PIT) built from the symbol CSVs already in the repo:

    large  -> in S&P 500            (src/data/symbols/sp500.csv)
    mid    -> in Nasdaq-500 but NOT S&P 500   (broader names outside the large-cap S&P)
    small  -> in neither index list (fallthrough of a known US ticker)
    other  -> unknown / not a tracked equity (ETF, leveraged, index proxy)

`classify_pit(sym, on_date)` ignores `on_date` (no history available) and is kept
only so call sites mirror the India API. Revisit if a US reconstitution feed is
added.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Optional, Set

_SYM_DIR = Path(__file__).resolve().parents[2] / "src" / "data" / "symbols"


def _norm(sym: str) -> str:
    """Plain US ticker: strip exchange prefixes / -EQ suffix / .US, upper-case."""
    s = (sym or "").upper().strip()
    for p in ("NASDAQ:", "NYSE:", "NSE:", "BSE:", "AMEX:"):
        if s.startswith(p):
            s = s[len(p):]
    s = s.replace("-EQ", "").replace(".US", "").replace(".NS", "")
    return s


def _load(name: str) -> Set[str]:
    """Load a symbols CSV -> set of plain tickers. Tolerates header variations
    (Symbol / symbol / ticker) or a single-column file."""
    p = _SYM_DIR / name
    out: Set[str] = set()
    if not p.exists():
        return out
    with open(p, newline="") as fh:
        rdr = csv.reader(fh)
        rows = list(rdr)
    if not rows:
        return out
    header = [c.strip().lower() for c in rows[0]]
    col = None
    for cand in ("symbol", "ticker", "tradingsymbol"):
        if cand in header:
            col = header.index(cand)
            break
    body = rows[1:] if col is not None else rows
    if col is None:
        col = 0  # single-column / headerless
    for r in body:
        if col < len(r) and r[col].strip():
            out.add(_norm(r[col]))
    return out


@lru_cache(maxsize=1)
def _sp500() -> Set[str]:
    return _load("sp500.csv")


@lru_cache(maxsize=1)
def _nasdaq500() -> Set[str]:
    return _load("nasdaq500.csv")


def classify(sym: str) -> str:
    """Current-snapshot cap segment -> large|mid|other.

    large = S&P 500 member; mid = Nasdaq-500 member outside the S&P 500;
    other = anything else (ETFs, leveraged proxies, untracked tickers). There is
    no US small-cap list in the repo, so 'small' is not currently emitted."""
    s = _norm(sym)
    if not s:
        return "other"
    if s in _sp500():
        return "large"
    if s in _nasdaq500():
        return "mid"
    return "other"


def classify_pit(sym: str, on_date=None) -> str:
    """PIT-shaped wrapper. US has no membership history, so `on_date` is ignored
    and the current-snapshot classification is returned."""
    return classify(sym)
