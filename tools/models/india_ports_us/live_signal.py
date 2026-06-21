"""Retest S&P 500 WEEKLY — OBSERVER-MODE live signal generator.

Signal-only. Writes a target-holdings JSON; places NO orders, invokes NO
executor. This is the live shadow of the India `retest` engine ported to the
S&P 500 (run via tools/models/india_ports_us/backtest.py run_retest, top-2,
weekly, QQQ 200d regime, PIT-gated to actual S&P 500 members each bar).

Strategy (LOCKED — identical to the backtest's selection rule):
  universe : broad nasdaq500 pool, PIT-restricted to S&P 500 members each bar
             via src/data/symbols/sp500_membership.csv
  candidate: top-120 by trailing-20d ADV from that PIT universe
  signal   : 126-day return (ret); retain held names still in the top-4 rank,
             then fill up to K=2 with the highest-ranked names sitting within
             20% above their 20-EMA (pullback/retest)
  hold     : top-2 equal-weight, rebalanced WEEKLY (first trading day of ISO week)
  regime   : 100% cash when the regime symbol (QQQ) < its 200d SMA

The selection logic is REUSED from the backtest via
`tools.models.india_ports_us.backtest.pick_retest_holdings` — do NOT duplicate
it here, so live and backtest can never drift.

Data: historical_data, data_source='yfinance' (eToro-sourced label), plain US
tickers (AAPL). QQQ present for the regime gate.

Usage (dry/observer):
  PYTHONPATH=. python tools/models/india_ports_us/live_signal.py \
    --universe-csv src/data/symbols/nasdaq500.csv \
    --membership-csv src/data/symbols/sp500_membership.csv \
    --model-name retest_sp500 \
    --signals-out /app/logs/retest_observer/signals/$(date +%F)_retest_sp500.json \
    --force
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# Reuse the backtest's shared engine + selection rule so live can't diverge.
from tools.models.india_ports_us.backtest import (  # noqa: E402
    get_engine, load_csv, pick_retest_holdings,
)
from tools.shared.us_index_membership import (  # noqa: E402
    load_membership, eligible_at,
)

log = logging.getLogger("retest_observer_signal")

# Locked knobs (match the backtest defaults for run_retest).
K = 2               # top-2 holdings
POOL = 120          # top-120 ADV candidate pool
RETAIN = 4          # held names retained while in top-4 rank
MOM_LB = 126        # 126-day momentum lookback
EMA = 20            # retest EMA span
BAND = 0.20         # within 20% above EMA = retest zone
SIGNAL = "blend"   # blend (avg 21/63/126d) > raw 126d ret: 112% vs 98% CAGR (5yr PIT), same 34% DD, Calmar 3.30
REGIME_SMA = 200
DATA_SOURCE = "yfinance"


def is_weekly_rebalance_day(today: datetime) -> bool:
    """True on the first weekday (Monday) of the current ISO week.

    Mirrors the backtest's weekly rebalance (first trading day each ISO week).
    Observer-only — being a touch early/late only matters for live orders.
    """
    return today.weekday() == 0  # Monday


def load_panels(symbols: List[str], days_back: int = 600):
    """Load (close, dollar_vol) pivots for `symbols`, ffilled, indexed by date.

    Same shape/labels as the backtest's load_panels but ending today. Needs a
    deeper history than n40 (126d momentum + 20-EMA warmup), so days_back=600.
    """
    eng = get_engine()
    end = datetime.now().date()
    start = end - timedelta(days=days_back)
    with eng.connect() as c:
        df = pd.read_sql(
            text(
                "SELECT symbol,date,close,volume FROM historical_data "
                "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b "
                "AND data_source=:src ORDER BY symbol,date"
            ),
            c, params={"s": symbols, "a": start, "b": end, "src": DATA_SOURCE},
        )
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    dv = (df.assign(dv=df["close"].astype(float) * df["volume"].astype(float))
            .pivot(index="date", columns="symbol", values="dv").ffill())
    return cl, dv


def load_regime_on(regime_sym: str, days_back: int = 420) -> bool:
    """True if regime_sym's latest close > its 200d SMA (risk-on)."""
    eng = get_engine()
    end = datetime.now().date()
    start = end - timedelta(days=days_back)
    with eng.connect() as c:
        q = pd.read_sql(
            text(
                "SELECT date,close FROM historical_data WHERE symbol=:s "
                "AND data_source=:src AND date BETWEEN :a AND :b ORDER BY date"
            ),
            c, params={"s": regime_sym, "src": DATA_SOURCE, "a": start, "b": end},
        )
    if q.empty or len(q) < REGIME_SMA:
        log.warning(f"regime symbol {regime_sym}: only {len(q)} bars (<{REGIME_SMA}) "
                    f"— treating as risk-OFF (conservative).")
        return False
    q["date"] = pd.to_datetime(q["date"])
    s = q.set_index("date")["close"].astype(float)
    sma = s.rolling(REGIME_SMA).mean()
    return bool(s.iloc[-1] > sma.iloc[-1])


def build_signal_payload(model_name: str, universe_csv: str, membership_csv: str,
                         regime_sym: str, risk_on: bool,
                         holdings: Dict[str, float], prices: Dict[str, float],
                         universe_size: int, members_size: int, asof: str) -> Dict:
    """Observer signal: target top-2 equal-weight retest holdings.

    Always observer/dry_run=True — there is NO executor path for these models.
    """
    try:
        from src.services.data.price_history_provider import etoro_display_name
    except Exception:
        etoro_display_name = None
    targets = []
    for i, (sym, w) in enumerate(sorted(holdings.items(), key=lambda kv: -kv[1]), 1):
        nm = (etoro_display_name(sym) if etoro_display_name else None) or sym
        targets.append({
            "rank": i,
            "symbol": sym,
            "company": nm,
            "weight": round(w, 6),
            "lev_weight": round(w, 6),    # cash, no leverage (lev 1.0)
            "price": round(float(prices.get(sym, 0.0)), 4),
        })
    return {
        "model": model_name,
        "strategy": "retest_sp500",
        "observer": True,        # signal-only; no orders are ever placed
        "dry_run": True,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "asof": asof,
        "universe_csv": universe_csv,
        "membership_csv": membership_csv,
        "universe_size": universe_size,
        "members_size": members_size,
        "params": {
            "k": K, "pool": POOL, "retain": RETAIN, "mom_lb": MOM_LB,
            "ema": EMA, "band": BAND, "signal": SIGNAL, "lev": 1.0,
            "regime_sym": regime_sym, "regime_sma": REGIME_SMA,
        },
        "regime_on": risk_on,
        "targets": targets,
        "note": (
            f"OBSERVER retest weekly: top-{K} of top-{POOL} ADV (S&P 500 PIT) by "
            f"{MOM_LB}d momentum in retest zone (<= EMA{EMA} +{int(BAND * 100)}%), "
            f"equal-weight cash, {regime_sym} 200d regime "
            f"{'ON' if risk_on else 'OFF (100% cash)'}."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-csv", required=True,
                    help="broad pool CSV (Symbol,Series) — e.g. nasdaq500.csv")
    ap.add_argument("--membership-csv", required=True,
                    help="PIT S&P 500 membership CSV (symbol,start_date,end_date)")
    ap.add_argument("--model-name", required=True,
                    help="registered model name (e.g. retest_sp500)")
    ap.add_argument("--signals-out", required=True)
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--pool", type=int, default=POOL)
    ap.add_argument("--signal", choices=["ret", "blend"], default=SIGNAL)
    ap.add_argument("--regime-sym", default="QQQ")
    ap.add_argument("--rebalance-only", action="store_true",
                    help="Skip (write empty file) unless today is the weekly rebalance day")
    ap.add_argument("--force", action="store_true",
                    help="Bypass the weekly rebalance-day gate (manual / initial)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    today = datetime.now()
    log.info(f"{args.model_name} OBSERVER run: today={today.date()} "
             f"weekday={today.strftime('%A')} universe={args.universe_csv} "
             f"membership={args.membership_csv}")

    out_path = Path(args.signals_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Weekly rebalance gate (observer still self-skips on non-rebalance days)
    if args.rebalance_only and not args.force and not is_weekly_rebalance_day(today):
        log.info("Not the weekly rebalance day (need Monday). Writing empty file.")
        out_path.write_text(json.dumps([]))
        return 0

    # Broad universe pool
    try:
        universe = sorted(set(load_csv(args.universe_csv)))
    except FileNotFoundError:
        log.error(f"universe CSV not found: {args.universe_csv}")
        out_path.write_text(json.dumps([]))
        return 1
    if not universe:
        log.error(f"empty universe CSV: {args.universe_csv}")
        out_path.write_text(json.dumps([]))
        return 1
    log.info(f"Universe pool: {len(universe)} symbols")

    # PIT membership intervals
    try:
        intervals = load_membership(args.membership_csv)
    except FileNotFoundError:
        log.error(f"membership CSV not found: {args.membership_csv}")
        out_path.write_text(json.dumps([]))
        return 1

    # OHLCV panels (close + dollar volume) up to today
    cl, dv = load_panels(universe)
    if cl.empty:
        log.error("No historical_data for universe — abort (empty signal file).")
        out_path.write_text(json.dumps([]))
        return 1
    di = len(cl) - 1  # latest bar index
    ema20 = cl.ewm(span=EMA, adjust=False).mean()

    # Regime gate (QQQ 200d). Cash when risk-off.
    risk_on = load_regime_on(args.regime_sym)
    log.info(f"{args.regime_sym} 200d regime: {'ON' if risk_on else 'OFF (100% cash)'}")

    # PIT-restrict candidates to actual S&P 500 members on the latest bar's date.
    members = eligible_at(intervals, cl.index[di])
    present = [s for s in universe if s in cl.columns and s in members]
    log.info(f"S&P 500 members present in panel today: {len(present)}")

    if risk_on:
        # Observer has no positions to retain → pos={} (fresh top-K basket).
        holdings = pick_retest_holdings(cl, dv, ema20, di, present, pos={},
                                        pool=args.pool, k=args.k, retain=RETAIN,
                                        mom_lb=MOM_LB, band=BAND, signal=args.signal)
    else:
        holdings = {}

    last_row = cl.iloc[di]
    prices = {s: float(last_row.get(s)) for s in holdings
              if pd.notna(last_row.get(s))}
    asof = cl.index[di].date().isoformat()

    log.info(f"Target holdings ({len(holdings)}):")
    for sym, w in sorted(holdings.items(), key=lambda kv: -kv[1]):
        log.info(f"  {sym:<8} w={w:.4f} @ ${prices.get(sym, 0):.2f}")

    payload = build_signal_payload(
        args.model_name, args.universe_csv, args.membership_csv, args.regime_sym,
        risk_on, holdings, prices, len(universe), len(present), asof,
    )
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    log.info(f"Wrote OBSERVER signal -> {out_path}")

    # Audit hook (best-effort; observer signals are informational)
    try:
        from src.services.audit_service import write_rankings
        top_n = [
            {"rank": t["rank"], "symbol": t["symbol"], "name": t.get("company") or t["symbol"],
             "ret_30d_pct": 0.0, "price": t["price"]}
            for t in payload["targets"]
        ]
        write_rankings(args.model_name, today.date(), len(present), 0, top_n)
    except Exception as _e:
        log.debug(f"audit hook failed: {_e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
