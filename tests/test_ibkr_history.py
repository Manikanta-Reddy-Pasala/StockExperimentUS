"""Tests for the IBKR broker — order/connection role only.

IBKR is no longer a data source (eToro is the sole data source). These run
without TWS/Gateway and without eToro keys: connection + trading calls must
return clean errors, and the data delegation methods must degrade gracefully
(no data -> error) rather than raise.
"""
from __future__ import annotations

import os

import pytest

from src.services.brokers.ibkr import IBKRBrokerService

_HAVE_KEYS = bool(os.environ.get("ETORO_API_KEY") and os.environ.get("ETORO_USER_KEY"))


def test_broker_test_connection_graceful_without_tws():
    b = IBKRBrokerService()
    res = b.test_connection()
    assert res["status"] == "error"
    assert "7497" in res["message"]


def test_broker_place_order_without_tws_is_clean_error():
    b = IBKRBrokerService()
    res = b.place_order({"symbol": "AAPL", "side": "BUY", "qty": 1, "type": "MKT"})
    assert res["status"] == "error"
    assert "Not connected" in res["message"]


def test_broker_get_history_delegates_to_etoro():
    """History delegates to the eToro shared core. Without keys -> clean error;
    with keys -> well-formed candles."""
    b = IBKRBrokerService()
    res = b.get_history("AAPL", range_from="2024-01-01", range_to="2024-01-15")
    if not _HAVE_KEYS:
        assert res["status"] == "error"
        return
    if res["status"] != "success":
        pytest.skip("eToro returned no data for window")
    candles = res["data"]["candles"]
    assert all(len(c) == 6 for c in candles)  # [ts, o, h, l, c, vol]
