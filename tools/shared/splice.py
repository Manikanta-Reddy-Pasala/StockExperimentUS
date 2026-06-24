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


def splice_ratio(old_close: pd.Series, new_close: pd.Series, join: pd.Timestamp,
                 lo: float = 1e-3, hi: float = 1e3):
    """Return (ratio, status) to scale the OLD (yfinance_real) segment so its level
    matches the NEW (eToro) segment at the join.

    ratio = new@anchor / old@anchor, anchor = latest trading day <= join present in
    BOTH series. status: ok | only_new | only_old | no_anchor | bad_ratio."""
    o = old_close.dropna()
    o = o[o.index <= join]
    n = new_close.dropna()
    n = n[n.index <= join]
    if o.empty and n.empty:
        return 1.0, "only_new"
    if o.empty:
        return 1.0, "only_new"
    if n.empty:
        return 1.0, "only_old"
    common = o.index.intersection(n.index)
    if len(common) == 0:
        return 1.0, "no_anchor"
    anchor = common.max()
    denom = float(o.loc[anchor])
    if denom == 0:
        return float("inf"), "bad_ratio"
    r = float(n.loc[anchor]) / denom
    if not np.isfinite(r) or r <= 0 or not (lo <= r <= hi):
        return r, "bad_ratio"
    return r, "ok"
