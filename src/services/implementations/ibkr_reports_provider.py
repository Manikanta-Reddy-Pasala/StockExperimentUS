"""IBKR reports provider — minimal P&L / trading-summary from the fills book.

Tax/Flex statement generation is not wired (IBKR Flex Web Service is a separate
integration); those return a clear not-implemented status rather than fake data.
"""
import logging
from typing import Dict, Any
from datetime import datetime

from ..interfaces.reports_interface import IReportsProvider, ReportType
from ..brokers.ibkr import get_ibkr_service

logger = logging.getLogger(__name__)


class IBKRReportsProvider(IReportsProvider):
    def __init__(self):
        self.ibkr = get_ibkr_service()
        self.broker_name = "ibkr"

    def generate_pnl_report(self, user_id: int, start_date: datetime,
                            end_date: datetime, **kwargs) -> Dict[str, Any]:
        tb = self.ibkr.get_tradebook()
        fills = tb.get("data", []) if tb.get("status") == "success" else []
        return {"status": "success", "data": {"fills": fills,
                                               "start": str(start_date), "end": str(end_date)}}

    def generate_tax_report(self, user_id: int, financial_year: str, **kwargs) -> Dict[str, Any]:
        return {"status": "error",
                "message": "Tax report requires IBKR Flex Web Service (not wired)"}

    def generate_portfolio_report(self, user_id: int, report_type: "ReportType",
                                  **kwargs) -> Dict[str, Any]:
        return self.ibkr.get_positions()

    def generate_trading_summary(self, user_id: int, start_date: datetime,
                                 end_date: datetime, **kwargs) -> Dict[str, Any]:
        tb = self.ibkr.get_tradebook()
        fills = tb.get("data", []) if tb.get("status") == "success" else []
        buys = sum(1 for f in fills if str(f.get("side", "")).upper().startswith("B"))
        sells = len(fills) - buys
        return {"status": "success", "data": {"fills": len(fills), "buys": buys, "sells": sells}}

    def get_report_history(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        return {"status": "success", "data": []}

    def download_report(self, user_id: int, report_id: str) -> Dict[str, Any]:
        return {"status": "error", "message": "download not implemented for IBKR"}
