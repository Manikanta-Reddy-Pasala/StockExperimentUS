"""N40 large-cap WEEKLY momentum — OBSERVER-MODE live signal generator.

Signal-only. Writes a target-holdings JSON; places NO orders, invokes NO
executor. This is the live shadow of tools/models/n40_largecap_weekly/backtest.py
(itself the IMPROVED US port of the India `n40` archetype).

Strategy (LOCKED — identical to the backtest's selection rule):
  universe : top-40 by trailing-20d ADV from a static large-cap CSV
  signal   : blend = avg(21/63/126-day return)
  hold     : top-3 equal-weight, rebalanced WEEKLY (first trading day of ISO week)
  regime   : 100% cash when the regime symbol (QQQ) < its 200d SMA
  lev      : margin multiplier applied to the equal weights (observer note only —
             no borrowing happens, this just scales the reported target weights so
             the emitted plan matches the backtested book)

The selection logic is REUSED from the backtest via
`tools.models.india_ports_us.backtest.pick_n40_holdings` — do NOT duplicate it
here, so live and backtest can never drift.

Data: historical_data, data_source='yfinance' (eToro-sourced label), plain US
tickers (AAPL). QQQ present for the regime gate.

Usage (dry/observer):
  PYTHONPATH=. python tools/models/n40_largecap_weekly/live_signal.py \
    --universe-csv src/data/symbols/sp500.csv --lev 1.10 \
    --model-name n40_sp500_lev11 \
    --signals-out /app/logs/n40_observer/signals/$(date +%F)_n40_sp500_lev11.json \
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
    get_engine, load_csv, pick_n40_holdings,
)

log = logging.getLogger("n40_observer_signal")

# Locked knobs (match the backtest defaults).
TOP = 3
TOPADV = 40
MOM_LB = 63
SIGNAL = "blend"
REGIME_SMA = 200
DATA_SOURCE = "yfinance"


def is_weekly_rebalance_day(today: datetime) -> bool:
    """True on the first weekday (Mon-Fri) of the current ISO week.

    Mirrors the backtest's weekly rebalance (first trading day each ISO week).
    Calendar Monday is the first weekday; if Monday is a holiday the real first
    trading day shifts, but the cron fires daily and the observer simply emits a
    fresh plan — being a touch early/late only matters for live orders, and this
    is observer-only. We anchor on Monday and treat it as the rebalance trigger.
    """
    return today.weekday() == 0  # Monday


def load_panels(symbols: List[str], days_back: int = 420):
    """Load (close, dollar_vol) pivots for `symbols`, ffilled, indexed by date.

    Same shape/labels as the backtest's load_panels but ending today.
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


def build_signal_payload(model_name: str, universe_csv: str, lev: float,
                         regime_sym: str, risk_on: bool,
                         holdings: Dict[str, float], prices: Dict[str, float],
                         universe_size: int, asof: str,
                         top: int = TOP, topadv: int = TOPADV,
                         signal: str = SIGNAL) -> Dict:
    """Observer signal: target top-3 holdings + leverage-scaled weights.

    Always observer/dry_run=True — there is NO executor path for these models.
    """
    targets = []
    for i, (sym, w) in enumerate(sorted(holdings.items(), key=lambda kv: -kv[1]), 1):
        targets.append({
            "rank": i,
            "symbol": sym,
            "company": sym,
            "weight": round(w, 6),               # equal weight within the basket
            "lev_weight": round(w * lev, 6),     # weight after margin multiplier
            "price": round(float(prices.get(sym, 0.0)), 4),
        })
    return {
        "model": model_name,
        "strategy": "n40_largecap_weekly",
        "observer": True,        # signal-only; no orders are ever placed
        "dry_run": True,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "asof": asof,
        "universe_csv": universe_csv,
        "universe_size": universe_size,
        "params": {
            "top": top, "topadv": topadv, "signal": signal,
            "mom_lb": MOM_LB, "lev": lev,
            "regime_sym": regime_sym, "regime_sma": REGIME_SMA,
        },
        "regime_on": risk_on,
        "targets": targets,
        "note": (
            f"OBSERVER n40 weekly: top-{top} of top-{topadv} ADV by {signal} "
            f"momentum, lev {lev:g}, {regime_sym} 200d regime "
            f"{'ON' if risk_on else 'OFF (100% cash)'}."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-csv", required=True,
                    help="large-cap pool CSV (Symbol,Series)")
    ap.add_argument("--lev", type=float, default=1.0,
                    help="margin multiplier reported on target weights (observer only)")
    ap.add_argument("--model-name", required=True,
                    help="registered model name (e.g. n40_sp500_lev11)")
    ap.add_argument("--signals-out", required=True)
    ap.add_argument("--top", type=int, default=TOP)
    ap.add_argument("--topadv", type=int, default=TOPADV)
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
             f"weekday={today.strftime('%A')} universe={args.universe_csv} lev={args.lev}")

    out_path = Path(args.signals_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Weekly rebalance gate (observer still self-skips on non-rebalance days)
    if args.rebalance_only and not args.force and not is_weekly_rebalance_day(today):
        log.info("Not the weekly rebalance day (need Monday). Writing empty file.")
        out_path.write_text(json.dumps([]))
        return 0

    # Universe pool
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

    # OHLCV panels (close + dollar volume) up to today
    cl, dv = load_panels(universe)
    if cl.empty:
        log.error("No historical_data for universe — abort (empty signal file).")
        out_path.write_text(json.dumps([]))
        return 1
    di = len(cl) - 1  # latest bar index

    # Regime gate (QQQ 200d). Cash when risk-off.
    risk_on = load_regime_on(args.regime_sym)
    log.info(f"{args.regime_sym} 200d regime: {'ON' if risk_on else 'OFF (100% cash)'}")

    if risk_on:
        # Candidate symbols must be present in the loaded panel columns.
        present = [s for s in universe if s in cl.columns]
        holdings = pick_n40_holdings(cl, dv, di, present, topadv=args.topadv,
                                     top=args.top, mom_lb=MOM_LB, signal=args.signal)
    else:
        holdings = {}

    last_row = cl.iloc[di]
    prices = {s: float(last_row.get(s)) for s in holdings
              if pd.notna(last_row.get(s))}
    asof = cl.index[di].date().isoformat()

    log.info(f"Target holdings ({len(holdings)}):")
    for sym, w in sorted(holdings.items(), key=lambda kv: -kv[1]):
        log.info(f"  {sym:<8} w={w:.4f} lev_w={w * args.lev:.4f} @ ${prices.get(sym, 0):.2f}")

    payload = build_signal_payload(
        args.model_name, args.universe_csv, args.lev, args.regime_sym,
        risk_on, holdings, prices, len(universe), asof,
        top=args.top, topadv=args.topadv, signal=args.signal,
    )
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    log.info(f"Wrote OBSERVER signal -> {out_path}")

    # Audit hook (best-effort; observer signals are informational)
    try:
        from src.services.audit_service import write_rankings
        top_n = [
            {"rank": t["rank"], "symbol": t["symbol"], "name": t["symbol"],
             "ret_30d_pct": 0.0, "price": t["price"]}
            for t in payload["targets"]
        ]
        write_rankings(args.model_name, today.date(), len(universe), 0, top_n)
    except Exception as _e:
        log.debug(f"audit hook failed: {_e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
