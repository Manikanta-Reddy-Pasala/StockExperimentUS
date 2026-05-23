"""
Daily Suggested Stocks Snapshot Service.

Slim helper around the ``daily_suggested_stocks`` table. Used by older
codepaths to read/write strategy snapshots. The active EMA 200/400
crossover runner does its own upsert; this module is retained for legacy
read paths.
"""

from datetime import datetime, date
from typing import List, Dict, Optional
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


COLUMN_LIST = (
    "date, symbol, strategy, model_type, stock_name, current_price, market_cap, "
    "selection_score, rank, target_price, stop_loss, recommendation, reason, "
    "sector, market_cap_category, created_at"
)


class DailySnapshotService:
    """Reader/writer for ``daily_suggested_stocks`` (current schema)."""

    def __init__(self, db_session):
        self.db = db_session

    def save_daily_snapshot(
        self,
        suggested_stocks: List[Dict],
        snapshot_date: Optional[date] = None,
        strategy: str = "ema_200_400",
        model_type: str = "crossover",
    ) -> Dict:
        if snapshot_date is None:
            snapshot_date = date.today()

        logger.info(
            f"Saving daily snapshot for {snapshot_date} "
            f"({len(suggested_stocks)} rows, strategy={strategy})"
        )

        inserted = 0
        updated = 0
        errors = 0

        for stock in suggested_stocks:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            try:
                row = {
                    "date": snapshot_date,
                    "symbol": symbol,
                    "strategy": strategy,
                    "model_type": model_type,
                    "stock_name": stock.get("name") or stock.get("stock_name"),
                    "current_price": stock.get("current_price"),
                    "market_cap": stock.get("market_cap"),
                    "selection_score": stock.get("selection_score"),
                    "rank": stock.get("rank"),
                    "target_price": stock.get("target_price"),
                    "stop_loss": stock.get("stop_loss"),
                    "recommendation": stock.get("recommendation"),
                    "reason": stock.get("reason"),
                    "sector": stock.get("sector"),
                    "market_cap_category": stock.get("market_cap_category"),
                }

                upsert = text(
                    """
                    INSERT INTO daily_suggested_stocks (
                        date, symbol, strategy, model_type, stock_name,
                        current_price, market_cap, selection_score, rank,
                        target_price, stop_loss, recommendation, reason,
                        sector, market_cap_category, created_at
                    ) VALUES (
                        :date, :symbol, :strategy, :model_type, :stock_name,
                        :current_price, :market_cap, :selection_score, :rank,
                        :target_price, :stop_loss, :recommendation, :reason,
                        :sector, :market_cap_category,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (date, symbol, strategy, model_type) DO UPDATE SET
                        stock_name = EXCLUDED.stock_name,
                        current_price = EXCLUDED.current_price,
                        market_cap = EXCLUDED.market_cap,
                        selection_score = EXCLUDED.selection_score,
                        rank = EXCLUDED.rank,
                        target_price = EXCLUDED.target_price,
                        stop_loss = EXCLUDED.stop_loss,
                        recommendation = EXCLUDED.recommendation,
                        reason = EXCLUDED.reason,
                        sector = EXCLUDED.sector,
                        market_cap_category = EXCLUDED.market_cap_category
                    RETURNING (xmax = 0) AS inserted
                    """
                )

                result = self.db.execute(upsert, row)
                xmax_inserted = result.fetchone()
                if xmax_inserted and xmax_inserted[0]:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                logger.error(f"Error saving snapshot for {symbol}: {e}")
                errors += 1

        self.db.commit()
        return {
            "date": snapshot_date.isoformat(),
            "total_stocks": len(suggested_stocks),
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
        }

    def get_latest_snapshot(
        self,
        strategy: str = "ema_200_400",
        limit: int = 50,
    ) -> List[Dict]:
        query = text(
            f"""
            SELECT {COLUMN_LIST}
            FROM daily_suggested_stocks
            WHERE strategy = :strategy
              AND date = (SELECT MAX(date) FROM daily_suggested_stocks
                          WHERE strategy = :strategy)
            ORDER BY selection_score DESC NULLS LAST
            LIMIT :limit
            """
        )
        rows = self.db.execute(query, {"strategy": strategy, "limit": limit}).fetchall()

        out: List[Dict] = []
        for row in rows:
            d = dict(row._mapping)
            if d.get("date"):
                d["date"] = d["date"].isoformat()
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            out.append(d)
        return out

    def get_snapshot_dates(self, strategy: str = "ema_200_400") -> List[str]:
        rows = self.db.execute(
            text(
                """
                SELECT DISTINCT date FROM daily_suggested_stocks
                WHERE strategy = :strategy
                ORDER BY date DESC LIMIT 60
                """
            ),
            {"strategy": strategy},
        ).fetchall()
        return [r.date.isoformat() for r in rows if r.date]

    def delete_old_snapshots(self, keep_days: int = 90) -> int:
        result = self.db.execute(
            text(
                f"""
                DELETE FROM daily_suggested_stocks
                WHERE date < CURRENT_DATE - INTERVAL '{int(keep_days)} days'
                """
            )
        )
        deleted = result.rowcount or 0
        self.db.commit()
        return deleted
