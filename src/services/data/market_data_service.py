"""MarketDataService — US market data (eToro only).

Replaces the old FyersService data role across the data pipeline. Drop-in for the
methods the data services + routes call on the former broker data service:
`history()`, `quotes()`, `quotes_multiple()`, plus thin compatibility stubs.

Daily bars route through the shared `price_history_provider.fetch_daily_bars`
(eToro, the SAME core the executor uses). Intraday is not supported (eToro
daily-only here). user_id is accepted for signature parity but unused.

Return shapes match what consumers expect:
  history(...) -> {"status":"success","data":{"candles":[{timestamp,open,high,low,close,volume}, ...]}}
  quotes(...)  -> {"status":"success","data":{symbol:{last_price}}}
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from .price_history_provider import fetch_daily_bars

logger = logging.getLogger(__name__)

_DAILY = {"1d", "d", "day", "daily", "1day", "D"}


def _plain(symbol: str) -> str:
    """Strip any exchange prefix/suffix (e.g. 'NSE:AAPL-EQ' -> 'AAPL')."""
    s = symbol
    if ":" in s:
        s = s.split(":", 1)[1]
    if "-" in s and s.rsplit("-", 1)[1].isalpha():
        s = s.rsplit("-", 1)[0]
    return s.upper()


def _err(msg: str) -> Dict[str, Any]:
    return {"status": "error", "message": msg}


class MarketDataService:
    def __init__(self):
        self.source = "etoro"

    # ------------------------------------------------------------------ #
    # history
    # ------------------------------------------------------------------ #
    def history(self, user_id: int, symbol: str, exchange: str = "",
                interval: str = "1d", start_date: str = None,
                end_date: str = None) -> Dict[str, Any]:
        sym = _plain(symbol)
        end = _to_date(end_date) or date.today()
        start = _to_date(start_date) or (end - timedelta(days=365 * 4))
        try:
            if interval in _DAILY or interval.lower() in _DAILY:
                df = fetch_daily_bars(sym, start, end)
            else:
                return _err(f"intraday interval '{interval}' not supported (eToro daily-only)")
            if df is None or df.empty:
                return _err(f"no data for {symbol}")
            candles = [{
                "timestamp": int(datetime(ts.year, ts.month, ts.day,
                                          getattr(ts, "hour", 0), getattr(ts, "minute", 0)).timestamp()),
                "open": float(r["Open"]), "high": float(r["High"]),
                "low": float(r["Low"]), "close": float(r["Close"]),
                "volume": int(r["Volume"]) if r["Volume"] == r["Volume"] else 0,
            } for ts, r in df.iterrows()]
            return {"status": "success", "data": {"candles": candles}}
        except Exception as e:  # noqa: BLE001
            logger.warning("history error %s: %s", symbol, e)
            return _err(str(e))

    # alias used by some legacy callers
    def get_historical_data(self, user_id: int, symbol: str, exchange: str = "",
                            interval: str = "1d", start_date: str = None,
                            end_date: str = None) -> Dict[str, Any]:
        return self.history(user_id, symbol, exchange, interval, start_date, end_date)

    # ------------------------------------------------------------------ #
    # quotes
    # ------------------------------------------------------------------ #
    def quotes(self, user_id: int, symbol: str, exchange: str = "") -> Dict[str, Any]:
        return self.quotes_multiple(user_id, [symbol])

    def quotes_multiple(self, user_id: int, symbols: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for raw in symbols:
            s = _plain(raw)
            df = fetch_daily_bars(s, date.today() - timedelta(days=7), date.today())
            if df is not None and not df.empty:
                out[s] = {"last_price": float(df["Close"].iloc[-1]),
                          "prev_close": float(df["Close"].iloc[-2]) if len(df) > 1 else None}
        return {"status": "success", "data": out}

    def depth(self, user_id: int, symbol: str, exchange: str = "") -> Dict[str, Any]:
        # No L2 depth without a live IBKR market-data subscription.
        return {"status": "error", "message": "market depth not available"}

    def get_market_depth(self, user_id: int, symbol: str, exchange: str = "") -> Dict[str, Any]:
        return self.depth(user_id, symbol, exchange)

    # ------------------------------------------------------------------ #
    # compatibility stubs (India/NSE-only features, no US equivalent)
    # ------------------------------------------------------------------ #
    def get_nse_symbols(self, *args, **kwargs) -> Dict[str, Any]:
        return {"status": "success", "data": []}

    def get_broker_config(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return None


_market_data_service: Optional[MarketDataService] = None


def get_market_data_service() -> MarketDataService:
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MarketDataService()
    return _market_data_service


def _to_date(s) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, date):
        return s
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(s)[:10], fmt).date()
        except ValueError:
            continue
    return None
