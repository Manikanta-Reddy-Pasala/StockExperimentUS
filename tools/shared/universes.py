"""Shared universe data + Fyers fetcher helpers.

Single source of truth for stock universes (NIFTY 50, NIFTY 500) and
the Fyers history fetch used by momentum rotation backtest + live signal.

Previously embedded inside run_ema_200_400_backtest.py — extracted here
when the EMA backtest was removed (rejected model).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.services.data.nifty500_universe import (  # noqa: E402
    load_nifty500_with_meta,
)


# NIFTY 50 constituents (plain NSE tickers, post 2024-2025 reconstitution).
NIFTY50_BASE = [
    'ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK',
    'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BEL', 'BPCL',
    'BHARTIARTL', 'BRITANNIA', 'CIPLA', 'COALINDIA', 'DIVISLAB',
    'DRREDDY', 'EICHERMOT', 'GRASIM', 'HCLTECH', 'HDFCBANK',
    'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK',
    'ITC', 'INDUSINDBK', 'INFY', 'JIOFIN', 'JSWSTEEL',
    'KOTAKBANK', 'LT', 'M&M', 'MARUTI', 'NTPC',
    'NESTLEIND', 'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE',
    'SBIN', 'SHRIRAMFIN', 'SUNPHARMA', 'TCS', 'TATACONSUM',
    'TMPV', 'TATASTEEL', 'TECHM', 'TITAN', 'TRENT',
    'ULTRACEMCO', 'UPL', 'WIPRO',
]
NIFTY50_SYMBOLS = [(s, s) for s in NIFTY50_BASE]


def nifty500_symbols(limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """Return [(symbol, company_name)] for the Nifty 500.

    Symbols are plain NSE tickers; fetcher converts to Fyers form.
    """
    rows = load_nifty500_with_meta()
    out = []
    for fyers_sym, name, _industry in rows:
        plain = fyers_sym.replace("NSE:", "").replace("-EQ", "")
        out.append((plain, name))
    return out[:limit] if limit else out


_NIFTY100_CACHE = ROOT / "src" / "data" / "symbols" / "nifty100.csv"


def nifty100_symbols(limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """Return [(symbol, company_name)] for the real NIFTY 100 (free-float mcap).

    Source: NSE archives ``ind_nifty100list.csv``. Refresh via
    ``tools/refresh_nifty100.py`` (NSE rebalances Mar/Sep).
    """
    import csv
    if not _NIFTY100_CACHE.exists():
        return []
    out: List[Tuple[str, str]] = []
    with _NIFTY100_CACHE.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("Symbol") or "").strip()
            series = (row.get("Series") or "EQ").strip()
            if not sym or series.upper() != "EQ":
                continue
            out.append((sym, (row.get("Company Name") or "").strip()))
    return out[:limit] if limit else out


# ---- US (Nasdaq) universes — plain US tickers, no NSE prefix ----

_NASDAQ100_CACHE = ROOT / "src" / "data" / "symbols" / "nasdaq100.csv"
_NASDAQ500_CACHE = ROOT / "src" / "data" / "symbols" / "nasdaq500.csv"


def _load_us_csv(path: Path, limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """Read a US universe CSV (cols Symbol[,Series]) → [(SYMBOL, ''), ...]."""
    import csv
    if not path.exists():
        return []
    out: List[Tuple[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("Symbol") or "").strip()
            series = (row.get("Series") or "EQ").strip()
            if not sym or series.upper() != "EQ":
                continue
            out.append((sym, (row.get("Company Name") or "").strip()))
    return out[:limit] if limit else out


def nasdaq500_symbols(limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """US analogue of nifty500_symbols(): top-500 Nasdaq by market cap.

    Source: tools/refresh_nasdaq500.py → src/data/symbols/nasdaq500.csv.
    """
    return _load_us_csv(_NASDAQ500_CACHE, limit)


def nasdaq100_symbols(limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """US analogue of the real NIFTY 100 list (Nasdaq-100 constituents).

    Source: tools/refresh_nasdaq100.py → src/data/symbols/nasdaq100.csv.
    """
    return _load_us_csv(_NASDAQ100_CACHE, limit)


# ---- Fyers symbol normalization ----

def to_fyers_symbol(sym: str) -> str:
    """Normalize input ticker to Fyers format.

    Plain NSE  ``RELIANCE``     -> ``NSE:RELIANCE-EQ``
    Yahoo      ``RELIANCE.NS``  -> ``NSE:RELIANCE-EQ``
    Index      ``^NSEI``        -> ``NSE:NIFTY50-INDEX``
    Already    ``NSE:RELIANCE-EQ`` (passthrough)
    """
    s = sym.upper()
    if s.startswith("NSE:"):
        return s
    if s.startswith("^"):
        idx_map = {
            "^NSEI": "NSE:NIFTY50-INDEX",
            "^NSEBANK": "NSE:NIFTYBANK-INDEX",
            "^CNXFIN": "NSE:FINNIFTY-INDEX",
            "^CNXIT": "NSE:NIFTYIT-INDEX",
            "^CNXAUTO": "NSE:NIFTYAUTO-INDEX",
        }
        return idx_map.get(s, s)
    return f"NSE:{s.replace('.NS', '')}-EQ"


# ---- Fyers fetcher (lazy-cached) ----

_FYERS_CACHE = {"service": None, "init_failed": False, "user_id": 1}


def _fyers_service():
    """Lazy-init Fyers service; cache result. Returns None if init fails."""
    if _FYERS_CACHE["init_failed"]:
        return None
    if _FYERS_CACHE["service"] is not None:
        return _FYERS_CACHE["service"]
    try:
        from src.services.data.market_data_service import MarketDataService
        svc = MarketDataService()
        cfg = svc.get_broker_config(_FYERS_CACHE["user_id"])
        if not cfg or not cfg.get("access_token"):
            print(f"  fyers: no token for user_id={_FYERS_CACHE['user_id']}")
            _FYERS_CACHE["init_failed"] = True
            return None
        _FYERS_CACHE["service"] = svc
        return svc
    except Exception as e:
        print(f"  fyers init failed: {e}")
        _FYERS_CACHE["init_failed"] = True
        return None


def _history_with_retry(svc, fyers_sym: str, user_id: int, interval: str,
                         start_str: str, end_str: str,
                         max_retries: int = 3) -> dict | None:
    """Call svc.history() with exponential backoff retry.

    Without this, a single network blip or transient Fyers 429/503 drops the
    whole chunk silently → data gap. Backoff: 2s, 4s, 8s.
    """
    import time as _time
    last_err = None
    for attempt in range(max_retries):
        try:
            res = svc.history(
                user_id=user_id, symbol=fyers_sym, exchange="NSE",
                interval=interval, start_date=start_str, end_date=end_str,
            )
            if res and res.get("status") == "success":
                return res
            last_err = (res or {}).get("message", "no response")
        except Exception as e:
            last_err = str(e)
        if attempt < max_retries - 1:
            _time.sleep(2 ** (attempt + 1))
    print(f"  fyers chunk fail {fyers_sym} {start_str}..{end_str} "
          f"after {max_retries} retries: {last_err}")
    return None


def _fetch_fyers_interval(symbol: str, days: int, user_id: int,
                          interval: str, chunk_days: int = 95) -> pd.DataFrame:
    """Generic Fyers history fetcher — chunks window into chunk_days slices."""
    svc = _fyers_service()
    if svc is None:
        return pd.DataFrame()
    fyers_sym = to_fyers_symbol(symbol)
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    cursor = start_dt
    all_candles: List = []
    while cursor < end_dt:
        chunk_end = min(cursor + timedelta(days=chunk_days), end_dt)
        res = _history_with_retry(
            svc, fyers_sym, user_id, interval,
            cursor.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"),
        )
        if res:
            all_candles += res.get("data", {}).get("candles", []) or []
        cursor = chunk_end
    if not all_candles:
        return pd.DataFrame()
    if isinstance(all_candles[0], dict):
        df = pd.DataFrame(all_candles)
    else:
        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high",
                                                 "low", "close", "volume"])
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df["candle_time"] = pd.to_datetime(df["timestamp"].astype("int64"),
                                       unit="s", utc=True) \
        .dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df["timestamp"] = df["timestamp"].astype("int64")
    return df[["timestamp", "candle_time", "open", "high", "low",
               "close", "volume"]]


def fetch_1h_fyers(symbol: str, days: int = 720, user_id: int = 1) -> pd.DataFrame:
    """1H candles. Postgres-cached — only calls Fyers on cache miss."""
    try:
        from tools.shared.ohlcv_cache import get_or_fetch
    except Exception:
        return _fetch_fyers_interval(symbol, days, user_id, interval="1h", chunk_days=95)
    return get_or_fetch(symbol, "1h", days,
                        lambda s, d: _fetch_fyers_interval(s, d, user_id,
                                                            interval="1h", chunk_days=95))


def fetch_15m_fyers(symbol: str, days: int = 30, user_id: int = 1) -> pd.DataFrame:
    """15m candles. Fyers caps intraday at ~30-day chunks. Postgres-cached."""
    try:
        from tools.shared.ohlcv_cache import get_or_fetch
    except Exception:
        return _fetch_fyers_interval(symbol, days, user_id, interval="15m", chunk_days=30)
    return get_or_fetch(symbol, "15m", days,
                        lambda s, d: _fetch_fyers_interval(s, d, user_id,
                                                            interval="15m", chunk_days=30))


def _fetch_daily_fyers_raw(symbol: str, days: int, user_id: int = 1,
                            chunk_days: int = 360) -> pd.DataFrame:
    """Daily candles direct from Fyers (no cache). Used by prefetch.

    chunk_days=360 stays safely under Fyers's 366-day max-per-request limit
    (cursor → cursor+chunk_days = 361-day span). chunk_days=365 was hitting
    the limit intermittently with -50 'Invalid input' errors.

    Robustness: each chunk has try/except + cursor advance; so recent IPOs
    that have no data for early chunks still get later chunks pulled
    successfully (don't abort the symbol on first chunk failure).
    """
    svc = _fyers_service()
    if svc is None:
        return pd.DataFrame()
    fyers_sym = to_fyers_symbol(symbol)
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    cursor = start_dt
    all_candles: List = []
    while cursor < end_dt:
        chunk_end = min(cursor + timedelta(days=chunk_days), end_dt)
        res = _history_with_retry(
            svc, fyers_sym, user_id, "D",
            cursor.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"),
        )
        if res:
            all_candles += res.get("data", {}).get("candles", []) or []
        cursor = chunk_end
    if not all_candles:
        return pd.DataFrame()
    if isinstance(all_candles[0], dict):
        df = pd.DataFrame(all_candles)
    else:
        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high",
                                                 "low", "close", "volume"])
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df["candle_time"] = pd.to_datetime(df["timestamp"].astype("int64"),
                                       unit="s", utc=True) \
        .dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df["timestamp"] = df["timestamp"].astype("int64")
    return df[["timestamp", "candle_time", "open", "high", "low", "close", "volume"]]


def df_to_candles(df: pd.DataFrame) -> List[SimpleNamespace]:
    """Lightweight stand-ins for HistoricalData1H rows (no DB needed)."""
    return [
        SimpleNamespace(
            timestamp=int(r.timestamp),
            candle_time=r.candle_time,
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=int(r.volume or 0),
        )
        for r in df.itertuples()
    ]
