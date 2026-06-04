"""IBKR portfolio provider — positions/holdings/allocation from Interactive Brokers.

Single-account model (TWS/Gateway): user_id is accepted for interface parity but
not used to scope data. Returns interface-shaped dicts; IBKR-unavailable data
(dividends, long-history risk metrics) returns safe empty defaults.
"""
import logging
from typing import Dict, Any
from datetime import datetime

from ..interfaces.portfolio_interface import IPortfolioProvider
from ..brokers.ibkr import get_ibkr_service

logger = logging.getLogger(__name__)


class IBKRPortfolioProvider(IPortfolioProvider):
    def __init__(self):
        self.ibkr = get_ibkr_service()
        self.broker_name = "ibkr"

    def _positions(self):
        res = self.ibkr.get_positions()
        return res.get("data", []) if res.get("status") == "success" else []

    def get_holdings(self, user_id: int) -> Dict[str, Any]:
        return {"status": "success", "data": self._positions()}

    def get_positions(self, user_id: int) -> Dict[str, Any]:
        return {"status": "success", "data": self._positions()}

    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        funds = self.ibkr.get_funds()
        f = funds.get("data", {}) if funds.get("status") == "success" else {}
        positions = self._positions()
        invested = sum((p.get("avg_price", 0) or 0) * (p.get("quantity", 0) or 0)
                       for p in positions)
        return {"status": "success", "data": {
            "net_liquidation": f.get("NetLiquidation", 0.0),
            "cash": f.get("TotalCashValue", 0.0),
            "buying_power": f.get("BuyingPower", 0.0),
            "invested": round(invested, 2),
            "positions_count": len(positions),
        }}

    def get_portfolio_allocation(self, user_id: int) -> Dict[str, Any]:
        positions = self._positions()
        total = sum(abs((p.get("avg_price", 0) or 0) * (p.get("quantity", 0) or 0))
                    for p in positions) or 1.0
        alloc = [{"symbol": p.get("symbol"),
                  "weight_pct": round(abs((p.get("avg_price", 0) or 0) *
                                          (p.get("quantity", 0) or 0)) / total * 100, 2)}
                 for p in positions]
        return {"status": "success", "data": alloc}

    def get_portfolio_performance(self, user_id: int, period: str = "1M") -> Dict[str, Any]:
        # IBKR PortfolioAnalyst history not wired; return empty series.
        return {"status": "success", "data": {"period": period, "series": []}}

    def get_dividend_history(self, user_id: int, start_date: datetime = None,
                             end_date: datetime = None) -> Dict[str, Any]:
        return {"status": "success", "data": []}

    def get_portfolio_risk_metrics(self, user_id: int) -> Dict[str, Any]:
        return {"status": "success", "data": {}}
