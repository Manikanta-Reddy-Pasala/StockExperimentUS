"""Mirror Fyers positions → model_ledger to catch drift.

Background: record_buy / record_sell in src/services/trading/model_ledger_service.py
keep ledger.cash + open_symbol/qty/entry_px in sync when fyers_executor
detects fills. When detection silently fails (status-mapping bug, exec crash,
external trade), ledger drifts from Fyers truth.

This reconciler:
  1. Pulls Fyers positions (single source of truth)
  2. For each enabled model with a known open_symbol, compares qty + avg_price
  3. Auto-mirrors Fyers → ledger when Fyers qty exceeds ledger qty (missed BUY)
  4. Alerts (no auto-fix) when Fyers qty under ledger qty (externally closed) —
     manual review needed because we don't know SELL price without Fyers tradebook
  5. Flags orphans (Fyers holds X, no ledger row claims X)

Cash invariant assumed after auto-fix:
  cash = invested_amount + realized_pnl - (new_open_qty * new_open_entry_px)
  (clamped >= 0; charges drift accepted as small)

Usage:
  python tools/live/position_reconciler.py [--dry-run] [--tg-on-fix]
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("position_reconciler")


def _normalize(sym: str) -> str:
    """Match record_buy convention (uppercase, NSE:…-EQ form)."""
    if not sym:
        return ""
    s = sym.strip().upper()
    if not s.startswith("NSE:") and "-" not in s:
        s = f"NSE:{s}-EQ"
    return s


def _merge_pos(out: Dict[str, Dict], rows, source: str) -> None:
    """Merge Fyers position/holding rows into {symbol: {qty, avg_price,
    last_price, source}}. Same symbol in both: sum qty + weighted-avg price."""
    for p in rows or []:
        sym = _normalize(p.get("symbol") or "")
        if not sym:
            continue
        qty = int(float(p.get("quantity") or 0))
        if qty == 0:
            continue
        px = float(p.get("average_price") or 0)
        lp = float(p.get("last_price") or 0)
        if sym in out:
            prev_qty = out[sym]["qty"]
            prev_px = out[sym]["avg_price"]
            total_qty = prev_qty + qty
            new_px = ((prev_qty * prev_px) + (qty * px)) / total_qty if total_qty else 0
            out[sym]["qty"] = total_qty
            out[sym]["avg_price"] = new_px
            out[sym]["source"] = f"{out[sym]['source']}+{source}"
            if lp and not out[sym]["last_price"]:
                out[sym]["last_price"] = lp
        else:
            out[sym] = {"qty": qty, "avg_price": px, "last_price": lp,
                        "source": source}


def _fyers_positions_by_symbol(svc, user_id: int = 1) -> Dict[str, Dict]:
    """Union of intraday positions + settled holdings. Both are real exposure
    and the model_ledger should match the sum.

    Background: CNC orders show in positions() on the day of purchase, then
    move to holdings() after T+1 settlement. Reconciler must check both or
    it will think the position vanished (false LEDGER_AHEAD alert).
    """
    out: Dict[str, Dict] = {}
    for fn_name, source in [("positions", "pos"), ("holdings", "hold")]:
        try:
            fn = getattr(svc, fn_name)
            res = fn(user_id=user_id)
            if not isinstance(res, dict) or res.get("status") != "success":
                log.warning(f"{fn_name}() returned non-success: {res}")
                continue
            _merge_pos(out, res.get("data", []), source)
        except Exception as e:
            log.error(f"fyers {fn_name} fetch failed: {e}")
    return out


def reconcile_once(user_id: int = 1, dry_run: bool = False) -> List[Dict]:
    """One pass. Returns list of correction dicts."""
    from src.models.database import get_database_manager
    from src.models.model_ledger_models import ModelLedger, ModelSettings
    from src.services.data.market_data_service import MarketDataService as FyersService

    svc = FyersService()
    fyers = _fyers_positions_by_symbol(svc, user_id)

    db = get_database_manager()
    corrections: List[Dict] = []
    with db.get_session() as s:
        ledgers = s.query(ModelLedger).all()
        settings_map = {x.model_name: x for x in s.query(ModelSettings).all()}
        claimed_syms = set()

        for l in ledgers:
            cfg = settings_map.get(l.model_name)
            if not cfg or not cfg.enabled:
                continue

            expected_sym = _normalize(l.open_symbol or "")
            expected_qty = int(l.open_qty or 0)
            expected_px = float(l.open_entry_px or 0)

            if not expected_sym:
                continue  # ledger flat — orphan check below

            claimed_syms.add(expected_sym)
            actual = fyers.get(expected_sym)

            if not actual:
                # Ledger thinks holding, Fyers shows nothing. External SELL?
                # Don't auto-clear (would lose realized PnL). Just alert.
                corrections.append({
                    "model": l.model_name,
                    "type": "LEDGER_AHEAD",
                    "before": f"{expected_sym} x{expected_qty} @ {expected_px:.2f}",
                    "after": "Fyers shows no position",
                    "action": "MANUAL: check Fyers tradebook, run record_sell",
                })
                continue

            actual_qty = actual["qty"]
            actual_px = actual["avg_price"]

            if actual_qty == expected_qty and abs(actual_px - expected_px) < 0.01:
                continue  # no drift

            # Drift detected — auto-fix only when safe.
            # SAFE: Fyers qty >= ledger qty (extra BUY captured) — mirror.
            # SAFE: ledger has same symbol but stale price — mirror.
            # UNSAFE: Fyers qty < ledger qty (external partial SELL) — alert.
            if actual_qty < expected_qty:
                corrections.append({
                    "model": l.model_name,
                    "type": "QTY_REDUCED",
                    "before": f"{expected_sym} x{expected_qty} @ {expected_px:.2f}",
                    "after": f"{expected_sym} x{actual_qty} @ {actual_px:.2f}",
                    "action": "MANUAL: partial external SELL, run record_sell for diff",
                })
                continue

            # Auto-fix path
            invested = float(cfg.invested_amount or 0)
            realized = float(l.realized_pnl or 0)
            new_cost = actual_qty * actual_px
            new_cash = max(0.0, invested + realized - new_cost)

            corrections.append({
                "model": l.model_name,
                "type": "AUTO_MIRROR",
                "before": (f"{expected_sym} x{expected_qty} @ {expected_px:.2f} "
                           f"cash=₹{float(l.cash or 0):.2f}"),
                "after": (f"{expected_sym} x{actual_qty} @ {actual_px:.2f} "
                          f"cash=₹{new_cash:.2f}"),
                "action": "applied" if not dry_run else "would-apply",
            })

            if not dry_run:
                l.open_symbol = expected_sym
                l.open_qty = actual_qty
                l.open_entry_px = Decimal(str(round(actual_px, 4)))
                if not l.open_entry_date:
                    l.open_entry_date = date.today()
                l.cash = Decimal(str(round(new_cash, 2)))
                l.updated_at = datetime.now()

        # Orphan detection: Fyers holds symbol no enabled-ledger claims
        for sym, pos in fyers.items():
            if sym in claimed_syms:
                continue
            corrections.append({
                "model": "?",
                "type": "FYERS_ORPHAN",
                "before": "no ledger row claims it",
                "after": f"{sym} x{pos['qty']} @ {pos['avg_price']:.2f}",
                "action": "MANUAL: assign to a model or sell",
            })

        if not dry_run:
            s.commit()

    return corrections


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tg-on-fix", action="store_true",
                    help="Send Telegram alert when corrections happen")
    ap.add_argument("--user-id", type=int, default=1)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    corrections = reconcile_once(user_id=args.user_id, dry_run=args.dry_run)

    if not corrections:
        log.info("Reconcile: no drift")
        return 0

    log.warning(f"Reconcile: {len(corrections)} item(s)"
                f"{'  (dry-run)' if args.dry_run else ''}")
    for c in corrections:
        log.warning(f"  [{c['type']}] {c['model']}: {c['before']} → {c['after']}"
                    f" ({c['action']})")

    if args.tg_on_fix:
        try:
            from tools.live.telegram_notify import send
            lines = [f"*Ledger reconciler* — {len(corrections)} item(s)"]
            for c in corrections[:8]:
                lines.append(f"`{c['type']}` `{c['model']}`")
                lines.append(f"  was: {c['before']}")
                lines.append(f"  now: {c['after']}")
                lines.append(f"  → {c['action']}")
            send("\n".join(lines))
        except Exception as e:
            log.error(f"TG alert failed: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
