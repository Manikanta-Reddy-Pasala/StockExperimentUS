"""US backtest fill-reference for the live-vs-backtest slippage monitor.

India overlaid a Fyers 5-minute exec-time bar on top of the next-day open to get
a live-parity fill price. The US data layer (eToro/yfinance) has DAILY bars only
— there is no 5m feed — and US backtests fill at the NEXT-DAY DAILY OPEN. So the
backtest "expected" fill price for a (symbol, date) is simply that date's daily
OPEN from `historical_data`. `exec_raw_open()` returns it; the slippage card and
fill-drift monitor compare the live fill price against it.

Because there is no intraday overlay, `fill_open()` is a pass-through (returns the
daily open unchanged) and `enabled()` is False. The module + API are kept so call
sites mirror India; revisit if a US intraday feed is added.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("intraday_fill")

_CACHE_FILE = Path(__file__).resolve().parent / "intraday_fill_cache.json"
_cache: Optional[dict] = None
_engine = None


def enabled() -> bool:
    """Intraday overlay master switch. US has no 5m feed, so default OFF.
    (Set BACKTEST_INTRADAY_FILL=1 only if a real intraday source is wired.)"""
    return os.environ.get("BACKTEST_INTRADAY_FILL", "0") == "1"


def _norm(sym: str) -> str:
    s = (sym or "").upper().strip()
    for p in ("NASDAQ:", "NYSE:", "NSE:", "BSE:", "AMEX:"):
        if s.startswith(p):
            s = s[len(p):]
    return s.replace("-EQ", "").replace(".US", "").replace(".NS", "")


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    from src.models.database import get_database_manager
    _engine = get_database_manager().engine
    return _engine


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CACHE_FILE.read_text()) if _CACHE_FILE.exists() else {}
        except Exception:
            _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    try:
        _CACHE_FILE.write_text(json.dumps(_cache, separators=(",", ":")))
    except Exception as e:
        log.debug(f"cache save failed: {e}")


def exec_raw_open(sym: str, date_iso: str, model: str = None,
                  side: str = None) -> Optional[float]:
    """Backtest reference fill price = the daily OPEN for (sym, date_iso) from
    historical_data (yfinance). Memoised in intraday_fill_cache.json for offline
    replay. Returns None if unavailable. `model`/`side` are accepted for API
    parity with India (US has a single daily-open reference per symbol-date)."""
    s = _norm(sym)
    day = (date_iso or "")[:10]
    if not s or len(day) != 10:
        return None
    cache = _load_cache()
    key = f"{s}|{day}"
    if key in cache:
        v = cache[key]
        return float(v) if v is not None else None
    val: Optional[float] = None
    try:
        from sqlalchemy import text
        with _get_engine().connect() as c:
            r = c.execute(text(
                "SELECT open FROM historical_data "
                "WHERE symbol=:s AND date=:d AND data_source='yfinance' "
                "ORDER BY date LIMIT 1"
            ), {"s": s, "d": day}).fetchone()
            if r and r[0] and float(r[0]) > 0:
                val = round(float(r[0]), 4)
    except Exception as e:
        log.debug(f"exec_raw_open db miss {key}: {e}")
        return None  # don't cache transient DB errors
    cache[key] = val
    _save_cache()
    return val


def fill_open(sym: str, date_iso: str, model: str, daily_open: float,
              side: str = None) -> Tuple[float, bool]:
    """Resolve the live-parity fill price. US has no intraday overlay, so this
    returns (daily_open, False). Signature matches India for drop-in call sites."""
    if not enabled():
        return float(daily_open), False
    px = exec_raw_open(sym, date_iso, model, side)
    if px and px > 0:
        return px, True
    return float(daily_open), False
