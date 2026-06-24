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
    matches the NEW (eToro) segment at the join, using ADJACENT-BOUNDARY anchoring
    (the two buckets do not overlap — eToro owns date >= join, yfinance_real owns
    date < join):
      anchor_old = last old bar with date <  join
      anchor_new = first new bar with date >= join
      ratio      = anchor_new / anchor_old
    status:
      ok        -> finite ratio in [lo, hi]; scale old by ratio
      only_new  -> no old bars before join (nothing to scale) -> 1.0
      only_old  -> no new bars at/after join (no eToro anchor) -> 1.0
      bad_ratio -> anchor_old == 0 or ratio non-finite / <=0 / outside [lo,hi]; do NOT scale
    """
    o = old_close.dropna()
    n = new_close.dropna()
    o_pre = o[o.index < join]
    n_post = n[n.index >= join]
    if o_pre.empty:
        return 1.0, "only_new"
    if n_post.empty:
        return 1.0, "only_old"
    anchor_old = float(o_pre.iloc[-1])
    anchor_new = float(n_post.iloc[0])
    if anchor_old == 0:
        return float("inf"), "bad_ratio"
    r = anchor_new / anchor_old
    if not np.isfinite(r) or r <= 0 or not (lo <= r <= hi):
        return r, "bad_ratio"
    return r, "ok"


_OHLC = ["open", "high", "low", "close"]

def splice_symbol(old_df: pd.DataFrame, new_df: pd.DataFrame, join: pd.Timestamp):
    """Join one symbol's older real-yfinance OHLCV (`old_df`) to its recent eToro
    OHLCV (`new_df`) into a continuous series. Both frames have columns
    [date, open, high, low, close, volume] with a datetime `date`.
    Old rows (date < join) are scaled by the splice ratio; new rows (date >= join)
    pass through. Volume is never scaled. Returns (df, ratio, status).
    On non-'ok' status old rows pass through unscaled — callers must check `status`."""
    o = old_df.copy()
    n = new_df.copy()
    _empty = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    oc = o.set_index("date")["close"] if not o.empty else _empty
    nc = n.set_index("date")["close"] if not n.empty else _empty
    ratio, status = splice_ratio(oc, nc, join)
    older = o[o["date"] < join].copy()
    recent = n[n["date"] >= join].copy()
    if status == "ok" and not older.empty:
        older[_OHLC] = older[_OHLC] * ratio
    out = pd.concat([older, recent], ignore_index=True)
    out = out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    return out, ratio, status
