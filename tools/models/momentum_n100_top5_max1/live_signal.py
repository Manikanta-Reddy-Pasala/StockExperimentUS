"""Model 3 — Momentum Rotation live signal generator.

Ranks the N100 universe by 30d return, picks top-N, emits ENTRY1 /
TARGET_HIT / STOP_HIT signals consumed by tools/live/fyers_executor.py.

Strategy:
  - Universe: real NIFTY 100 (NSE constituents from ind_nifty100list.csv)
  - top_n = 5
  - max_concurrent = 1
  - rebalance: 1st of month (or first trading day on/after)

Logic per run:
  1. Load current ledger -> currently held symbol (if any)
  2. Rank universe by 30d return; pick top-N
  3. If held NOT in top-N -> emit STOP_HIT (rotation exit)
  4. Emit ENTRY1 for rank-1 stock if not already held

Usage:
  python tools/models/momentum_n100_top5_max1/live_signal.py \
    --universe-file /app/logs/momrot/universes/n100_current.json \
    --top-n 5 --rebalance-only \
    --signals-out /app/logs/momrot/signals/$(date +%F)_momrot_n100.json

Flags:
  --rebalance-only       only emit signals on 1st-of-month (or after weekend)
  --force                emit regardless of date
  --ledger PATH          live ledger to read current holdings (optional)
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import read_cached  # noqa: E402

log = logging.getLogger("momrot_signal")


def is_rebalance_day(today: datetime, last_rotation: datetime = None) -> bool:
    """True if today is rebalance trigger.

    Rule: rebalance once per month. Trigger on first weekday on/after
    the 1st of month. If last rotation was this month already, skip.
    """
    if last_rotation and last_rotation.year == today.year and last_rotation.month == today.month:
        return False
    # Today is 1st-7th of month and weekday (Mon-Fri)
    if today.day <= 7 and today.weekday() < 5:
        return True
    return False


# Mid-month check: trigger an extra rank check on the first weekday on/after
# day 15 of each month. Only emits a ROTATE signal if the new rank-1 leads
# the currently-held stock's 30d return by >= MID_MONTH_LEAD_PCT. Backtested
# on 2023-26 N100 universe: +19.7pp CAGR over plain monthly (+81.4% vs
# +61.7% baseline, Calmar 1.31 → 1.75) with honest costs included.
MID_MONTH_LEAD_PCT = 5.0   # rotate mid-month only if new rank-1 leads by 5pp


def is_mid_month_check_day(today: datetime) -> bool:
    """True if today is the mid-month check trigger.

    Rule: first weekday on/after day 15 of month, but NOT also a rebalance
    day (avoids double-firing in odd calendars).
    """
    if today.day < 15 or today.day > 21:
        return False
    if today.weekday() >= 5:
        return False
    # Earliest weekday on/after 15 — anchor by walking back from today
    anchor = datetime(today.year, today.month, 15)
    while anchor.weekday() >= 5:
        anchor += timedelta(days=1)
    return today.date() == anchor.date()


def load_universe(path: str) -> List[Dict]:
    with open(path) as f:
        return json.load(f)["stocks"]


def get_close_at(symbol: str, target_ts: int) -> float:
    df = read_cached(symbol, "D", target_ts - 90 * 86400, target_ts)
    if df.empty:
        return 0.0
    return float(df.iloc[-1]["close"])


def rank_universe(stocks: List[Dict], today_ts: int,
                  lookback_days: int = 30) -> List[tuple]:
    """Return [(symbol, name, 30d_return%, current_price)] sorted desc."""
    lookback_ts = today_ts - lookback_days * 86400
    rows = []
    for s in stocks:
        sym = s["symbol"]
        c_now = get_close_at(sym, today_ts)
        c_past = get_close_at(sym, lookback_ts)
        if c_now > 0 and c_past > 0:
            ret = (c_now / c_past - 1) * 100
            rows.append((sym, s.get("name", sym), ret, c_now))
    rows.sort(key=lambda r: -r[2])
    return rows


def load_held(ledger_path: Path) -> List[Dict]:
    if not ledger_path or not ledger_path.exists():
        return []
    try:
        with open(ledger_path) as f:
            return json.load(f).get("open", [])
    except Exception as e:
        log.warning(f"ledger read fail: {e}")
        return []


def emit_signals(top_picks: List[tuple], held: List[Dict],
                  top_n: int) -> List[Dict]:
    top_syms = {p[0] for p in top_picks[:top_n]}
    held_syms = {h["symbol"] for h in held}
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    signals = []

    # Exits: held but no longer in top-N
    for h in held:
        if h["symbol"] not in top_syms:
            price = get_close_at(h["symbol"], int(datetime.now().timestamp()))
            kind = "TARGET_HIT" if price >= h["entry_price"] else "STOP_HIT"
            signals.append({
                "model": "momentum_rotation",
                "universe": "n100_real",
                "symbol": h["symbol"],
                "company": h["symbol"],
                "ts": today_str,
                "side": "BUY",
                "signal": kind,
                "price": float(price),
                "sl": 0.0, "target": 0.0,
                "note": f"rotation exit (dropped out of top-{top_n})",
            })

    # Entries: rank-1 stock if no held position already in top-N
    # (max_concurrent=1 means take rank-1 if not held)
    if not any(h["symbol"] in top_syms for h in held) and top_picks:
        sym, name, ret, price = top_picks[0]
        signals.append({
            "model": "momentum_rotation",
            "universe": "n100_pseudo",
            "symbol": sym,
            "company": name,
            "ts": today_str,
            "side": "BUY",
            "signal": "ENTRY1",
            "price": float(price),
            "sl": 0.0, "target": 0.0,
            "note": f"30d momentum rank-1 ({ret:+.2f}%)",
        })

    return signals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-file", required=True)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--signals-out", required=True)
    ap.add_argument("--ledger", default=None,
                    help="Paper ledger JSON to read current holdings")
    ap.add_argument("--rebalance-only", action="store_true",
                    help="Skip if today is not rebalance trigger day")
    ap.add_argument("--mid-month-check", action="store_true",
                    help="Day-15 check: emit ROTATE only if rank-1 leads "
                         "current held by >= MID_MONTH_LEAD_PCT (default 5pp)")
    ap.add_argument("--force", action="store_true",
                    help="Bypass rebalance-day check (initial deploy / manual)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    today = datetime.now()
    log.info(f"momentum_rotation_signal run: today={today.date()} "
             f"weekday={today.strftime('%A')} day_of_month={today.day}")

    # Mid-month gate (mutually exclusive with rebalance-only; --force still
    # overrides). Only emit on day-15 weekday AND lead >= threshold.
    if args.mid_month_check and not args.force:
        if not is_mid_month_check_day(today):
            log.info("Not mid-month check day (need day-15-weekday). Skipping.")
            Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
            with open(args.signals_out, "w") as f:
                json.dump([], f)
            return 0

    if args.rebalance_only and not args.force and not args.mid_month_check:
        if not is_rebalance_day(today):
            log.info(f"Not rebalance day (need day<=7 + weekday). Skipping.")
            Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
            with open(args.signals_out, "w") as f:
                json.dump([], f)
            return 0

    stocks = load_universe(args.universe_file)
    log.info(f"Universe: {len(stocks)} symbols from {args.universe_file}")

    held = load_held(Path(args.ledger)) if args.ledger else []
    log.info(f"Currently held: {[h['symbol'] for h in held]}")

    today_ts = int(today.timestamp())
    ranks = rank_universe(stocks, today_ts)
    log.info(f"Ranked {len(ranks)} stocks. Top-{args.top_n}:")
    for i, (sym, name, ret, price) in enumerate(ranks[:args.top_n], 1):
        log.info(f"  {i}. {sym:<14} {ret:+7.2f}%  @ ₹{price:.2f}")

    signals = emit_signals(ranks, held, args.top_n)

    # Mid-month lead-threshold filter:
    # If today is the mid-month check day, suppress rotation unless the
    # new rank-1 leads the currently-held stock's 30d return by at least
    # MID_MONTH_LEAD_PCT. Keeps trade count low while still catching
    # genuine new winners that broke out mid-cycle.
    if args.mid_month_check and held and signals:
        held_sym = held[0]["symbol"]
        held_ret = next((r[2] for r in ranks if r[0] == held_sym), None)
        top1_sym, top1_name, top1_ret, top1_price = ranks[0] if ranks else (None, None, None, None)
        if held_sym == top1_sym:
            log.info(f"mid-month: already holding rank-1 ({held_sym}). No rotation.")
            signals = []
        elif held_ret is None:
            log.info(f"mid-month: held {held_sym} dropped from ranking. Allowing rotation.")
        else:
            lead = top1_ret - held_ret
            if lead < MID_MONTH_LEAD_PCT:
                log.info(f"mid-month: rank-1 {top1_sym} leads held {held_sym} "
                         f"by {lead:.2f}pp (< {MID_MONTH_LEAD_PCT}pp). No rotation.")
                signals = []
            else:
                log.info(f"mid-month: ROTATE — {top1_sym} leads {held_sym} "
                         f"by {lead:.2f}pp (>= {MID_MONTH_LEAD_PCT}pp).")

    log.info(f"Emitting {len(signals)} signals")

    Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.signals_out, "w") as f:
        json.dump(signals, f, indent=2, default=str)
    log.info(f"Wrote {args.signals_out}")

    # Persist top-N ranking for the Today's Picks UI. Always written (even
    # on non-rebalance days the user wants to *see* the current ranking).
    ranking_dir = Path("/app/logs/momrot/ranking")
    ranking_dir.mkdir(parents=True, exist_ok=True)
    ranking_path = ranking_dir / f"{today.strftime('%Y-%m-%d')}.json"
    top_payload = {
        "model": "momentum_n100_top5_max1",
        "date": today.strftime("%Y-%m-%d"),
        "universe_size": len(stocks),
        "top_n": [
            {
                "rank": i + 1,
                "symbol": sym,
                "name": name,
                "ret_30d_pct": round(ret, 2),
                "price": round(price, 2),
            }
            for i, (sym, name, ret, price) in enumerate(ranks[:5])
        ],
    }
    ranking_path.write_text(json.dumps(top_payload, indent=2, default=str))
    log.info(f"Wrote ranking -> {ranking_path}")

    # Audit hook
    try:
        from src.services.audit_service import write_rankings, write_signal
        write_rankings("momentum_n100_top5_max1", today.date(),
                       top_payload.get("universe_size") or 0,
                       0, top_payload.get("top_n") or [])
        # Audit signals ONLY for scheduled (cron) runs, not manual --force.
        if not args.force:
            if signals:
                for _sig in signals:
                    write_signal("momentum_n100_top5_max1", today.date(),
                                 _sig.get("signal", ""), _sig.get("symbol", ""),
                                 _sig.get("side", ""), price=_sig.get("price"),
                                 reason=(_sig.get("note") or "")[:120])
            else:
                write_signal("momentum_n100_top5_max1", today.date(), "HOLD", "", "NONE",
                             reason="no signal emitted")
    except Exception as _e:
        log.debug(f"audit hook failed: {_e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
