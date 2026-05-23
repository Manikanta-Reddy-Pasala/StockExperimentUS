"""OHLCV cache using EXISTING Postgres tables (no new tables created).

Maps backtest fetcher requests to the prod app's historical_data tables:
    "1h"  -> historical_data_1h     (PK: symbol, timestamp)
    "15m" -> historical_data_15m    (PK: symbol, timestamp)
    "D"   -> historical_data        (PK: symbol, date)
    "5m"  -> not cached (no table); always hits Fyers

Symbol format inside the tables is the full Fyers form
``NSE:<TICKER>-EQ`` (e.g. ``NSE:RELIANCE-EQ``). Backtest harness passes
plain tickers (``RELIANCE``); we normalize via ``to_fyers_symbol`` from
the EMA harness before any DB read/write.

Usage from a fetcher:
    from tools.shared.ohlcv_cache import get_or_fetch
    df = get_or_fetch("RELIANCE", "1h", days=365,
                      lambda sym, d: raw_fyers_fetch(sym, d, user_id=1))
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Maps backtest interval string -> (table_name, time_col_kind)
# time_col_kind: "ts"   = unique by (symbol, timestamp), candle_time present
#                "date" = unique by (symbol, date),     date col present
_TABLE_MAP = {
    "1h":  ("historical_data_1h",  "ts"),
    "15m": ("historical_data_15m", "ts"),
    "D":   ("historical_data",     "date"),
}

_engine = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    try:
        from src.models.database import get_database_manager
        dbm = get_database_manager()
        _engine = dbm.engine
        return _engine
    except Exception as e:
        logger.warning(f"ohlcv_cache: no DB engine ({e})")
        return None


def _to_fyers_sym(symbol: str) -> str:
    """Normalize plain ticker to the Fyers form used in the DB.
    Already-Fyers strings pass through."""
    s = symbol.upper()
    if s.startswith("NSE:") or s.startswith("BSE:"):
        return s
    if s.startswith("^"):
        return s   # index pseudo-tickers — fetcher handles
    return f"NSE:{s.replace('.NS', '')}-EQ"


def read_cached(symbol: str, interval: str,
                from_ts: int, to_ts: int) -> pd.DataFrame:
    """Return cached rows in [from_ts, to_ts] from the matching table.
    Empty df if interval has no table or DB unreachable."""
    if interval not in _TABLE_MAP:
        return pd.DataFrame()
    table, kind = _TABLE_MAP[interval]
    eng = _get_engine()
    if eng is None:
        return pd.DataFrame()
    sym = _to_fyers_sym(symbol)
    try:
        if kind == "ts":
            q = text(
                f"SELECT timestamp, candle_time, open, high, low, close, volume "
                f"FROM {table} "
                f"WHERE symbol = :sym AND timestamp BETWEEN :a AND :b "
                f"ORDER BY timestamp"
            )
            with eng.connect() as conn:
                df = pd.read_sql(q, conn, params={"sym": sym, "a": from_ts, "b": to_ts})
        else:  # daily
            from_d = datetime.utcfromtimestamp(from_ts).date()
            to_d   = datetime.utcfromtimestamp(to_ts).date()
            q = text(
                f"SELECT timestamp, date, open, high, low, close, volume "
                f"FROM {table} "
                f"WHERE symbol = :sym AND date BETWEEN :a AND :b "
                f"ORDER BY date"
            )
            with eng.connect() as conn:
                df = pd.read_sql(q, conn, params={"sym": sym, "a": from_d, "b": to_d})
            if not df.empty:
                df["candle_time"] = pd.to_datetime(df["date"])
                df = df.drop(columns=["date"])
    except Exception as e:
        logger.warning(f"ohlcv_cache: read fail {sym}/{interval}: {e}")
        return pd.DataFrame()

    if df.empty:
        return df
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df["timestamp"] = df["timestamp"].astype("int64")
    return df[["timestamp", "candle_time", "open", "high", "low", "close", "volume"]]


def write_rows(symbol: str, interval: str, df: pd.DataFrame) -> int:
    """Upsert rows from df into the matching table. ON CONFLICT DO NOTHING.
    No-op for unmapped intervals (e.g. 5m)."""
    if interval not in _TABLE_MAP or df is None or df.empty:
        return 0
    table, kind = _TABLE_MAP[interval]
    eng = _get_engine()
    if eng is None:
        return 0
    sym = _to_fyers_sym(symbol)
    try:
        if kind == "ts":
            q = text(
                f"INSERT INTO {table} "
                f"(symbol, timestamp, candle_time, open, high, low, close, volume, data_source) "
                f"VALUES (:sym, :ts, :ct, :o, :h, :l, :c, :v, 'fyers') "
                f"ON CONFLICT (symbol, timestamp) DO NOTHING"
            )
            params = [{
                "sym": sym, "ts": int(r.timestamp), "ct": r.candle_time,
                "o": float(r.open), "h": float(r.high),
                "l": float(r.low), "c": float(r.close),
                "v": int(getattr(r, "volume", 0) or 0),
            } for r in df.itertuples()]
        else:  # daily
            q = text(
                f"INSERT INTO {table} "
                f"(symbol, date, timestamp, open, high, low, close, volume, data_source) "
                f"VALUES (:sym, :dt, :ts, :o, :h, :l, :c, :v, 'fyers') "
                f"ON CONFLICT (symbol, date) DO NOTHING"
            )
            params = [{
                "sym": sym, "dt": pd.to_datetime(r.candle_time).date(),
                "ts": int(r.timestamp),
                "o": float(r.open), "h": float(r.high),
                "l": float(r.low), "c": float(r.close),
                "v": int(getattr(r, "volume", 0) or 0),
            } for r in df.itertuples()]
        with eng.begin() as conn:
            conn.execute(q, params)
        return len(params)
    except Exception as e:
        logger.warning(f"ohlcv_cache: write fail {sym}/{interval}: {e}")
        return 0


def _expected_bars(interval: str, days: int) -> int:
    trading_days = max(1, int(days * 250 / 365))
    return {
        "1h":  trading_days * 6,
        "15m": trading_days * 25,
        "5m":  trading_days * 75,
        "D":   trading_days,
    }.get(interval, trading_days)


def get_or_fetch(symbol: str, interval: str, days: int,
                 fyers_fetcher: Callable[[str, int], pd.DataFrame],
                 min_coverage_frac: float = 0.0) -> pd.DataFrame:
    """Return OHLCV for the last ``days`` days.

    Cache-only mode (default min_coverage_frac=0): return whatever the
    cache has. Never call Fyers during backtest — accept that recent
    IPOs / sparse symbols have less data, strategy will skip them
    naturally via len(candles) check.

    Set ``min_coverage_frac=0.50`` to re-enable fallback Fyers fetch on
    low coverage.
    """
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    from_ts, to_ts = int(start_dt.timestamp()), int(end_dt.timestamp())

    cached = read_cached(symbol, interval, from_ts, to_ts)
    if min_coverage_frac <= 0:
        # Pure cache mode — no Fyers fallback.
        return cached
    expected = _expected_bars(interval, days)
    have = len(cached)
    if have >= int(expected * min_coverage_frac) and have > 0:
        return cached
    fresh = fyers_fetcher(symbol, days)
    if fresh is None or fresh.empty:
        return cached
    write_rows(symbol, interval, fresh)
    return fresh


def warm_cache_summary() -> dict:
    """Return per-(symbol, interval) cache footprint across all 3 tables."""
    eng = _get_engine()
    if eng is None:
        return {}
    out = {}
    for interval, (table, kind) in _TABLE_MAP.items():
        try:
            with eng.connect() as conn:
                rows = conn.execute(text(
                    f"SELECT symbol, COUNT(*) AS n FROM {table} "
                    f"GROUP BY symbol ORDER BY n DESC LIMIT 30"
                )).fetchall()
            for r in rows:
                out[(r.symbol, interval)] = r.n
        except Exception as e:
            logger.warning(f"ohlcv_cache: summary fail {table}: {e}")
    return out


if __name__ == "__main__":
    summary = warm_cache_summary()
    if not summary:
        print("Cache empty (or DB unreachable).")
    else:
        print(f"{len(summary)} (symbol, interval) entries (top 30 per table):")
        for (sym, iv), n in sorted(summary.items(), key=lambda x: -x[1])[:30]:
            print(f"  {sym:25s} {iv:4s} n={n}")
