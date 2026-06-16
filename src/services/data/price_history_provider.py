"""Shared daily-bar history core — ONE fetch path for backtests AND live code.

KISS: a single function `fetch_daily_bars()` backed solely by the eToro public
market-data API (https://api-portal.etoro.com). There is no yfinance or IBKR
fallback — eToro is the only data source. The DB loader
(tools/pull_etoro_history.py), the data pipeline and the live executor all
call this, so backtest data and live history come from identical core logic.

Returns a DataFrame indexed by Timestamp with columns:
    Open, High, Low, Close, Adj Close, Volume
(the same column layout the rest of the pipeline already consumes).
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# eToro public market-data API (https://api-portal.etoro.com).
# Auth = three headers: x-request-id (per-request UUID), x-api-key, x-user-key.
# Keys are minted under eToro Settings > Trading > API Key Management.
ETORO_BASE_URL = os.environ.get("ETORO_BASE_URL", "https://public-api.etoro.com/api/v1").rstrip("/")
ETORO_API_KEY = os.environ.get("ETORO_API_KEY", "")
ETORO_USER_KEY = os.environ.get("ETORO_USER_KEY", "")
ETORO_TIMEOUT = float(os.environ.get("ETORO_TIMEOUT", "10"))
# eToro daily candles are count-based (max 1000 ≈ 4y of trading days), latest-first.
ETORO_MAX_CANDLES = 1000
_ETORO_INTERVAL_DAILY = "OneDay"

COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]

# Module-level symbol -> eToro instrumentId cache (avoids a lookup per history call).
_ETORO_ID_CACHE: dict[str, Optional[int]] = {}


def _as_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


# --------------------------------------------------------------------------- #
# eToro source (sole data source)
# --------------------------------------------------------------------------- #
def _etoro_headers() -> dict:
    return {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": ETORO_API_KEY,
        "x-user-key": ETORO_USER_KEY,
        "Accept": "application/json",
    }


def _etoro_instrument_id(symbol: str, session) -> Optional[int]:
    """Resolve a ticker (e.g. AAPL) to eToro's integer instrumentId. Cached."""
    key = symbol.upper()
    if key in _ETORO_ID_CACHE:
        return _ETORO_ID_CACHE[key]
    try:
        resp = session.get(
            f"{ETORO_BASE_URL}/instruments/{key}",
            headers=_etoro_headers(), timeout=ETORO_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.info("eToro instrument lookup %s -> HTTP %s", key, resp.status_code)
            _ETORO_ID_CACHE[key] = None
            return None
        iid = resp.json().get("instrumentId")
        iid = int(iid) if iid is not None else None
        _ETORO_ID_CACHE[key] = iid
        return iid
    except Exception as e:  # noqa: BLE001
        logger.warning("eToro instrument lookup error for %s: %s", key, e)
        return None


def _etoro_daily_bars(symbol: str, start: date, end: date) -> Optional[pd.DataFrame]:
    """Pull daily bars from eToro's public market-data API. Returns None on any
    config/connection/data failure (eToro is the only source, so None means the
    bars are simply unavailable).

    The candles endpoint is count-based (latest-first), not date-ranged, so we
    request enough recent daily candles to cover the window then filter to it.
    Windows older than ~1000 trading days back will filter empty.
    """
    if not (ETORO_API_KEY and ETORO_USER_KEY):
        logger.error("eToro keys not configured (ETORO_API_KEY/ETORO_USER_KEY); no data source")
        return None
    try:
        import requests
    except ImportError:
        logger.error("requests not installed; eToro source unavailable")
        return None

    session = requests.Session()
    try:
        iid = _etoro_instrument_id(symbol, session)
        if iid is None:
            return None
        days = (date.today() - start).days + 2          # cover window incl. today
        count = max(1, min(days, ETORO_MAX_CANDLES))
        if days > ETORO_MAX_CANDLES:
            logger.info("eToro %s: window needs %d daily candles > cap %d; "
                        "older bars unavailable", symbol, days, ETORO_MAX_CANDLES)
        url = (f"{ETORO_BASE_URL}/market-data/instruments/{iid}"
               f"/history/candles/desc/{_ETORO_INTERVAL_DAILY}/{count}")
        resp = session.get(url, headers=_etoro_headers(), timeout=ETORO_TIMEOUT)
        if resp.status_code != 200:
            logger.info("eToro candles %s (id=%s) -> HTTP %s", symbol, iid, resp.status_code)
            return None
        payload = resp.json()
        # Response nests candles: {"candles": [{"candles": [ {fromDate,open,...}, ... ]}]}
        rows = []
        for group in payload.get("candles", []) or []:
            inner = group.get("candles") if isinstance(group, dict) else None
            for c in (inner if inner is not None else [group]):
                if not isinstance(c, dict) or "close" not in c:
                    continue
                rows.append(c)
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["fromDate"]).dt.tz_localize(None).dt.normalize()
        df = df.set_index("date").sort_index()
        out = pd.DataFrame(index=df.index)
        out["Open"] = df["open"].astype(float)
        out["High"] = df["high"].astype(float)
        out["Low"] = df["low"].astype(float)
        out["Close"] = df["close"].astype(float)
        out["Adj Close"] = df["close"].astype(float)   # eToro candles unadjusted; Close==AdjClose
        out["Volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0).astype("int64")
        out = out[~out.index.duplicated(keep="last")]
        out = out[(out.index.date >= start) & (out.index.date <= end)]
        return out if not out.empty else None
    except Exception as e:  # noqa: BLE001
        logger.warning("eToro history error for %s: %s", symbol, e)
        return None
    finally:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Public core
# --------------------------------------------------------------------------- #
def fetch_daily_bars(symbol: str, start, end) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV+AdjClose for one symbol from eToro.

    Returns a DataFrame with COLUMNS, or None if eToro returned no data.
    """
    start, end = _as_date(start), _as_date(end)
    df = _etoro_daily_bars(symbol, start, end)
    if df is not None and not df.empty:
        logger.debug("history %s from eToro (%d rows)", symbol, len(df))
    return df


def source_for(symbol: str, start, end) -> str:
    """Diagnostic helper: report whether eToro returned data."""
    start, end = _as_date(start), _as_date(end)
    if _etoro_daily_bars(symbol, start, end) is not None:
        return "etoro"
    return "none"
