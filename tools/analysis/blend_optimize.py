"""Grid-search blend weights over N model equity curves to maximize an objective
(Calmar by default). Reports the best weight vector + its CAGR/MaxDD/Calmar, and a
few notable alternatives (max CAGR, min DD).

Usage:
  python tools/analysis/blend_optimize.py MOM=a.csv TQQQ=b.csv BRK=c.csv \
      [--objective calmar|cagr|mar30] [--step 0.05] [--min-weight 0.0]

`mar30` = CAGR subject to a soft penalty when MaxDD > 30% (favors the <30% DD goal).
"""
from __future__ import annotations
import argparse, itertools
from pathlib import Path
import numpy as np
import pandas as pd


def load_curve(path: str) -> pd.Series:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]])
    return df.set_index(df.columns[0])["equity"]


def stats(eq: pd.Series):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1) * 100
    mdd = float(-((eq - eq.cummax()) / eq.cummax()).min() * 100)
    return cagr, mdd, cagr / max(0.01, mdd)


def weight_grid(n, step, min_w):
    ticks = int(round(1.0 / step))
    for combo in itertools.product(range(ticks + 1), repeat=n - 1):
        if sum(combo) > ticks:
            continue
        last = ticks - sum(combo)
        w = np.array([*combo, last], dtype=float) / ticks
        if (w >= min_w - 1e-9).all():
            yield w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--objective", choices=["calmar", "cagr", "mar30"], default="calmar")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--min-weight", type=float, default=0.0)
    a = ap.parse_args()

    names, curves = [], []
    for sp in a.specs:
        n, p = sp.split("=", 1)
        names.append(n); curves.append(load_curve(p))
    rets = pd.concat([c.pct_change() for c in curves], axis=1, join="inner")
    rets.columns = names
    rets = rets.dropna()
    idx = rets.index

    def score(w):
        eq = (1 + (rets * w).sum(axis=1)).cumprod()
        cg, dd, cal = stats(eq)
        if a.objective == "calmar":
            obj = cal
        elif a.objective == "cagr":
            obj = cg
        else:  # mar30: CAGR minus steep penalty above 30% DD
            obj = cg - max(0.0, dd - 30.0) * 3.0
        return obj, cg, dd, cal

    best = None; max_cagr = None; min_dd = None
    for w in weight_grid(len(names), a.step, a.min_weight):
        obj, cg, dd, cal = score(w)
        rec = (obj, cg, dd, cal, w)
        if best is None or obj > best[0]:
            best = rec
        if max_cagr is None or cg > max_cagr[1]:
            max_cagr = rec
        if min_dd is None or dd < min_dd[2]:
            min_dd = rec

    def show(tag, rec):
        _, cg, dd, cal, w = rec
        wt = "  ".join(f"{n}={x:.2f}" for n, x in zip(names, w))
        print(f"{tag:<14} CAGR {cg:>7.2f}%  MaxDD {dd:>6.2f}%  Calmar {cal:>5.2f}   [{wt}]")

    print(f"\n=== weight optimization ({idx[0].date()} -> {idx[-1].date()}, "
          f"{(idx[-1]-idx[0]).days/365.25:.2f}y, objective={a.objective}, step={a.step}) ===")
    show(f"best {a.objective}", best)
    show("max CAGR", max_cagr)
    show("min DD", min_dd)


if __name__ == "__main__":
    main()
