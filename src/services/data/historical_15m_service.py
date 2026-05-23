"""
15-Minute Historical Data Service.

Fetches 15m OHLCV candles from Fyers and persists them in
``historical_data_15m``. Used only by the EMA 200/400 sustain check so that
post-cross ENTRY confirmation triggers ~15m after a level break instead of
waiting for the next 1H close.

Mirror of :mod:`historical_1h_service`; reuses the same FyersService auth.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc

try:
    from ..brokers.fyers_service import FyersService
    from ...models.database import get_database_manager
    from ...models.historical_models import HistoricalData15M
except ImportError:
    from src.services.brokers.fyers_service import FyersService
    from src.models.database import get_database_manager
    from src.models.historical_models import HistoricalData15M

logger = logging.getLogger(__name__)

FYERS_INTRADAY_MAX_DAYS = 95
IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60


class Historical15MService:
    """Fetch and persist 15m OHLCV candles."""

    def __init__(self):
        self.db = get_database_manager()
        self.fyers = FyersService()
        self.rate_limit_delay = 0.3

    def backfill_symbol(
        self,
        user_id: int,
        symbol: str,
        days: int = 30,
        exchange: str = "NSE",
    ) -> Dict[str, Any]:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)
        return self._fetch_and_store_range(user_id, symbol, exchange, start_dt, end_dt)

    def update_latest(
        self,
        user_id: int,
        symbol: str,
        exchange: str = "NSE",
        lookback_days: int = 2,
    ) -> Dict[str, Any]:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days)
        return self._fetch_and_store_range(user_id, symbol, exchange, start_dt, end_dt)

    def backfill_universe(
        self,
        user_id: int,
        symbols: List[str],
        days: int = 30,
        exchange: str = "NSE",
    ) -> Dict[str, Any]:
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
                logger.error(f"15m backfill error for {sym}: {e}")
                results["failed"] += 1
                results["details"].append({"symbol": sym, "success": False, "error": str(e)})
            time.sleep(self.rate_limit_delay)
            if (i + 1) % 25 == 0:
                logger.info(f"15m backfill progress: {i + 1}/{len(symbols)}")
        return results

    def _fetch_and_store_range(
        self,
        user_id: int,
        symbol: str,
        exchange: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> Dict[str, Any]:
        total_inserted = 0
        total_updated = 0
        cursor = start_dt
        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(days=FYERS_INTRADAY_MAX_DAYS), end_dt)
            try:
                candles = self._fetch_chunk(user_id, symbol, exchange, cursor, chunk_end)
            except Exception as e:
                logger.error(f"15m fetch chunk failed for {symbol} {cursor.date()}..{chunk_end.date()}: {e}")
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

        result = self.fyers.history(
            user_id=user_id,
            symbol=symbol,
            exchange=exchange,
            interval="15m",
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
                    logger.warning(f"Bad 15m candle for {symbol}: {c} ({e})")
                    continue

                ist_dt = datetime.utcfromtimestamp(ts + IST_OFFSET_SECONDS)

                existing = (
                    session.query(HistoricalData15M)
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
                        HistoricalData15M(
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

    def load_candles(
        self,
        symbol: str,
        limit: int = 200,
    ) -> List[HistoricalData15M]:
        """Most recent ``limit`` 15m candles ordered ascending."""
        with self.db.get_session() as session:
            rows = (
                session.query(HistoricalData15M)
                .filter(HistoricalData15M.symbol == symbol)
                .order_by(desc(HistoricalData15M.timestamp))
                .limit(limit)
                .all()
            )
            for r in rows:
                session.expunge(r)
        return list(reversed(rows))

    def latest_candle(self, symbol: str) -> Optional[HistoricalData15M]:
        """Newest 15m candle for ``symbol``, or None."""
        with self.db.get_session() as session:
            row = (
                session.query(HistoricalData15M)
                .filter(HistoricalData15M.symbol == symbol)
                .order_by(desc(HistoricalData15M.timestamp))
                .first()
            )
            if row is not None:
                session.expunge(row)
        return row


_instance: Optional[Historical15MService] = None


def get_historical_15m_service() -> Historical15MService:
    global _instance
    if _instance is None:
        _instance = Historical15MService()
    return _instance
