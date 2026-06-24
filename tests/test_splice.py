from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from tools.shared.splice import trading_days


def test_trading_days_dedups_and_drops_weekends():
    raw = ["2024-01-05","2024-01-05","2024-01-06","2024-01-07","2024-01-08"]
    idx = trading_days(pd.to_datetime(pd.Series(raw)))
    assert list(idx.strftime("%Y-%m-%d")) == ["2024-01-05", "2024-01-08"]
    assert idx.is_monotonic_increasing


from tools.shared.splice import splice_ratio
JOIN = pd.Timestamp("2022-05-24")
def _series(d):
    return pd.Series(list(d.values()), index=pd.to_datetime(list(d.keys())))
def test_ratio_ok_uses_latest_common_day_le_join():
    old = _series({"2022-05-19": 10.0, "2022-05-20": 11.0, "2022-05-25": 99.0})
    new = _series({"2022-05-20": 22.0, "2022-05-24": 30.0})
    r, status = splice_ratio(old, new, JOIN)
    assert status == "ok"
    assert r == pytest.approx(22.0 / 11.0)
def test_ratio_only_old_when_no_new_anchor():
    r, status = splice_ratio(_series({"2022-05-20": 11.0}), _series({}), JOIN)
    assert status == "only_old" and r == 1.0
def test_ratio_only_new_when_no_old():
    r, status = splice_ratio(_series({}), _series({"2022-05-24": 30.0}), JOIN)
    assert status == "only_new" and r == 1.0
def test_ratio_no_common_anchor_keeps_unscaled():
    r, status = splice_ratio(_series({"2022-05-18": 11.0}), _series({"2022-05-20": 22.0}), JOIN)
    assert status == "no_anchor" and r == 1.0
def test_ratio_bad_when_zero_or_out_of_bounds():
    r, status = splice_ratio(_series({"2022-05-20": 0.0}), _series({"2022-05-20": 22.0}), JOIN)
    assert status == "bad_ratio"
def test_ratio_large_but_finite_is_ok_for_scaled_tickers():
    r, status = splice_ratio(_series({"2022-05-20": 1900.0}), _series({"2022-05-20": 190.0}), JOIN)
    assert status == "ok" and r == pytest.approx(0.1)
