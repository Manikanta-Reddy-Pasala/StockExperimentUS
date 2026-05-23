"""momentum_pseudo_n100_adv — monthly live signal generator.

Ranks the pseudo-N100 universe (yearly-PIT top-100 by 20d ADV from N500)
by 30-day return, picks top-5, emits ENTRY1 / TARGET_HIT / STOP_HIT.

Strategy:
  - Universe: yearly-PIT pseudo-N100 (read from yearly_universes.json) —
    rebuilt at year-start using current data at that time (PIT-safe)
  - top_n = 5
  - max_concurrent = 1 (rank-1 of top-5)
  - rebalance: 1st of month (or first trading day on/after)
  - Filter: skip stocks with price > MAX_PRICE (₹3000) — share-count floor
    heuristic so 1 share ≤ 10% of ₹30K live capital

Usage:
  python tools/models/momentum_pseudo_n100_adv/live_signal.py \
    --universes-file tools/models/momentum_pseudo_n100_adv/yearly_universes.json \
    --top-n 5 --rebalance-only \
    --signals-out /app/logs/momrot_pseudo/signals/$(date +%F)_pseudo_n100.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import read_cached  # noqa: E402

log = logging.getLogger("momrot_pseudo_signal")

MODEL_NAME = "momentum_pseudo_n100_adv"
MAX_PRICE = 3000.0  # skip very-large priced names that hurt CAGR in backtest
SMA_LONG = 200  # uptrend filter — must hold close > 200d SMA (backtest parity)
SMALLCAP_CSV = "/app/src/data/symbols/nifty_smallcap250.csv"


def _load_smallcap_set() -> set:
    """Backtest excludes Nifty Smallcap 250 names (+2pp CAGR, DD unchanged).
    Live must mirror. Returns empty set on file missing — fail-soft."""
    import csv as _csv
    out: set = set()
    try:
        with open(SMALLCAP_CSV) as f:
            for r in _csv.DictReader(f):
                if r.get("Series", "").strip() == "EQ":
                    out.add(r["Symbol"].strip())
    except FileNotFoundError:
        log.warning(f"smallcap CSV missing: {SMALLCAP_CSV} — no smallcap filter applied")
    return out


_SMALLCAP_SET = _load_smallcap_set()


# ---- Helpers ----

def is_rebalance_day(today: datetime, last_rotation: datetime = None) -> bool:
    """True if today is monthly rebalance trigger (1st-7th + weekday)."""
    if (last_rotation and last_rotation.year == today.year
            and last_rotation.month == today.month):
        return False
    if today.day <= 7 and today.weekday() < 5:
        return True
    return False


def load_yearly_universes(path: str) -> Dict[str, List[str]]:
    """Read yearly PIT universe dict {year_start_iso: [symbol, ...]}."""
    with open(path) as f:
        return json.load(f)


def pick_universe_for(today: datetime,
                      yearly: Dict[str, List[str]]) -> Tuple[str, List[str]]:
    """Pick most-recent year_start key <= today. Returns (key, symbols)."""
    today_d = today.date()
    chosen_key: Optional[str] = None
    for key in sorted(yearly.keys()):
        try:
            d = datetime.strptime(key, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d <= today_d:
            chosen_key = key
    if chosen_key is None:
        chosen_key = sorted(yearly.keys())[0]
    return chosen_key, yearly[chosen_key]


def get_close_at(symbol: str, target_ts: int) -> float:
    """Return last close at/before target_ts for symbol (0.0 if missing)."""
    df = read_cached(symbol, "D", target_ts - 90 * 86400, target_ts)
    if df.empty:
        return 0.0
    return float(df.iloc[-1]["close"])


def _close_above_sma200(symbol: str, today_ts: int) -> bool:
    """200d SMA uptrend gate (backtest parity).

    Requires ≥200 daily closes in cache. Returns False on insufficient data
    (fail-CLOSED — matches backtest which skips names without 200d history).

    Lookback: 200 trading days × ~7/5 calendar:trading ratio + holidays
    buffer = 420 calendar days. Tighter window misses SMA200 for some names
    (Indian markets ~250 trading days/yr).
    """
    lookback = int(SMA_LONG * 1.6 + 100) * 86400  # calendar-day buffer
    df = read_cached(symbol, "D", today_ts - lookback, today_ts)
    if df.empty or len(df) < SMA_LONG:
        return False
    closes = df["close"].astype(float)
    sma = closes.iloc[-SMA_LONG:].mean()
    return float(closes.iloc[-1]) > float(sma)


def rank_universe(symbols: List[str], today_ts: int,
                  lookback_days: int = 30) -> List[tuple]:
    """Return [(symbol, name, 30d_return_pct, current_price)] sorted desc.

    Filters applied (backtest parity):
      - Drop Nifty Smallcap 250 names
      - Drop current_price > MAX_PRICE
      - Drop names where close ≤ 200d SMA (uptrend gate)
    """
    lookback_ts = today_ts - lookback_days * 86400
    rows = []
    for plain_sym in symbols:
        if plain_sym in _SMALLCAP_SET:
            continue
        fyers_sym = f"NSE:{plain_sym}-EQ"
        c_now = get_close_at(fyers_sym, today_ts)
        c_past = get_close_at(fyers_sym, lookback_ts)
        if c_now <= 0 or c_past <= 0:
            continue
        if c_now > MAX_PRICE:
            continue
        if not _close_above_sma200(fyers_sym, today_ts):
            continue
        ret = (c_now / c_past - 1) * 100
        rows.append((fyers_sym, plain_sym, ret, c_now))
    rows.sort(key=lambda r: -r[2])
    return rows


def get_current_position() -> Optional[Dict]:
    """Read model's open position from model_ledger."""
    try:
        from src.services.trading.model_ledger_service import get_ledger
        l = get_ledger(MODEL_NAME)
        if l and l.get("open_symbol"):
            return l
    except Exception as e:
        log.warning(f"ledger read failed: {e}")
    return None


def is_model_enabled() -> bool:
    """Query model_settings.enabled. Fail-CLOSED on read errors to avoid
    trading without confirming the operator has the model active."""
    try:
        from src.services.trading.model_ledger_service import get_all_settings
        for s in get_all_settings():
            if s["model_name"] == MODEL_NAME:
                return bool(s.get("enabled"))
        return False
    except Exception as e:
        log.warning(f"enabled-flag read failed: {e} — defaulting to OFF")
        return False


def emit_signals(top_picks: List[tuple], pos: Optional[Dict],
                 top_n: int) -> List[Dict]:
    top_syms = {p[0] for p in top_picks[:top_n]}
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    signals: List[Dict] = []

    held_sym = pos.get("open_symbol") if pos else None
    if held_sym and held_sym not in top_syms:
        price = get_close_at(held_sym, int(datetime.now().timestamp()))
        entry_px = float(pos.get("open_entry_px") or 0)
        kind = "TARGET_HIT" if price >= entry_px else "STOP_HIT"
        signals.append({
            "model": MODEL_NAME,
            "universe": "pseudo_n100",
            "symbol": held_sym,
            "company": held_sym,
            "ts": today_str,
            "side": "SELL",
            "signal": kind,
            "price": float(price),
            "sl": 0.0, "target": 0.0,
            "note": f"rotation exit (dropped out of top-{top_n})",
        })

    # Entry: rank-1 if not already held
    if not held_sym or held_sym not in top_syms:
        if top_picks:
            sym, name, ret, price = top_picks[0]
            signals.append({
                "model": MODEL_NAME,
                "universe": "pseudo_n100",
                "symbol": sym,
                "company": name,
                "ts": today_str,
                "side": "BUY",
                "signal": "ENTRY1",
                "price": float(price),
                "sl": 0.0, "target": 0.0,
                "note": f"30d momentum rank-1 ({ret:+.2f}%) — pseudo-N100",
            })

    return signals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universes-file", required=True,
                    help="Path to yearly_universes.json (PIT universe map)")
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--signals-out", required=True)
    ap.add_argument("--rebalance-only", action="store_true",
                    help="Skip if today is not rebalance trigger day")
    ap.add_argument("--force", action="store_true",
                    help="Bypass rebalance-day + enabled checks")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    today = datetime.now()
    log.info(f"{MODEL_NAME} signal run: today={today.date()} "
             f"weekday={today.strftime('%A')} day_of_month={today.day}")

    # Even when disabled / non-rebalance day, we still want the Today's Picks
    # UI to show the ranking. Compute it up front and write to the per-model
    # ranking dir, then proceed with the enabled-flag + rebalance gates.
    yearly = load_yearly_universes(args.universes_file)
    universe_key, symbols = pick_universe_for(today, yearly)
    today_ts = int(today.timestamp())
    ranks = rank_universe(symbols, today_ts)
    log.info(f"PIT universe: {universe_key} → {len(symbols)} symbols")

    ranking_dir = Path("/app/logs/momrot_pseudo/ranking")
    ranking_dir.mkdir(parents=True, exist_ok=True)
    ranking_path = ranking_dir / f"{today.strftime('%Y-%m-%d')}.json"
    ranking_payload = {
        "model": MODEL_NAME,
        "date": today.strftime("%Y-%m-%d"),
        "universe_size": len(symbols),
        "top_n": [
            {
                "rank": i + 1,
                "symbol": plain,
                "name": plain,
                "ret_30d_pct": round(ret, 2),
                "price": round(price, 2),
            }
            for i, (_fyers, plain, ret, price) in enumerate(ranks[:5])
        ],
    }
    ranking_path.write_text(json.dumps(ranking_payload, indent=2, default=str))
    log.info(f"Wrote ranking -> {ranking_path}")

    # Enabled-flag gate (skippable via --force)
    if not args.force and not is_model_enabled():
        log.info(f"{MODEL_NAME}: model_settings.enabled is False — "
                 "writing empty signals file and exiting.")
        Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.signals_out).write_text(json.dumps([]))
        return 0

    # Monthly rebalance gate
    if args.rebalance_only and not args.force:
        if not is_rebalance_day(today):
            log.info("Not rebalance day (need day<=7 + weekday). Skipping.")
            Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.signals_out).write_text(json.dumps([]))
            return 0

    pos = get_current_position()
    log.info(f"Currently held: {pos.get('open_symbol') if pos else 'none'}")
    log.info(f"Ranked {len(ranks)} stocks (after MAX_PRICE={MAX_PRICE} filter). "
             f"Top-{args.top_n}:")
    for i, (sym, name, ret, price) in enumerate(ranks[:args.top_n], 1):
        log.info(f"  {i}. {sym:<20} {ret:+7.2f}%  @ ₹{price:.2f}")

    signals = emit_signals(ranks, pos, args.top_n)
    log.info(f"Emitting {len(signals)} signals")

    Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.signals_out, "w") as f:
        json.dump(signals, f, indent=2, default=str)
    log.info(f"Wrote {args.signals_out}")

    # Audit hook
    try:
        from src.services.audit_service import write_rankings, write_signal
        write_rankings(MODEL_NAME, today.date(),
                       ranking_payload.get("universe_size") or 0,
                       0, ranking_payload.get("top_n") or [])
        # Audit signals ONLY for scheduled (cron) runs, not manual --force.
        if not args.force:
            if signals:
                for _sig in signals:
                    write_signal(MODEL_NAME, today.date(),
                                 _sig.get("signal", ""), _sig.get("symbol", ""),
                                 _sig.get("side", ""), price=_sig.get("price"),
                                 reason=(_sig.get("note") or "")[:120])
            else:
                write_signal(MODEL_NAME, today.date(), "HOLD", "", "NONE",
                             reason="no signal emitted")
    except Exception as _e:
        log.debug(f"audit hook failed: {_e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
