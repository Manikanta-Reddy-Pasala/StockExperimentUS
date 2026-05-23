"""
Nifty 500 universe loader.

Source: NSE archives CSV at
``https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv``.

A pinned copy lives at ``src/data/symbols/nifty500.csv``. The loader prefers
the cached file; a refresh script (``tools/refresh_nifty500.py``) re-downloads
it on demand. Symbols are returned in Fyers format (``NSE:<SYMBOL>-EQ``).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_CACHE = (
    Path(__file__).resolve().parents[2] / "data" / "symbols" / "nifty500.csv"
)
NSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"


def to_fyers_symbol(nse_symbol: str) -> str:
    """``RELIANCE`` -> ``NSE:RELIANCE-EQ``."""
    s = nse_symbol.strip().upper()
    if s.startswith("NSE:"):
        return s if s.endswith("-EQ") else f"{s}-EQ"
    return f"NSE:{s}-EQ"


def load_nifty500(
    cache_path: Optional[Path] = None,
    fyers_format: bool = True,
) -> List[str]:
    """Read the cached Nifty 500 CSV and return a list of symbols."""
    path = cache_path or DEFAULT_CACHE
    if not path.exists():
        logger.warning(
            f"Nifty 500 cache missing at {path}. "
            f"Run tools/refresh_nifty500.py to download."
        )
        return []

    symbols: List[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sym = (row.get("Symbol") or "").strip()
            series = (row.get("Series") or "EQ").strip()
            if not sym or series.upper() != "EQ":
                continue
            symbols.append(to_fyers_symbol(sym) if fyers_format else sym)
    logger.info(f"Loaded {len(symbols)} Nifty 500 symbols from {path}")
    return symbols


def load_nifty500_with_meta(
    cache_path: Optional[Path] = None,
) -> List[Tuple[str, str, str]]:
    """Return ``(fyers_symbol, company_name, industry)`` triples."""
    path = cache_path or DEFAULT_CACHE
    if not path.exists():
        return []
    out: List[Tuple[str, str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("Symbol") or "").strip()
            if not sym:
                continue
            out.append(
                (to_fyers_symbol(sym),
                 (row.get("Company Name") or "").strip(),
                 (row.get("Industry") or "").strip())
            )
    return out
