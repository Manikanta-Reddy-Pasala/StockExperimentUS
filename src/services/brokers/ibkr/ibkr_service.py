"""IBKR broker service — Interactive Brokers (US) trade + history.

KISS scope: history + orders module.
  * History  -> delegates to the SAME shared core the backtest loader uses
                (services/data/price_history_provider.fetch_daily_bars), so
                live history and backtest data share one code path.
  * Orders   -> market/limit place / modify / cancel via ib_async.
  * Account  -> positions, holdings, funds via ib_async.
  * Fallback -> yfinance for history/quotes when TWS/Gateway is unreachable.

Connects to TWS or IB Gateway. Default = paper trading port 7497
(live = 7496). Override via IBKR_HOST / IBKR_PORT / IBKR_CLIENT_ID env vars.

Implements the project BaseBrokerService interface. Self-contained: no DB or
per-user token coupling (unlike the Fyers service) — IBKR auth lives in TWS.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from src.services.brokers.base_broker_service import BaseBrokerService
from src.services.data.price_history_provider import (
    fetch_daily_bars,
    IBKR_HOST,
    IBKR_PORT,
    IBKR_CLIENT_ID,
    IBKR_TIMEOUT,
)

logger = logging.getLogger(__name__)


class IBKRBrokerService(BaseBrokerService):
    """Interactive Brokers service (paper by default). Graceful when TWS is down:
    history/quotes fall back to yfinance; trading calls return a clear error."""

    def __init__(self, host: str = None, port: int = None, client_id: int = None):
        super().__init__(client_id=str(client_id) if client_id else str(IBKR_CLIENT_ID))
        self.host = host or IBKR_HOST
        self.port = int(port or IBKR_PORT)
        self.ib_client_id = int(client_id or IBKR_CLIENT_ID)
        self._ib = None  # lazy ib_async.IB instance

    # ------------------------------------------------------------------ #
    # connection
    # ------------------------------------------------------------------ #
    def _connect(self):
        """Return a connected ib_async.IB, or None if TWS/Gateway unreachable."""
        if self._ib is not None and self._ib.isConnected():
            return self._ib
        try:
            from ib_async import IB
        except ImportError:
            logger.error("ib_async not installed — `pip install ib_async`")
            return None
        ib = IB()
        try:
            ib.connect(self.host, self.port, clientId=self.ib_client_id, timeout=IBKR_TIMEOUT)
            self._ib = ib
            self.is_connected = True
            return ib
        except Exception as e:  # noqa: BLE001
            logger.info("IBKR connect failed %s:%s -> %s", self.host, self.port, e)
            self.is_connected = False
            return None

    def disconnect(self):
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._ib = None
        self.is_connected = False

    @staticmethod
    def _stock(symbol: str):
        from ib_async import Stock
        c = Stock(symbol.upper(), "SMART", "USD")
        return c

    @staticmethod
    def _ok(data: Any) -> Dict[str, Any]:
        return {"s": "ok", "status": "success", "data": data}

    @staticmethod
    def _err(msg: str) -> Dict[str, Any]:
        return {"s": "error", "status": "error", "message": msg}

    # ------------------------------------------------------------------ #
    # status / account
    # ------------------------------------------------------------------ #
    def test_connection(self) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err(f"Cannot reach TWS/Gateway at {self.host}:{self.port} "
                             f"(paper=7497, live=7496). History falls back to yfinance.")
        try:
            accounts = ib.managedAccounts()
            return self._ok({"connected": True, "accounts": accounts,
                             "host": self.host, "port": self.port})
        finally:
            pass

    def get_user_profile(self) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        accounts = ib.managedAccounts()
        return self._ok({"accounts": accounts, "broker": "IBKR"})

    def get_funds(self) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        vals = ib.accountSummary()
        wanted = {"NetLiquidation", "TotalCashValue", "BuyingPower",
                  "AvailableFunds", "GrossPositionValue"}
        funds = {v.tag: float(v.value) for v in vals
                 if v.tag in wanted and _is_float(v.value)}
        return self._ok(funds)

    def get_holdings(self) -> Dict[str, Any]:
        """Long-term holdings = IBKR portfolio positions (mirrors Fyers 'holdings')."""
        return self.get_positions()

    def get_positions(self) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        out: List[Dict[str, Any]] = []
        for p in ib.positions():
            out.append({
                "symbol": p.contract.symbol,
                "exchange": p.contract.exchange or "SMART",
                "quantity": p.position,
                "avg_price": p.avgCost,
            })
        return self._ok(out)

    # ------------------------------------------------------------------ #
    # orders
    # ------------------------------------------------------------------ #
    def get_orderbook(self) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        out = []
        for t in ib.openTrades():
            out.append({
                "order_id": t.order.orderId,
                "symbol": t.contract.symbol,
                "side": t.order.action,
                "qty": t.order.totalQuantity,
                "type": t.order.orderType,
                "status": t.orderStatus.status,
                "filled": t.orderStatus.filled,
                "avg_fill_price": t.orderStatus.avgFillPrice,
            })
        return self._ok(out)

    def get_tradebook(self) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        out = []
        for f in ib.fills():
            out.append({
                "symbol": f.contract.symbol,
                "side": f.execution.side,
                "qty": f.execution.shares,
                "price": f.execution.price,
                "time": str(f.execution.time),
            })
        return self._ok(out)

    def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """order_data: {symbol, side(BUY/SELL), qty, type(MKT/LMT), price?}"""
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR — cannot place order")
        try:
            from ib_async import MarketOrder, LimitOrder
            symbol = order_data["symbol"]
            side = order_data.get("side", order_data.get("action", "BUY")).upper()
            qty = float(order_data["qty"])
            otype = order_data.get("type", "MKT").upper()
            contract = self._stock(symbol)
            ib.qualifyContracts(contract)
            if otype in ("LMT", "LIMIT"):
                order = LimitOrder(side, qty, float(order_data["price"]))
            else:
                order = MarketOrder(side, qty)
            trade = ib.placeOrder(contract, order)
            ib.sleep(0.5)
            return self._ok({
                "order_id": trade.order.orderId,
                "symbol": symbol, "side": side, "qty": qty, "type": otype,
                "status": trade.orderStatus.status,
            })
        except Exception as e:  # noqa: BLE001
            return self._err(f"place_order failed: {e}")

    def modify_order(self, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        try:
            for t in ib.openTrades():
                if str(t.order.orderId) == str(order_id):
                    if "qty" in order_data:
                        t.order.totalQuantity = float(order_data["qty"])
                    if "price" in order_data:
                        t.order.lmtPrice = float(order_data["price"])
                    ib.placeOrder(t.contract, t.order)  # re-place w/ same id = modify
                    ib.sleep(0.3)
                    return self._ok({"order_id": order_id, "status": t.orderStatus.status})
            return self._err(f"order {order_id} not found in open trades")
        except Exception as e:  # noqa: BLE001
            return self._err(f"modify_order failed: {e}")

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        ib = self._connect()
        if ib is None:
            return self._err("Not connected to IBKR")
        try:
            for t in ib.openTrades():
                if str(t.order.orderId) == str(order_id):
                    ib.cancelOrder(t.order)
                    ib.sleep(0.3)
                    return self._ok({"order_id": order_id, "status": "cancel_sent"})
            return self._err(f"order {order_id} not found in open trades")
        except Exception as e:  # noqa: BLE001
            return self._err(f"cancel_order failed: {e}")

    # ------------------------------------------------------------------ #
    # market data / history  (SHARED CORE + yfinance fallback)
    # ------------------------------------------------------------------ #
    def get_quotes(self, symbols: str) -> Dict[str, Any]:
        """Last price per symbol. Comma-separated. IBKR snapshot, yfinance fallback."""
        syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        out: Dict[str, Any] = {}
        ib = self._connect()
        if ib is not None:
            try:
                for s in syms:
                    c = self._stock(s)
                    ib.qualifyContracts(c)
                    t = ib.reqMktData(c, "", True, False)
                    ib.sleep(0.4)
                    px = t.marketPrice() if t else None
                    if px and px == px:  # not NaN
                        out[s] = {"last_price": float(px), "source": "ibkr"}
            except Exception as e:  # noqa: BLE001
                logger.info("IBKR quotes error: %s -> yfinance", e)
        # yfinance fallback for anything missing
        missing = [s for s in syms if s not in out]
        for s in missing:
            df = fetch_daily_bars(s, date.today() - timedelta(days=7), date.today(),
                                  prefer="yfinance")
            if df is not None and not df.empty:
                out[s] = {"last_price": float(df["Close"].iloc[-1]), "source": "yfinance"}
        return self._ok(out)

    def get_history(self, symbol: str, resolution: str = "D",
                    range_from: str = None, range_to: str = None) -> Dict[str, Any]:
        """Daily history via the shared core (IBKR -> yfinance fallback).

        resolution is accepted for interface parity; only daily ('D'/'1D') is
        supported by the shared core today.
        """
        end = _parse_date(range_to) or date.today()
        start = _parse_date(range_from) or (end - timedelta(days=365 * 4))
        df = fetch_daily_bars(symbol, start, end, prefer="ibkr")
        if df is None or df.empty:
            return self._err(f"no history for {symbol}")
        candles = [
            [int(datetime(ts.year, ts.month, ts.day).timestamp()),
             float(r["Open"]), float(r["High"]), float(r["Low"]),
             float(r["Close"]), int(r["Volume"])]
            for ts, r in df.iterrows()
        ]
        return self._ok({"symbol": symbol, "candles": candles, "resolution": "D"})


def _is_float(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _parse_date(s) -> Optional[date]:
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
