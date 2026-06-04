"""Leveraged 3x-ETF momentum rotation — the high-CAGR search sleeve.

Rotate into the strongest 3x leveraged ETFs by momentum, gated by QQQ's 200d SMA
(cash in bear markets so the 3x decay/crash doesn't compound). This is the realistic
path to >60-100% CAGR: leverage applied to a momentum signal, not stock concentration.

Universe: src/data/symbols/leveraged_3x.csv (TQQQ/SOXL/TECL/FAS/UPRO/UDOW/TNA/...).
Signal  : blend = avg(21/63/126d return) by default; --signal ret for raw lookback.
Hold    : top-K equal-weight, weekly (default) or monthly.
Regime  : 100% cash when QQQ < 200d SMA (critical — 3x ETFs lose 70-90% in bears).
Costs   : $0 commission + 8 bps slippage; true daily-MTM drawdown.

WARNING: 3x ETFs carry extreme drawdown + volatility-decay risk. High backtest CAGR
here is leverage, not alpha — forward DD can exceed 60-80% even with the regime gate
(gap-throughs in 2020/2022). Survivorship also flatters (failed 3x ETFs delisted).
"""
from __future__ import annotations
import sys, argparse
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.models.india_ports_us.backtest import (  # noqa: E402  shared engine
    load_csv, load_panels, load_regime, simulate, momscore, build_rebal, _report,
)

LEV_CSV = str(ROOT / "src/data/symbols/leveraged_3x.csv")
DEFAULT_START = date(2016, 5, 24)
DEFAULT_END = date(2026, 5, 24)
DEFAULT_CAP = 1_000_000.0


def run(cl, dv, dates, start, end, capital, universe, top=2, signal="blend",
        siglb=63, weekly=True, trail=0.0, regime_on=None, regime=True, out_dir=None, tag=""):
    present = [s for s in universe if s in cl.columns]
    if weekly:
        rebal = build_rebal(dates, start, end, weekly=True); mid = None
    else:
        rebal, mid = build_rebal(dates, start, end, mid_month=False)
    run_dates = dates[dates >= pd.Timestamp(start)]

    def target_fn(di, d, pos, risk_on):
        rk = momscore(cl, di, signal, siglb).reindex(present)
        rk = rk[rk > 0].dropna().sort_values(ascending=False)
        if rk.empty:
            return {}
        picks = list(rk.index[:top])
        w = 1.0 / len(picks)
        return {s: w for s in picks}

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal, mid,
                                 regime_on=regime_on, regime=regime, trail=trail)
    _report(f"lev3x{tag}", res, trades, txns, out_dir)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--top", type=int, default=2)
    ap.add_argument("--signal", choices=["ret", "blend"], default="blend")
    ap.add_argument("--siglb", type=int, default=63)
    ap.add_argument("--monthly", action="store_true", help="monthly rebalance (default weekly)")
    ap.add_argument("--trail", type=float, default=0.0)
    ap.add_argument("--no-regime", dest="regime", action="store_false")
    ap.add_argument("--regime-sym", default="QQQ")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--out", default=None)
    ap.set_defaults(regime=True)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)

    universe = load_csv(LEV_CSV)
    syms = sorted(set(universe) | {a.regime_sym})
    cl, dv = load_panels(syms, s, e)
    dates = cl.index
    reg = load_regime(a.regime_sym, dates, s, e) if a.regime else None

    if a.sweep:
        for top in (1, 2, 3):
            for sig, lb in (("blend", 63), ("ret", 63), ("ret", 21)):
                for wk in (True, False):
                    run(cl, dv, dates, s, e, a.capital, universe, top=top, signal=sig,
                        siglb=lb, weekly=wk, regime_on=reg, regime=a.regime,
                        tag=f" top{top} {sig}{lb} {'wk' if wk else 'mo'}")
        return

    run(cl, dv, dates, s, e, a.capital, universe, top=a.top, signal=a.signal,
        siglb=a.siglb, weekly=not a.monthly, trail=a.trail, regime_on=reg,
        regime=a.regime, out_dir=a.out,
        tag=f"_top{a.top}_{a.signal}{'_reg' if a.regime else ''}")


if __name__ == "__main__":
    main()
