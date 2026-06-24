"""Pure (DB-free) splice helpers.

This module holds pure helper functions used to join an older real-yfinance
price segment to a more recent eToro price segment into one continuous series.
It is deliberately kept independent of the backtest DB layer so the splicing
logic can be unit-tested in isolation without any database, network, or I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trading_days(dates) -> pd.DatetimeIndex:
    """Sorted, de-duplicated, weekday-only DatetimeIndex from any date iterable."""
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Index(dates)).unique()).sort_values()
    return idx[idx.weekday < 5]
