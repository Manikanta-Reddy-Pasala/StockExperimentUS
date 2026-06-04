"""US live executor — compute today's book target and place IBKR orders.

India-parity live path (replaces the old Fyers executor): one tool that
  1. computes today's target basket for a US book model (default: N40 large-cap
     weekly = top-3 ADV∩Nasdaq-100 by blend momentum, QQQ 200d regime gate),
  2. reads current IBKR positions + net liquidation value,
  3. diffs target vs held -> BUY/SELL share deltas,
  4. prints the plan (dry-run) and, with --live, places market orders via IBKR.

Data comes from the same DB the backtests use (data_source='yfinance'); signal
logic reuses the backtest core so live and backtest cannot drift.

Usage:
  PYTHONPATH=. python tools/live/us_executor.py                 # dry-run, N40 book
  PYTHONPATH=. python tools/live/us_executor.py --live          # actually place (paper 7497)
  PYTHONPATH=. python tools/live/us_executor.py --capital 5000  # size to a $5k book
"""
from __future__ import annotations
import sys, argparse, json
from pathlib import Path
from datetime import date, timedelta

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.models.india_ports_us.backtest import (  # noqa: E402  shared signal core
    load_csv, load_panels, load_regime, momscore, adv_pool, N100_CSV,
)


def n40_target(asof: date, topadv=40, top=3, signal="blend", regime_sym="QQQ"):
    """Today's N40 target weights {symbol: weight} (empty = go to cash)."""
    syms = sorted(set(load_csv(N100_CSV)))
    start = asof - timedelta(days=420)
    cl, dv = load_panels(syms, start, asof)
    if cl.empty:
        return {}, "no data"
    di = len(cl.index) - 1
    reg = load_regime(regime_sym, cl.index, start, asof)
    if not bool(reg.iloc[di]):
        return {}, f"regime OFF ({regime_sym} < 200d) -> cash"
    n100 = [s for s in cl.columns if s in set(load_csv(N100_CSV))]
    cand = adv_pool(dv, di, n100, topadv)
    rk = momscore(cl, di, signal, 63).reindex(cand)
    rk = rk[rk > 0].dropna().sort_values(ascending=False)
    picks = list(rk.index[:top])
    if not picks:
        return {}, "no positive-momentum names -> cash"
    w = 1.0 / len(picks)
    return {s: w for s in picks}, f"regime ON, top-{top}: {picks}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="n40", choices=["n40"])
    ap.add_argument("--capital", type=float, default=None,
                    help="book size $; default = IBKR NetLiquidation")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--live", action="store_true", help="actually place orders (default dry-run)")
    a = ap.parse_args()
    asof = date.fromisoformat(a.asof)

    target_w, why = n40_target(asof)
    print(f"[signal] {a.model} as of {asof}: {why}")

    from src.services.brokers.ibkr import get_ibkr_service
    ib = get_ibkr_service()

    # account value + current positions
    nav = a.capital
    funds = ib.get_funds()
    if nav is None and funds.get("status") == "success":
        nav = funds["data"].get("NetLiquidation")
    if nav is None:
        print("[warn] no NAV (TWS down + no --capital); using $100000 placeholder for the plan")
        nav = 100_000.0

    held = {}
    pos = ib.get_positions()
    if pos.get("status") == "success":
        held = {p["symbol"]: p["quantity"] for p in pos["data"]}
    else:
        print(f"[warn] IBKR positions unavailable ({pos.get('message')}); assuming flat")

    # last prices for target symbols (via shared history core / IBKR->yfinance)
    from src.services.data.price_history_provider import fetch_daily_bars
    plan = []
    target_sym = set(target_w) | set(held)
    for s in sorted(target_sym):
        df = fetch_daily_bars(s, asof - timedelta(days=7), asof, prefer="ibkr")
        px = float(df["Close"].iloc[-1]) if df is not None and not df.empty else None
        tgt_val = target_w.get(s, 0.0) * nav
        tgt_sh = (tgt_val / px) if px else 0.0
        cur_sh = held.get(s, 0.0)
        dsh = round(tgt_sh - cur_sh, 4)
        if px and abs(dsh) * px >= max(1.0, 0.001 * nav):   # skip dust
            plan.append({"symbol": s, "side": "BUY" if dsh > 0 else "SELL",
                         "qty": abs(dsh), "price": px,
                         "cur": cur_sh, "target": round(tgt_sh, 4)})

    print(f"[plan] NAV ${nav:,.0f}  orders: {len(plan)}")
    for o in plan:
        print(f"  {o['side']:4} {o['qty']:>10.2f} {o['symbol']:6} @ ~${o['price']:.2f} "
              f"(cur {o['cur']:.2f} -> {o['target']:.2f})")

    if not a.live:
        print("[dry-run] no orders placed. Re-run with --live to execute (IBKR paper 7497).")
        return 0
    if not plan:
        print("[live] nothing to do.")
        return 0
    print("[live] placing market orders via IBKR...")
    for o in plan:
        res = ib.place_order({"symbol": o["symbol"], "side": o["side"],
                              "qty": o["qty"], "type": "MKT"})
        print(f"  {o['side']} {o['symbol']}: {res.get('status')} {res.get('data', res.get('message'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
