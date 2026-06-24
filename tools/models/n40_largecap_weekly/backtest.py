"""N40 — large-cap WEEKLY momentum (top-3, blend signal, QQQ regime). LOCKED config.

The improved US port of the India `n40` archetype. The faithful India rule (single
large-cap name, weekly) bled to 62-80% DD on US; the IMPROVED config below
(diversify to top-3 + the v2 "blend" momentum signal + a QQQ 200d regime gate)
turns it into a real ≥60%-CAGR large-cap sleeve — see
`exports/backtests/us/INDIA_PORTS_IMPROVED.md`.

LOCKED config (this file's defaults):
  universe  : top-40 by 20d ADV ∩ Nasdaq-100  (liquid large caps)
  signal    : blend = avg(21/63/126-day return)  (same alpha as the v2 MOM sleeve)
  hold      : top-3 equal-weight, rebalanced WEEKLY (first trading day each ISO week)
  regime    : 100% cash when QQQ < 200d SMA
  costs     : $0 commission (IBKR Lite) + 8 bps slippage; true daily-MTM drawdown

NOTE (book role): this is essentially a higher-turnover twin of the v2 MOM sleeve
(large-cap blend momentum) — expect HIGH correlation to MOM, so it raises CAGR/turnover
but does NOT diversify the 3-model book. Use as a MOM variant, not a low-corr sleeve.

Measured (Nasdaq-100, locked config):
  3yr  2023-05→2026-05 : ~132% CAGR / 38% DD / Calmar 3.4
  5yr  2021-03→2026-05 : ~53%  CAGR / 47% DD / Calmar 1.1
Run:
  PYTHONPATH=. python tools/models/n40_largecap_weekly/backtest.py \
      --from 2023-05-24 --to 2026-05-24 --out exports/backtests/us/n40_largecap_weekly/3yr
"""
from __future__ import annotations
import sys, argparse
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.models.india_ports_us.backtest import (  # noqa: E402  shared core engine
    load_csv, load_panels, load_panels_spliced, load_open, load_regime, run_n40, N100_CSV,
)

DEFAULT_START = date(2023, 5, 24)
DEFAULT_END = date(2026, 5, 24)
DEFAULT_CAP = 1_000_000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--universe-csv", default=N100_CSV, help="large-cap pool (default Nasdaq-100)")
    ap.add_argument("--membership-csv", default=None,
                    help="point-in-time index membership CSV (symbol,start_date,end_date). "
                         "When set, the universe is the FULL --universe-csv panel gated to "
                         "actual members at each rebalance (survivorship-correct). When unset, "
                         "behavior is unchanged (universe = panel ∩ Nasdaq-100).")
    ap.add_argument("--regime-sym", default="QQQ")
    # locked knobs (overridable for research)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--topadv", type=int, default=40)
    ap.add_argument("--signal", choices=["ret", "blend"], default="blend")
    ap.add_argument("--trail", type=float, default=0.0)
    ap.add_argument("--lev", type=float, default=1.0,
                    help="margin multiplier on target weights (1=cash; >1 borrows). "
                         "WARNING: lev>=2 => 75-90%% DD = margin-call territory.")
    ap.add_argument("--margin-apr", type=float, default=0.06, help="annual borrow cost on margin")
    ap.add_argument("--no-regime", dest="regime", action="store_false")
    ap.add_argument("--txn-charge", type=float, default=1.0,
                    help="flat $ per-transaction fee deducted on EVERY fill, both "
                         "buys and sells (eToro charges $1/txn each side). 0 = off.")
    ap.add_argument("--out", default=None)
    ap.add_argument("--legacy-fills", action="store_true",
                    help="old same-close fills (no next-open / no T+1 settlement)")
    ap.add_argument("--decide-prior", action="store_true",
                    help="scheme B: decide on the bar before the rebal day (sell ON rebal day)")
    ap.add_argument("--extended", action="store_true",
                    help="10yr history: splice real-yfinance backfill (pre-join) to "
                         "eToro (post-join) per symbol")
    ap.add_argument("--join", default="2022-05-18",
                    help="splice date: eToro authoritative on/after this day")
    ap.set_defaults(regime=True)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)

    syms = sorted(set(load_csv(a.universe_csv)))
    cl, dv = (load_panels_spliced(syms, s, e, join=a.join) if a.extended
              else load_panels(syms, s, e))
    op = load_open(syms, s, e, cl)
    dates = cl.index
    reg = load_regime(a.regime_sym, dates, s, e,
                      buckets=("yfinance", "yfinance_real") if a.extended else ("yfinance",),
                      join=a.join) if a.regime else None

    run_n40(cl, dv, dates, s, e, a.capital, topadv=a.topadv, top=a.top,
            signal=a.signal, trail=a.trail, out_dir=a.out,
            regime_on=reg, regime=a.regime, lev=a.lev,
            margin_apr=(a.margin_apr if a.lev > 1 else 0.0),
            membership_csv=a.membership_csv, txn_charge=a.txn_charge,
            op=(None if a.legacy_fills else op), decide_prior=a.decide_prior,
            tag="_top%d_%s%s%s%s" % (a.top, a.signal, "_reg" if a.regime else "",
                                     ("_lev%g" % a.lev) if a.lev != 1 else "",
                                     "_pit" if a.membership_csv else ""))


if __name__ == "__main__":
    main()
