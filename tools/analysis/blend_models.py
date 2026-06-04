"""Blend N model equity curves into a daily-rebalanced portfolio; report combined
CAGR / true daily MaxDD / Calmar and the pairwise daily-return correlation matrix
(low/negative correlation => diversification cuts drawdown).

Usage:
  python tools/analysis/blend_models.py NAME=path/equity_curve.csv [NAME2=... ...] \
      [--weights 0.5,0.3,0.2]
"""
from __future__ import annotations
import sys, argparse
from pathlib import Path
import numpy as np
import pandas as pd


def load_curve(path: str) -> pd.Series:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    dcol = df.columns[0]
    df[dcol] = pd.to_datetime(df[dcol])
    return df.set_index(dcol)["equity"]


def stats(equity: pd.Series):
    yrs = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / yrs) - 1) * 100
    peak = equity.cummax()
    mdd = float(-((equity - peak) / peak).min() * 100)
    return cagr, mdd, cagr / max(0.01, mdd), yrs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+", help="NAME=path/equity_curve.csv")
    ap.add_argument("--weights", default=None, help="comma weights, default equal")
    ap.add_argument("--lev", type=float, default=1.0,
                    help="margin multiplier on the blend (>1 borrows). WARNING: lev>=2 "
                         "=> ~70-90%% DD = margin-call/liquidation territory.")
    ap.add_argument("--margin-apr", type=float, default=0.06, help="annual borrow cost on margin")
    ap.add_argument("--vol-target", type=float, default=0.0,
                    help="annualized vol target (e.g. 0.50). Scales daily leverage by "
                         "target/realized-vol (de-levers in crashes). Overrides --lev.")
    ap.add_argument("--max-lev", type=float, default=3.0, help="cap on vol-target leverage")
    ap.add_argument("--vol-window", type=int, default=20, help="realized-vol lookback (days)")
    a = ap.parse_args()

    names, curves = [], []
    for sp in a.specs:
        name, path = sp.split("=", 1)
        names.append(name); curves.append(load_curve(path))

    rets = pd.concat([c.pct_change() for c in curves], axis=1, join="inner")
    rets.columns = names
    rets = rets.dropna()

    if a.weights:
        w = np.array([float(x) for x in a.weights.split(",")])
    else:
        w = np.ones(len(names)) / len(names)
    w = w / w.sum()

    blend_ret = (rets * w).sum(axis=1)
    mc = a.margin_apr / 252.0
    if a.vol_target > 0:                   # vol-targeted leverage (de-levers in crashes)
        rv = blend_ret.rolling(a.vol_window).std() * np.sqrt(252)
        lev_t = (a.vol_target / rv).clip(0, a.max_lev).shift(1).fillna(1.0)
        blend_ret = blend_ret * lev_t - (lev_t - 1).clip(lower=0) * mc
    elif a.lev != 1.0:                     # flat margin leverage + daily borrow cost
        blend_ret = blend_ret * a.lev - max(0.0, a.lev - 1.0) * mc
    blend_eq = (1 + blend_ret).cumprod()

    print("\n=== individual (on common dates) ===")
    print(f"{'model':<16} {'CAGR%':>8} {'MaxDD%':>8} {'Calmar':>7}")
    for n, c in zip(names, curves):
        c2 = c.reindex(rets.index).dropna()
        cg, dd, cal, _ = stats(c2)
        print(f"{n:<16} {cg:>8.2f} {dd:>8.2f} {cal:>7.2f}")

    cg, dd, cal, yrs = stats(blend_eq)
    wtxt = ",".join(f"{x:.2f}" for x in w)
    print(f"\n=== BLEND  weights [{wtxt}]  ({rets.index[0].date()} -> {rets.index[-1].date()}, {yrs:.2f}y) ===")
    print(f"{'BLEND':<16} {cg:>8.2f} {dd:>8.2f} {cal:>7.2f}")

    print("\n=== daily-return correlation (lower = better diversification) ===")
    corr = rets.corr()
    print(corr.round(2).to_string())


if __name__ == "__main__":
    main()
