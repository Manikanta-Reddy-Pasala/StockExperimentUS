"""n20_daily_large_only — daily live signal generator.

Daily rotation: ranks top-20 N500 stocks by 20d ADV ∩ Nifty 100 with
close > 200d SMA (uptrend filter), then picks rank-1 by 30d return.

Strategy:
  - Universe: top-20 by 20d ADV from N500 ∩ NSE Nifty 100
  - Uptrend filter: close > 200d SMA
  - Rank by 30d return desc
  - top_n = 1 (max_concurrent=1)
  - Rebalance: DAILY (not monthly — much higher turnover)

Logic per run:
  1. Build today's PIT universe (top-20 ADV ∩ N100, uptrend-filtered)
  2. Rank universe by 30d return
  3. If held NOT in top-1 → emit STOP_HIT / TARGET_HIT (rotation exit)
  4. Emit ENTRY1 for rank-1 if not already held

Usage:
  python tools/models/n20_daily_large_only/live_signal.py \
    --signals-out /app/logs/n20_daily/signals/$(date +%F)_n20.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import _get_engine  # noqa: E402
from tools.shared.universes import nifty100_symbols, nifty500_symbols  # noqa: E402

log = logging.getLogger("n20_daily_signal")

MODEL_NAME = "n20_daily_large_only"

# Strategy params (must match backtest)
UNIV_SIZE = 20
LOOKBACK_RET = 30
ADV_WIN = 20
SMA_LONG = 200


def is_weekday(today: datetime) -> bool:
    return today.weekday() < 5


def is_model_enabled() -> bool:
    """Check model_settings.enabled. Fail-closed on error (skip trading)."""
    try:
        from src.services.trading.model_ledger_service import get_all_settings
        for s in get_all_settings():
            if s["model_name"] == MODEL_NAME:
                return bool(s.get("enabled"))
        return False
    except Exception as e:
        log.warning(f"enabled-flag read failed: {e} — defaulting to DISABLED")
        return False


def get_current_position() -> Optional[Dict]:
    try:
        from src.services.trading.model_ledger_service import get_ledger
        l = get_ledger(MODEL_NAME)
        if l and l.get("open_symbol"):
            return l
    except Exception as e:
        log.warning(f"ledger read failed: {e}")
    return None


def load_panel(symbols: List[str], days_back: int = 400) -> pd.DataFrame:
    """Load OHLCV panel for symbol list ending today."""
    eng = _get_engine()
    end = datetime.now().date()
    start = end - timedelta(days=days_back)
    with eng.connect() as c:
        df = pd.read_sql(
            text(
                "SELECT symbol,date,close,volume FROM historical_data "
                "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b "
                "AND data_source='fyers' ORDER BY symbol,date"
            ),
            c, params={"s": symbols, "a": start, "b": end},
        )
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_pit_universe_and_rank(df: pd.DataFrame, n100: set
                                ) -> List[tuple]:
    """Return ranked top-20 ∩ N100 with uptrend filter, by 30d return.

    Output: [(fyers_symbol, plain_symbol, 30d_return_pct, current_price)]
    """
    if df.empty:
        return []
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    df["adv_rs"] = df["close"].astype(float) * df["volume"].astype(float)

    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    adv = df.pivot(index="date", columns="symbol", values="adv_rs").fillna(0)
    if cl.empty:
        return []
    adv20 = adv.rolling(ADV_WIN).mean()
    sma200 = cl.rolling(SMA_LONG).mean()

    today_row = cl.iloc[-1]
    pit_adv = adv20.iloc[-1].dropna().sort_values(ascending=False)
    pit_univ = pit_adv.head(UNIV_SIZE).index.tolist()

    # Uptrend filter
    sma_today = sma200.iloc[-1]
    pit_univ = [s for s in pit_univ if pd.notna(sma_today.get(s))
                and pd.notna(today_row.get(s))
                and float(today_row[s]) > float(sma_today[s])]
    # Nifty 100 intersection
    pit_univ = [s for s in pit_univ
                if s.replace("NSE:", "").replace("-EQ", "") in n100]

    if len(cl) < LOOKBACK_RET + 1:
        return []
    ref_row = cl.iloc[-LOOKBACK_RET - 1]
    rows = []
    for sym in pit_univ:
        c_now = float(today_row.get(sym, 0) or 0)
        c_past = float(ref_row.get(sym, 0) or 0)
        if c_now <= 0 or c_past <= 0:
            continue
        ret = (c_now / c_past - 1) * 100
        plain = sym.replace("NSE:", "").replace("-EQ", "")
        rows.append((sym, plain, ret, c_now))
    rows.sort(key=lambda r: -r[2])
    return rows


def emit_signals(top_picks: List[tuple], pos: Optional[Dict],
                 top_n: int) -> List[Dict]:
    top_syms = {p[0] for p in top_picks[:top_n]}
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    signals: List[Dict] = []

    held_sym = pos.get("open_symbol") if pos else None
    if held_sym and held_sym not in top_syms:
        # Re-read latest price for exit
        exit_price = 0.0
        for p in top_picks:
            if p[0] == held_sym:
                exit_price = p[3]
                break
        entry_px = float(pos.get("open_entry_px") or 0)
        kind = "TARGET_HIT" if exit_price >= entry_px else "STOP_HIT"
        signals.append({
            "model": MODEL_NAME,
            "universe": "n20_adv_n100",
            "symbol": held_sym,
            "company": held_sym,
            "ts": today_str,
            "side": "SELL",
            "signal": kind,
            "price": float(exit_price),
            "sl": 0.0, "target": 0.0,
            "note": f"daily rotation exit (dropped out of top-{top_n})",
        })

    # Entry: rank-1 if not already held
    if (not held_sym or held_sym not in top_syms) and top_picks:
        sym, name, ret, price = top_picks[0]
        signals.append({
            "model": MODEL_NAME,
            "universe": "n20_adv_n100",
            "symbol": sym,
            "company": name,
            "ts": today_str,
            "side": "BUY",
            "signal": "ENTRY1",
            "price": float(price),
            "sl": 0.0, "target": 0.0,
            "note": f"30d momentum rank-1 ({ret:+.2f}%) — N20 ADV∩N100",
        })

    return signals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signals-out", required=True)
    ap.add_argument("--top-n", type=int, default=1)
    ap.add_argument("--force", action="store_true",
                    help="Bypass weekday + enabled checks")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    today = datetime.now()
    log.info(f"{MODEL_NAME} signal run: today={today.date()} "
             f"weekday={today.strftime('%A')}")

    if not args.force and not is_model_enabled():
        log.warning(f"{MODEL_NAME}: model_settings.enabled is False — "
                    "writing empty signals file and exiting.")
        Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.signals_out).write_text(json.dumps([]))
        return 0

    if not args.force and not is_weekday(today):
        log.info("Weekend — skipping daily rotation.")
        Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.signals_out).write_text(json.dumps([]))
        return 0

    # Build Nifty 100 set (plain symbol form)
    n100 = {s for s, _ in nifty100_symbols()}
    if not n100:
        log.error("Nifty 100 CSV missing — run tools/refresh_nifty100.py")
        Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.signals_out).write_text(json.dumps([]))
        return 1
    log.info(f"Nifty 100 set: {len(n100)} symbols")

    # Load OHLCV for full N500 (PIT ranking pool)
    n500_fyers = [f"NSE:{s}-EQ" for s, _ in nifty500_symbols()]
    log.info(f"Loading N500 OHLCV for {len(n500_fyers)} symbols...")
    df = load_panel(n500_fyers, days_back=400)
    if df.empty:
        log.error("No historical data — abort.")
        Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.signals_out).write_text(json.dumps([]))
        return 1

    ranks = build_pit_universe_and_rank(df, n100)
    log.info(f"PIT-ranked {len(ranks)} stocks (top-{UNIV_SIZE} ADV ∩ N100 + "
             f"uptrend). Top-{args.top_n}:")
    for i, (sym, name, ret, price) in enumerate(ranks[:max(args.top_n, 5)], 1):
        log.info(f"  {i}. {sym:<20} {ret:+7.2f}%  @ ₹{price:.2f}")

    pos = get_current_position()
    log.info(f"Currently held: {pos.get('open_symbol') if pos else 'none'}")

    signals = emit_signals(ranks, pos, args.top_n)
    log.info(f"Emitting {len(signals)} signals")

    Path(args.signals_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.signals_out, "w") as f:
        json.dump(signals, f, indent=2, default=str)
    log.info(f"Wrote {args.signals_out}")

    # Per-model ranking JSON for Today's Picks UI. Top-5 always written so
    # the picks page works even on weekends / when the model is disabled.
    ranking_dir = Path("/app/logs/n20_daily/ranking")
    ranking_dir.mkdir(parents=True, exist_ok=True)
    today_str = today.strftime("%Y-%m-%d")
    ranking_payload = {
        "model": MODEL_NAME,
        "date": today_str,
        "universe_size": len(ranks),
        "top_n": [
            {
                "rank": i + 1,
                "symbol": plain,
                "name": plain,
                "ret_30d_pct": round(ret, 2),
                "price": round(price, 2),
            }
            for i, (_fyers_sym, plain, ret, price) in enumerate(ranks[:5])
        ],
    }
    (ranking_dir / f"{today_str}.json").write_text(
        json.dumps(ranking_payload, indent=2, default=str)
    )
    log.info(f"Wrote ranking -> {ranking_dir / (today_str + '.json')}")

    # Audit: persist rankings + signals to DB
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
