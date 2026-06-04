"""Tests for the shared history core + IBKR broker fallback.

These run without TWS/Gateway: IBKR connection is refused, so every path must
fall back to yfinance and still return well-formed data. Network (yfinance) is
required; tests skip if it is unavailable.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.services.data.price_history_provider import fetch_daily_bars, COLUMNS
from src.services.brokers.ibkr import IBKRBrokerService

WINDOW = (date(2024, 1, 1), date(2024, 2, 1))


def _net_df(symbol="AAPL", prefer="yfinance"):
    return fetch_daily_bars(symbol, *WINDOW, prefer=prefer)


def test_shared_core_yfinance_shape():
    df = _net_df()
    if df is None:
        pytest.skip("no network / yfinance unavailable")
    assert list(df.columns) == COLUMNS
    assert len(df) > 10
    assert (df["High"] >= df["Low"]).all()


def test_ibkr_prefer_falls_back_to_yfinance():
    """prefer='ibkr' with no TWS running must transparently return yfinance data."""
    df = fetch_daily_bars("MSFT", *WINDOW, prefer="ibkr")
    if df is None:
        pytest.skip("no network / yfinance unavailable")
    assert list(df.columns) == COLUMNS
    assert len(df) > 10


def test_broker_test_connection_graceful_without_tws():
    b = IBKRBrokerService()
    res = b.test_connection()
    assert res["status"] == "error"
    assert "7497" in res["message"]


def test_broker_get_history_fallback():
    b = IBKRBrokerService()
    res = b.get_history("AAPL", range_from="2024-01-01", range_to="2024-01-15")
    if res["status"] != "success":
        pytest.skip("no network / yfinance unavailable")
    candles = res["data"]["candles"]
    assert len(candles) > 5
    # candle = [ts, o, h, l, c, vol]
    assert all(len(c) == 6 for c in candles)


def test_broker_place_order_without_tws_is_clean_error():
    b = IBKRBrokerService()
    res = b.place_order({"symbol": "AAPL", "side": "BUY", "qty": 1, "type": "MKT"})
    assert res["status"] == "error"
    assert "Not connected" in res["message"]
