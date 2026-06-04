"""IBKR dashboard provider — account/positions snapshot for the web dashboard.

IBKR is single-account; user_id accepted for interface parity. Falls back to safe
defaults when TWS/Gateway is down (the underlying service returns errors cleanly).
"""
import logging
from typing import Dict, List, Any

from ..interfaces.dashboard_interface import IDashboardProvider
from ..brokers.ibkr import get_ibkr_service

logger = logging.getLogger(__name__)


class IBKRDashboardProvider(IDashboardProvider):
    def __init__(self):
        self.ibkr = get_ibkr_service()
        self.broker_name = "ibkr"

    def _positions(self):
        res = self.ibkr.get_positions()
        return res.get("data", []) if res.get("status") == "success" else []

    def get_market_overview(self, user_id: int) -> Dict[str, Any]:
        # Use US index proxies as a lightweight overview.
        q = self.ibkr.get_quotes("QQQ,SPY,DIA")
        return {"status": "success", "data": q.get("data", {})}

    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        funds = self.ibkr.get_funds()
        f = funds.get("data", {}) if funds.get("status") == "success" else {}
        return {"status": "success", "data": {
            "net_liquidation": f.get("NetLiquidation", 0.0),
            "cash": f.get("TotalCashValue", 0.0),
            "positions_count": len(self._positions()),
        }}

    def get_top_holdings(self, user_id: int, limit: int = 5) -> Dict[str, Any]:
        pos = sorted(self._positions(),
                     key=lambda p: abs((p.get("avg_price", 0) or 0) * (p.get("quantity", 0) or 0)),
                     reverse=True)
        return {"status": "success", "data": pos[:limit]}

    def get_recent_activity(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        tb = self.ibkr.get_tradebook()
        data = tb.get("data", []) if tb.get("status") == "success" else []
        return {"status": "success", "data": data[:limit]}

    def get_account_balance(self, user_id: int) -> Dict[str, Any]:
        return self.ibkr.get_funds()

    def get_daily_pnl_chart_data(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        return {"status": "success", "data": {"days": days, "series": []}}

    def get_performance_metrics(self, user_id: int, period: str = "1M") -> Dict[str, Any]:
        return {"status": "success", "data": {"period": period}}

    def get_watchlist_quotes(self, user_id: int, symbols: List[str] = None) -> Dict[str, Any]:
        syms = ",".join(symbols) if symbols else "QQQ,SPY"
        return self.ibkr.get_quotes(syms)
