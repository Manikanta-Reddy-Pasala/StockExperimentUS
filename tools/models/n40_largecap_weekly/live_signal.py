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


def apply_ranked_weights(holdings: Dict[str, float],
                         weights: List[float]) -> Dict[str, float]:
    """Override equal-weight holdings with explicit ranked weights.

    `holdings` is {symbol: equal_weight} as returned by pick_n40_holdings, which
    builds the dict in momentum-descending order. We rely on that insertion
    order: rank-1 = first key, rank-2 = second, etc.

    rank-1 gets weights[0], rank-2 weights[1], etc. If there are FEWER holdings
    than weights, only the present ranks are used and re-normalized to sum to the
    weight mass they cover (so a 2-name day on a 3-weight scheme keeps the same
    relative split). If MORE holdings than weights, extras are dropped (the
    scheme defines the basket size).
    """
    syms = list(holdings.keys())  # preserve insertion (momentum-desc) order
    n = min(len(syms), len(weights))
    if n == 0:
        return {}
    chosen = syms[:n]
    w = weights[:n]
    total = sum(w)
    if total <= 0:
        return {}
    return {s: w[i] / total for i, s in enumerate(chosen)}


def build_signal_payload(model_name: str, universe_csv: str, lev: float,
                         regime_sym: str, risk_on: bool,
                         holdings: Dict[str, float], prices: Dict[str, float],
                         universe_size: int, asof: str,
                         top: int = TOP, topadv: int = TOPADV,
                         signal: str = SIGNAL,
                         weights: List[float] = None) -> Dict:
    """Observer signal: target top-3 holdings + leverage-scaled weights.

    Always observer/dry_run=True — there is NO executor path for these models.
    When `weights` is provided the holdings are blend-weighted (rank-1 heavy)
    instead of equal-weight; otherwise the equal weights from pick_n40_holdings
    flow through unchanged.
    """
    # Holdings arrive in rank order (momentum-desc); keep that order so blend
    # weights map rank-1 -> heaviest. (Sorting by weight would scramble equal
    # weights and break the ranked-weight mapping.)
    try:
        from src.services.data.price_history_provider import etoro_display_name
    except Exception:
        etoro_display_name = None
    targets = []
    for i, (sym, w) in enumerate(holdings.items(), 1):
        nm = (etoro_display_name(sym) if etoro_display_name else None) or sym
        targets.append({
            "rank": i,
            "symbol": sym,
            "company": nm,
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
            "weights": list(weights) if weights else None,
        },
        "regime_on": risk_on,
        "targets": targets,
        "note": (
            f"OBSERVER n40 weekly: top-{top} of top-{topadv} ADV by {signal} "
            f"momentum, "
            + (f"blend weights {weights}, " if weights else "equal-weight, ")
            + f"lev {lev:g}, {regime_sym} 200d regime "
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
    ap.add_argument("--weights", default=None,
                    help='comma-separated ranked weights, e.g. "0.7333,0.1333,0.1333". '
                         "When set, holdings are blend-weighted (rank-1 heaviest) and "
                         "re-normalized; default is equal-weight.")
    ap.add_argument("--regime-sym", default="QQQ")
    ap.add_argument("--rebalance-only", action="store_true",
                    help="Skip (write empty file) unless today is the weekly rebalance day")
    ap.add_argument("--force", action="store_true",
                    help="Bypass the weekly rebalance-day gate (manual / initial)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    weights = None
    if args.weights:
        try:
            weights = [float(x) for x in args.weights.split(",") if x.strip()]
        except ValueError:
            log.error(f"invalid --weights '{args.weights}' (need comma-separated floats)")
            Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.signals_out).write_text(json.dumps([]))
            return 1

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
        # pick_n40_holdings returns {symbol: equal_weight} in momentum-desc order.
        holdings = pick_n40_holdings(cl, dv, di, present, topadv=args.topadv,
                                     top=args.top, mom_lb=MOM_LB, signal=args.signal)
        if weights:
            # Override equal weights with the ranked blend scheme (order kept).
            holdings = apply_ranked_weights(holdings, weights)
    else:
        holdings = {}

    last_row = cl.iloc[di]
    prices = {s: float(last_row.get(s)) for s in holdings
              if pd.notna(last_row.get(s))}
    asof = cl.index[di].date().isoformat()

    log.info(f"Target holdings ({len(holdings)}):")
    # Keep rank order (insertion = momentum-desc); do NOT re-sort by weight.
    for sym, w in holdings.items():
        log.info(f"  {sym:<8} w={w:.4f} lev_w={w * args.lev:.4f} @ ${prices.get(sym, 0):.2f}")

    payload = build_signal_payload(
        args.model_name, args.universe_csv, args.lev, args.regime_sym,
        risk_on, holdings, prices, len(universe), asof,
        top=args.top, topadv=args.topadv, signal=args.signal,
        weights=weights,
    )
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    log.info(f"Wrote OBSERVER signal -> {out_path}")

    # Persist to Postgres (best-effort; JSON write above stays primary)
    try:
        from src.services.trading.observer_signal_store import save_signal
        save_signal(args.model_name, payload)
        log.info(f"Persisted OBSERVER signal to DB (observer_signals): "
                 f"{args.model_name} asof={payload.get('asof')}")
    except Exception as _e:
        log.warning(f"observer_signals DB persist failed (JSON written): {_e}")

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
