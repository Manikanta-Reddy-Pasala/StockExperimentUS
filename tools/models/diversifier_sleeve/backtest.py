"""Diversifier sleeve — low-correlation all-weather basket to CUT book drawdown.

Holds the strongest of a managed-futures / commodity / dollar / gold / bond basket
by momentum. These assets have ~0.05-0.20 correlation to the Nasdaq momentum book,
so blending a slice in cuts the book's drawdown STRUCTURALLY (not just by de-risking)
— the one real DD lever beyond the regime gate. Standalone CAGR is modest by design;
its value is the near-zero correlation.

Universe: src/data/symbols/diversifier_etfs.csv (DBMF/KMLM/CTA/DBC/PDBC/UUP/GLD/TLT).
Signal  : blend = avg(63/126d return). Hold top-K equal-weight, monthly. NO regime gate
          (all-weather — managed futures should be on in equity bears, that's the point).
Costs   : $0 commission + 8 bps slippage; true daily-MTM DD.

NOTE: DBMF (2019)/KMLM (2020)/CTA (2022) have short histories — long-cycle (2008/2018)
behaviour is untested. GLD/TLT/DBC/UUP go back further. Treat pre-2020 as partial.
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
    load_csv, load_panels, simulate, momscore, build_rebal, _report,
)

DIV_CSV = str(ROOT / "src/data/symbols/diversifier_etfs.csv")
DEFAULT_START = date(2020, 1, 1)
DEFAULT_END = date(2026, 5, 24)
DEFAULT_CAP = 1_000_000.0


def run(cl, dates, start, end, capital, universe, top=4, siglb=126, out_dir=None, tag=""):
    present = [s for s in universe if s in cl.columns]
    rebal, mid = build_rebal(dates, start, end, mid_month=False)
    run_dates = dates[dates >= pd.Timestamp(start)]

    def target_fn(di, d, pos, risk_on):
        rk = momscore(cl, di, "blend", siglb).reindex(present)
        rk = rk[rk > 0].dropna().sort_values(ascending=False)
        if rk.empty:
            return {}                       # nothing trending up -> cash
        picks = list(rk.index[:top])
        return {s: 1.0 / len(picks) for s in picks}

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal, mid,
                                 regime=False)
    _report(f"diversifier{tag}", res, trades, txns, out_dir)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--siglb", type=int, default=126)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    universe = load_csv(DIV_CSV)
    cl, dv = load_panels(universe, s, e)
    run(cl, cl.index, s, e, a.capital, universe, top=a.top, siglb=a.siglb,
        out_dir=a.out, tag=f"_top{a.top}")


if __name__ == "__main__":
    main()
