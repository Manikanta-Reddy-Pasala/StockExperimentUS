"""Live-vs-backtest FILL-DRIFT monitor (US).

For every REAL filled order today, compare the live fill price to the price the
BACKTEST would have used for that (symbol, date) — the daily OPEN (US has daily
bars only; no 5m feed). backtest↔live logic + timing are in lockstep, so the only
thing that erodes live CAGR vs the backtest is EXECUTION friction (slippage /
non-fills). This logs that friction per fill so you can watch CAGR adherence and
get alerted when slippage blows past a threshold.

GAIN convention (UI-friendly): +ve = filled BETTER than the backtest (profit),
-ve = worse (loss). BUY better = paid less; SELL better = sold higher.

Run (technical_scheduler cron, after fills settle):
  python tools/live/fill_drift_monitor.py            # today
  python tools/live/fill_drift_monitor.py --date 2026-06-22
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("fill_drift")
LEDGER = ROOT / "logs" / "fill_drift.jsonl"  # ./logs is the SHARED volume (scheduler writes, app reads)
ALERT_PCT = float(os.environ.get("FILL_DRIFT_ALERT_PCT", "0.75"))        # per-fill |drift|
ALERT_MEAN_PCT = float(os.environ.get("FILL_DRIFT_ALERT_MEAN_PCT", "0.40"))  # model mean cost


def _live_fills(day: date):
    """Filled real orders for `day` from audit_orders (skip test/blank symbols)."""
    from src.models.database import get_database_manager
    from src.models.audit_models import AuditOrder
    from sqlalchemy import func
    db = get_database_manager()
    rows = []
    with db.get_session() as s:
        for r in (s.query(AuditOrder.model_name, AuditOrder.side, AuditOrder.symbol,
                          AuditOrder.fill_qty, AuditOrder.fill_price)
                    .filter(func.date(AuditOrder.placed_at) == day)
                    .filter(AuditOrder.status == "filled").all()):
            sym = (r[2] or "").strip()
            if not sym or sym.upper() in ("X", "TEST") or not r[4] or float(r[4]) <= 0:
                continue
            rows.append({"model": r[0], "side": (r[1] or "").upper(), "symbol": sym,
                         "qty": int(r[3] or 0), "fill_price": float(r[4])})
    return rows


def run(day: date) -> int:
    from tools.shared.intraday_fill import exec_raw_open
    fills = _live_fills(day)
    if not fills:
        log.info(f"fill-drift {day}: no live fills — nothing to compare.")
        return 0

    out, breaches = [], []
    by_model: dict = {}
    for f in fills:
        exp = exec_raw_open(f["symbol"], day.isoformat(), f["model"], f["side"])
        rec = {"date": day.isoformat(), **f, "expected": exp}
        if exp:
            drift = (f["fill_price"] / exp - 1) * 100        # signed price diff
            # GAIN convention: +ve = filled BETTER than backtest (profit), -ve = loss.
            gain = -drift if f["side"] == "BUY" else drift
            # $ gain: qty x per-share edge, +ve = money gained vs backtest open.
            edge = (exp - f["fill_price"]) if f["side"] == "BUY" else (f["fill_price"] - exp)
            cost_usd = round(f["qty"] * edge, 2)
            rec["drift_pct"] = round(drift, 3)
            rec["cost_pct"] = round(gain, 3)   # +ve = profit, -ve = loss
            rec["cost_usd"] = cost_usd          # +ve = $ gained, -ve = $ lost
            by_model.setdefault(f["model"], []).append(gain)
            if abs(drift) >= ALERT_PCT:
                breaches.append(rec)
        else:
            rec["drift_pct"] = rec["cost_pct"] = rec["cost_usd"] = None
        out.append(rec)

    # Idempotent per-date write: drop existing rows for `day`, then append today's
    # — so a re-run REPLACES (never duplicates) while keeping every distinct
    # same-day fill (multiple BUYs of one symbol are real, not dups).
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    keep = []
    if LEDGER.exists():
        for ln in LEDGER.read_text().splitlines():
            try:
                if json.loads(ln).get("date") != day.isoformat():
                    keep.append(ln)
            except Exception:
                continue
    with open(LEDGER, "w") as fh:
        for ln in keep:
            fh.write(ln + "\n")
        for rec in out:
            fh.write(json.dumps(rec) + "\n")

    # Per-model mean gain (+ve = better than backtest, -ve = loss); flag models
    # LOSING more than the threshold to slippage.
    model_mean = {m: round(sum(c) / len(c), 3) for m, c in by_model.items() if c}
    bad_models = {m: v for m, v in model_mean.items() if v <= -ALERT_MEAN_PCT}

    usd_by_model: dict = {}
    for rec in out:
        if rec.get("cost_usd") is not None:
            usd_by_model[rec["model"]] = usd_by_model.get(rec["model"], 0.0) + rec["cost_usd"]

    lines = [f"📉 *Fill-drift {day}* (live vs backtest daily open)"]
    for m, v in sorted(model_mean.items()):
        n = len(by_model[m])
        flag = " ⚠️" if m in bad_models else ""
        usd = usd_by_model.get(m, 0.0)
        lines.append(f"• {m}: mean {v:+.2f}% / ${usd:+,.0f} over {n} fill(s){flag}")
    for b in breaches:
        lines.append(f"  ⚠️ {b['model']} {b['side']} {b['symbol']} "
                     f"fill {b['fill_price']:.2f} vs bt {b['expected']:.2f} "
                     f"({b['drift_pct']:+.2f}%)")
    msg = "\n".join(lines)
    print(msg)

    # Alert ONLY on a breach (per-fill drift or model mean) — no spam on clean
    # days. Weekend/holiday = no fills = silent (handled above).
    if breaches or bad_models:
        try:
            from tools.live.telegram_notify import send
            send(msg)
        except Exception as e:
            log.debug(f"tg send failed: {e}")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default today)")
    a = ap.parse_args()
    day = date.fromisoformat(a.date) if a.date else datetime.now().date()
    return run(day)


if __name__ == "__main__":
    raise SystemExit(main())
