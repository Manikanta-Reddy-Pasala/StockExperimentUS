"""Tests for the eToro daily-bar source — the sole data source in the shared core.

Without ETORO_API_KEY/ETORO_USER_KEY the source returns None (there is no
yfinance/IBKR fallback). A live smoke test runs only when both keys are present.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from src.services.data.price_history_provider import (
    fetch_daily_bars,
    _etoro_daily_bars,
    source_for,
    COLUMNS,
)

WINDOW = (date(2024, 1, 1), date(2024, 2, 1))
_HAVE_KEYS = bool(os.environ.get("ETORO_API_KEY") and os.environ.get("ETORO_USER_KEY"))


@pytest.mark.skipif(_HAVE_KEYS, reason="keys present; this asserts the unconfigured path")
def test_etoro_returns_none_without_keys():
    """No creds -> eToro source is a no-op (None), never raises. No fallback."""
    assert _etoro_daily_bars("AAPL", *WINDOW) is None
    assert fetch_daily_bars("AAPL", *WINDOW) is None
    assert source_for("AAPL", *WINDOW) == "none"


@pytest.mark.skipif(not _HAVE_KEYS, reason="eToro keys not in env")
def test_etoro_live_recent_window():
    """Live smoke test: recent daily bars come straight from eToro, correct shape."""
    end = date.today()
    df = _etoro_daily_bars("AAPL", end - timedelta(days=20), end)
    assert df is not None and not df.empty
    assert list(df.columns) == COLUMNS
    assert (df["High"] >= df["Low"]).all()


@pytest.mark.skipif(not _HAVE_KEYS, reason="eToro keys not in env")
def test_etoro_is_default_path():
    """fetch_daily_bars routes to eToro with no source argument."""
    end = date.today()
    df = fetch_daily_bars("MSFT", end - timedelta(days=20), end)
    assert df is not None
    assert list(df.columns) == COLUMNS
    assert source_for("MSFT", end - timedelta(days=20), end) == "etoro"
