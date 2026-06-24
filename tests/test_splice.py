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


from tools.shared.splice import splice_symbol
def _ohlcv(rows):
    df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume"])
    df["date"] = pd.to_datetime(df["date"])
    return df
def test_splice_symbol_scales_old_and_keeps_new():
    old = _ohlcv([("2022-05-19",10,10,10,10,100),("2022-05-20",11,11,11,11,100),("2022-05-25",12,12,12,12,100)])
    new = _ohlcv([("2022-05-20",22,22,22,22,200),("2022-05-24",30,30,30,30,200),("2022-05-25",33,33,33,33,200)])
    out, ratio, status = splice_symbol(old, new, pd.Timestamp("2022-05-24"))
    assert status == "ok" and ratio == pytest.approx(2.0)
    out = out.set_index("date")
    assert out.loc["2022-05-19","close"] == pytest.approx(20.0)
    assert out.loc["2022-05-20","close"] == pytest.approx(22.0)
    assert out.loc["2022-05-24","close"] == pytest.approx(30.0)
    assert out.loc["2022-05-19","volume"] == 100
    assert out.index.is_unique and out.index.is_monotonic_increasing
def test_splice_symbol_returns_unchanged_within_segment_returns():
    old = _ohlcv([("2022-05-18",10,10,10,10,1),("2022-05-19",12,12,12,12,1),("2022-05-20",11,11,11,11,1)])
    new = _ohlcv([("2022-05-20",55,55,55,55,1),("2022-05-24",60,60,60,60,1)])
    out, ratio, status = splice_symbol(old, new, pd.Timestamp("2022-05-24"))
    seg = out[out["date"] < "2022-05-24"].set_index("date")["close"]
    raw = old.set_index("date")["close"]
    assert np.allclose(seg.pct_change().dropna().values, raw.pct_change().dropna().values)
def test_splice_symbol_only_new_when_old_empty():
    new = _ohlcv([("2022-05-24",30,30,30,30,200),("2022-05-25",33,33,33,33,200)])
    out, ratio, status = splice_symbol(_ohlcv([]), new, pd.Timestamp("2022-05-24"))
    assert status == "only_new"
    out = out.set_index("date")
    assert out.loc["2022-05-24","close"] == pytest.approx(30.0)
    assert out.loc["2022-05-25","close"] == pytest.approx(33.0)
    assert list(out.index.strftime("%Y-%m-%d")) == ["2022-05-24", "2022-05-25"]
def test_splice_symbol_only_old_when_new_empty():
    old = _ohlcv([("2022-05-19",10,10,10,10,100),("2022-05-20",11,11,11,11,100)])
    out, ratio, status = splice_symbol(old, _ohlcv([]), pd.Timestamp("2022-05-24"))
    assert status == "only_old" and ratio == pytest.approx(1.0)
    out = out.set_index("date")
    assert out.loc["2022-05-19","close"] == pytest.approx(10.0)
    assert out.loc["2022-05-20","close"] == pytest.approx(11.0)
def test_splice_symbol_both_empty():
    out, ratio, status = splice_symbol(_ohlcv([]), _ohlcv([]), pd.Timestamp("2022-05-24"))
    assert status == "only_new"
    assert out.empty
def test_splice_symbol_bad_ratio_passes_old_through_unscaled():
    old = _ohlcv([("2022-05-19",10,10,10,10,100),("2022-05-20",0,0,0,0,100)])
    new = _ohlcv([("2022-05-20",22,22,22,22,200),("2022-05-24",30,30,30,30,200)])
    out, ratio, status = splice_symbol(old, new, pd.Timestamp("2022-05-24"))
    assert status == "bad_ratio"
    out = out.set_index("date")
    assert out.loc["2022-05-19","close"] == pytest.approx(10.0)
    assert out.loc["2022-05-20","close"] == pytest.approx(0.0)
    assert out.loc["2022-05-24","close"] == pytest.approx(30.0)
