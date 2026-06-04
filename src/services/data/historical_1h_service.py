"""
1-Hour Historical Data Service

Fetches 1H OHLCV candles from Fyers and persists them in `historical_data_1h`.
Used by the EMA 200/400 crossover strategy (1H timeframe).

This service does NOT touch login or token flow — it reuses the existing
`MarketDataService.history()` which handles authentication for us.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import and_, desc

try:
    from ..data.market_data_service import MarketDataService
    from ...models.database import get_database_manager
    from ...models.historical_models import HistoricalData1H
    from ...models.stock_models import Stock
except ImportError:
    from ..data.market_data_service import MarketDataService
    from src.models.database import get_database_manager
    from src.models.historical_models import HistoricalData1H
    from src.models.stock_models import Stock

logger = logging.getLogger(__name__)

# Fyers caps intraday history fetches at ~100 days per call.
FYERS_INTRADAY_MAX_DAYS = 95
IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60  # IST = UTC+5:30


class Historical1HService:
    """Fetch and persist 1H OHLCV candles."""

    def __init__(self):
        self.db = get_database_manager()
        self.fyers = MarketDataService()
        self.rate_limit_delay = 0.3  # seconds between Fyers calls

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def backfill_symbol(
        self,
        user_id: int,
        symbol: str,
        days: int = 120,
        exchange: str = "NSE",
    ) -> Dict[str, Any]:
        """
        Backfill `days` of 1H data for one symbol.

        Args:
            user_id: User whose Fyers token will be used.
            symbol: e.g. ``NSE:HDFCBANK-EQ`` or ``HDFCBANK-EQ``.
            days: Calendar days to backfill (default 120 ≈ 80 trading days).
            exchange: Defaults to NSE.
        """
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)
        return self._fetch_and_store_range(user_id, symbol, exchange, start_dt, end_dt)

    def update_latest(
        self,
        user_id: int,
        symbol: str,
        exchange: str = "NSE",
        lookback_days: int = 5,
    ) -> Dict[str, Any]:
        """Incremental update — fetch the last `lookback_days` and upsert."""
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days)
        return self._fetch_and_store_range(user_id, symbol, exchange, start_dt, end_dt)

    def backfill_universe(
        self,
        user_id: int,
        symbols: List[str],
        days: int = 120,
        exchange: str = "NSE",
    ) -> Dict[str, Any]:
        """Backfill many symbols in sequence (rate-limited)."""
        results = {"success": 0, "failed": 0, "details": []}
        for i, sym in enumerate(symbols):
            try:
                res = self.backfill_symbol(user_id, sym, days=days, exchange=exchange)
                if res.get("success"):
                    results["success"] += 1
                else:
                    results["failed"] += 1
                results["details"].append({"symbol": sym, **res})
            except Exception as e:
                logger.error(f"Backfill error for {sym}: {e}")
                results["failed"] += 1
                results["details"].append({"symbol": sym, "success": False, "error": str(e)})
            time.sleep(self.rate_limit_delay)
            if (i + 1) % 25 == 0:
                logger.info(f"1H backfill progress: {i + 1}/{len(symbols)}")
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _fetch_and_store_range(
        self,
        user_id: int,
        symbol: str,
        exchange: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> Dict[str, Any]:
        """Walk the requested window in 95-day chunks (Fyers intraday cap)."""
        total_inserted = 0
        total_updated = 0
        cursor = start_dt
        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(days=FYERS_INTRADAY_MAX_DAYS), end_dt)
            try:
                candles = self._fetch_chunk(user_id, symbol, exchange, cursor, chunk_end)
            except Exception as e:
                logger.error(f"Fetch chunk failed for {symbol} {cursor.date()}..{chunk_end.date()}: {e}")
                cursor = chunk_end
                continue

            ins, upd = self._upsert_candles(symbol, candles)
            total_inserted += ins
            total_updated += upd
            cursor = chunk_end
            time.sleep(self.rate_limit_delay)

        return {
            "success": True,
            "symbol": symbol,
            "inserted": total_inserted,
            "updated": total_updated,
        }

    def _fetch_chunk(
        self,
        user_id: int,
        symbol: str,
        exchange: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> List[Dict[str, Any]]:
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        # `interval='1h'` is mapped to Fyers resolution '60' inside fyers/api.py.
        result = self.fyers.history(
            user_id=user_id,
            symbol=symbol,
            exchange=exchange,
            interval="1h",
            start_date=start_str,
            end_date=end_str,
        )

        if not result or result.get("status") != "success":
            msg = (result or {}).get("message", "no response")
            raise RuntimeError(f"Fyers history failed: {msg}")

        return result.get("data", {}).get("candles", []) or []

    def _upsert_candles(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
    ) -> tuple:
        if not candles:
            return 0, 0

        inserted = 0
        updated = 0
        with self.db.get_session() as session:
            for c in candles:
                try:
                    ts = int(c["timestamp"])
                    o = float(c["open"])
                    h = float(c["high"])
                    lo = float(c["low"])
                    cl = float(c["close"])
                    vol = int(float(c.get("volume") or 0))
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(f"Bad candle for {symbol}: {c} ({e})")
                    continue

                ist_dt = datetime.utcfromtimestamp(ts + IST_OFFSET_SECONDS)

                existing = (
                    session.query(HistoricalData1H)
                    .filter_by(symbol=symbol, timestamp=ts)
                    .one_or_none()
                )

                if existing:
                    existing.open = o
                    existing.high = h
                    existing.low = lo
                    existing.close = cl
                    existing.volume = vol
                    existing.candle_time = ist_dt
                    updated += 1
                else:
                    session.add(
                        HistoricalData1H(
                            symbol=symbol,
                            timestamp=ts,
                            candle_time=ist_dt,
                            open=o,
                            high=h,
                            low=lo,
                            close=cl,
                            volume=vol,
                        )
                    )
                    inserted += 1

            session.commit()

        return inserted, updated

    # ------------------------------------------------------------------
    # Convenience: load candles for the strategy
    # ------------------------------------------------------------------
    def load_candles(
        self,
        symbol: str,
        limit: int = 600,
    ) -> List[HistoricalData1H]:
        """Load the most recent `limit` 1H candles for `symbol` ordered ascending."""
        with self.db.get_session() as session:
            rows = (
                session.query(HistoricalData1H)
                .filter(HistoricalData1H.symbol == symbol)
                .order_by(desc(HistoricalData1H.timestamp))
                .limit(limit)
                .all()
            )
            # Detach from session and reverse to ascending order
            for r in rows:
                session.expunge(r)
        return list(reversed(rows))


_instance: Optional[Historical1HService] = None


def get_historical_1h_service() -> Historical1HService:
    global _instance
    if _instance is None:
        _instance = Historical1HService()
    return _instance
