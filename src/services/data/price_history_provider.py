"""Shared daily-bar history core — ONE fetch path for backtests AND the IBKR broker.

KISS: a single function `fetch_daily_bars()` that tries IBKR first (TWS/Gateway)
and falls back to yfinance. Both the DB loader (tools/pull_yfinance_history.py)
and the live IBKR broker (services/brokers/ibkr) call this, so backtest data and
live history come from identical core logic.

Returns a yfinance-shaped DataFrame indexed by Timestamp with columns:
    Open, High, Low, Close, Adj Close, Volume
so it is a drop-in for code that already consumes `yf.download` output.
"""
from __future__ import annotations

import os
import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# IBKR TWS/Gateway connection (paper port 7497 by default; live = 7496).
IBKR_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.environ.get("IBKR_PORT", "7497"))
IBKR_CLIENT_ID = int(os.environ.get("IBKR_CLIENT_ID", "11"))
IBKR_TIMEOUT = float(os.environ.get("IBKR_TIMEOUT", "8"))

COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def _as_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


# --------------------------------------------------------------------------- #
# IBKR source
# --------------------------------------------------------------------------- #
def _ibkr_daily_bars(symbol: str, start: date, end: date) -> Optional[pd.DataFrame]:
    """Pull daily bars from IBKR. Returns None on any connection/data failure
    so the caller transparently falls back to yfinance."""
    try:
        from ib_async import IB, Stock, util
    except ImportError:
        logger.debug("ib_async not installed; skipping IBKR source")
        return None

    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=IBKR_TIMEOUT)
    except Exception as e:  # noqa: BLE001  (TWS down, port closed, etc.)
        logger.info("IBKR connect failed (%s:%s): %s -> fallback", IBKR_HOST, IBKR_PORT, e)
        return None

    try:
        days = (end - start).days + 1
        # IBKR caps a single daily request well above any realistic window.
        duration = f"{max(days, 1)} D"
        contract = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=datetime(end.year, end.month, end.day),
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow="ADJUSTED_LAST",   # split+div adjusted, matches yfinance Adj Close
            useRTH=True,
            formatDate=1,
        )
        if not bars:
            return None
        df = util.df(bars)
        if df is None or df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        out = pd.DataFrame(index=df.index)
        out["Open"] = df["open"]
        out["High"] = df["high"]
        out["Low"] = df["low"]
        out["Close"] = df["close"]
        out["Adj Close"] = df["close"]   # ADJUSTED_LAST already adjusted
        out["Volume"] = df["volume"].fillna(0).astype("int64")
        out = out[(out.index.date >= start) & (out.index.date <= end)]
        return out if not out.empty else None
    except Exception as e:  # noqa: BLE001
        logger.warning("IBKR history error for %s: %s -> fallback", symbol, e)
        return None
    finally:
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# yfinance source (fallback)
# --------------------------------------------------------------------------- #
def _yfinance_daily_bars(symbol: str, start: date, end: date) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed; no data source available")
        return None
    try:
        df = yf.download(
            symbol, start=start.isoformat(), end=end.isoformat(),
            auto_adjust=False, progress=False, threads=False,
        )
        if df is None or df.empty:
            return None
        # yfinance may return a single-level or MultiIndex column frame.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        keep = [c for c in COLUMNS if c in df.columns]
        df = df[keep].dropna(subset=["Open", "High", "Low", "Close"])
        if "Adj Close" not in df.columns:
            df["Adj Close"] = df["Close"]
        if "Volume" not in df.columns:
            df["Volume"] = 0
        return df[COLUMNS] if not df.empty else None
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance history error for %s: %s", symbol, e)
        return None


# --------------------------------------------------------------------------- #
# Public core
# --------------------------------------------------------------------------- #
def fetch_daily_bars(
    symbol: str,
    start,
    end,
    prefer: str = "ibkr",
) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV+AdjClose for one symbol.

    prefer="ibkr" (default): try IBKR, fall back to yfinance.
    prefer="yfinance": yfinance only (skip IBKR entirely).

    Returns a yfinance-shaped DataFrame or None if every source failed.
    """
    start, end = _as_date(start), _as_date(end)

    if prefer == "ibkr":
        df = _ibkr_daily_bars(symbol, start, end)
        if df is not None and not df.empty:
            logger.debug("history %s from IBKR (%d rows)", symbol, len(df))
            return df
    df = _yfinance_daily_bars(symbol, start, end)
    if df is not None and not df.empty:
        logger.debug("history %s from yfinance (%d rows)", symbol, len(df))
    return df


def source_for(symbol: str, start, end, prefer: str = "ibkr") -> str:
    """Diagnostic helper: report which source actually returned data."""
    start, end = _as_date(start), _as_date(end)
    if prefer == "ibkr" and _ibkr_daily_bars(symbol, start, end) is not None:
        return "ibkr"
    if _yfinance_daily_bars(symbol, start, end) is not None:
        return "yfinance"
    return "none"
