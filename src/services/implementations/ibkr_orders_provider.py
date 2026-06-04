"""IBKR orders provider — order book / trades / place-modify-cancel via IBKR."""
import logging
from typing import Dict, Any
from datetime import datetime

from ..interfaces.orders_interface import IOrdersProvider
from ..brokers.ibkr import get_ibkr_service

logger = logging.getLogger(__name__)


class IBKROrdersProvider(IOrdersProvider):
    def __init__(self):
        self.ibkr = get_ibkr_service()
        self.broker_name = "ibkr"

    def get_orders_history(self, user_id: int, start_date: datetime = None,
                           end_date: datetime = None) -> Dict[str, Any]:
        # IBKR exposes open orders + fills live; completed-order history is the fills book.
        return self.ibkr.get_tradebook()

    def get_pending_orders(self, user_id: int) -> Dict[str, Any]:
        return self.ibkr.get_orderbook()

    def get_trades_history(self, user_id: int, start_date: datetime = None,
                           end_date: datetime = None) -> Dict[str, Any]:
        return self.ibkr.get_tradebook()

    def place_order(self, user_id: int, order_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.ibkr.place_order(order_data)

    def modify_order(self, user_id: int, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.ibkr.modify_order(order_id, order_data)

    def cancel_order(self, user_id: int, order_id: str) -> Dict[str, Any]:
        return self.ibkr.cancel_order(order_id)

    def get_order_details(self, user_id: int, order_id: str) -> Dict[str, Any]:
        ob = self.ibkr.get_orderbook()
        if ob.get("status") == "success":
            for o in ob["data"]:
                if str(o.get("order_id")) == str(order_id):
                    return {"status": "success", "data": o}
        return {"status": "error", "message": f"order {order_id} not found"}
