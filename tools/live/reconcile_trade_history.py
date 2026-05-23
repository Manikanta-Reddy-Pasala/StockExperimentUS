"""Rewrite model_trades history rows from audit_orders truth.

Use when ModelTrade entries were manually patched in the past (synthetic
LINK_FYERS_POSITION rows, hand-set pnl values) and no longer match the
real Fyers fills recorded in audit_orders.

Strategy: for the named model, delete existing BUY/SELL ModelTrade rows
and rebuild them from audit_orders.filled rows in chronological order.
DEPOSIT/WITHDRAW rows preserved. PnL recomputed:
  buy.pnl = NULL  (PnL realises only on sell)
  sell.pnl = qty * sell_px - qty * weighted_avg_buy_px - sell_chg
            (matches record_sell formula)

Read-only by default. --apply commits.

Usage:
    docker exec trading_system_app python -m tools.live.reconcile_trade_history \
        --model n20_daily_large_only
    docker exec trading_system_app python -m tools.live.reconcile_trade_history \
        --model n20_daily_large_only --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("reconcile_trade_history")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    from src.models.database import get_database_manager
    from src.models.audit_models import AuditOrder
    from src.models.model_ledger_models import ModelTrade
    from sqlalchemy import asc

    db = get_database_manager()
    with db.get_session() as s:
        audit_rows = (s.query(AuditOrder)
                       .filter(AuditOrder.model_name == args.model)
                       .filter(AuditOrder.status.in_(["placed", "filled", "partial"]))
                       .order_by(asc(AuditOrder.placed_at), asc(AuditOrder.id))
                       .all())
        existing_trades = (s.query(ModelTrade)
                            .filter(ModelTrade.model_name == args.model)
                            .filter(ModelTrade.side.in_(["BUY", "SELL"]))
                            .order_by(asc(ModelTrade.trade_at))
                            .all())
        # Snapshot data before session ends
        audit_snap = [(r.id, r.placed_at, r.side, r.symbol, r.qty, r.fill_qty,
                       float(r.fill_price or r.ordered_price or 0),
                       float(r.charges_inr or 0), r.fyers_order_id)
                      for r in audit_rows]
        existing_snap = [(t.id, t.side, t.symbol, t.qty, float(t.price), float(t.value),
                          float(t.pnl) if t.pnl is not None else None, t.reason)
                         for t in existing_trades]

    log.info(f"=== {args.model} ===")
    log.info(f"audit_orders (truth): {len(audit_snap)} rows")
    for r in audit_snap:
        log.info(f"  {r[1]} {r[2]:5s} {r[3]} qty={r[4]} fill_qty={r[5]} px={r[6]} chg={r[7]} ord={r[8]}")
    log.info(f"existing model_trades (BUY/SELL): {len(existing_snap)} rows")
    for r in existing_snap:
        log.info(f"  id={r[0]} {r[1]:5s} {r[2]} qty={r[3]} px={r[4]} val={r[5]} pnl={r[6]} reason={r[7]}")

    # Build rebuild plan: walk audit chronologically, track open WAvg buy px,
    # emit ModelTrade equivalent for each row.
    plan = []
    open_qty = 0
    open_cost = 0.0  # sum of qty*px for open lots (no charges)
    open_buy_chg = 0.0
    for (aid, placed_at, side, sym, q, fq, px, chg, oid) in audit_snap:
        qty = int(fq if fq else q)
        if side == "BUY":
            cost_incl_chg = qty * px + chg
            plan.append({
                "trade_at": placed_at,
                "side": "BUY",
                "symbol": sym,
                "qty": qty,
                "price": px,
                "value": cost_incl_chg,
                "pnl": None,
                "reason": "ENTRY",
                "fyers_order_id": oid or None,
            })
            open_cost += qty * px
            open_qty += qty
            open_buy_chg += chg
        elif side == "SELL":
            if open_qty <= 0:
                log.warning(f"  WARN: SELL without prior BUY (id={aid}) — pnl untracked")
                avg_px = px
            else:
                avg_px = open_cost / open_qty
            # Cap sell qty to open_qty (Fyers can sell extras via auto-square
            # but ledger PnL only against tracked entries)
            sell_qty = min(qty, open_qty) if open_qty > 0 else qty
            proceeds = sell_qty * px
            net = proceeds - chg
            pnl = net - sell_qty * avg_px
            plan.append({
                "trade_at": placed_at,
                "side": "SELL",
                "symbol": sym,
                "qty": qty,
                "price": px,
                "value": net,
                "pnl": pnl,
                "reason": "EXIT",
                "fyers_order_id": oid or None,
            })
            # FIFO-style: shrink remaining open. For simplicity assume sell
            # qty matches open_qty entirely (common case in single-pos models).
            if qty >= open_qty:
                open_qty = 0
                open_cost = 0.0
                open_buy_chg = 0.0
            else:
                # Partial sell — keep remaining open proportional
                remaining_frac = (open_qty - qty) / open_qty
                open_cost *= remaining_frac
                open_qty -= qty
                open_buy_chg *= remaining_frac

    log.info(f"\nRebuild plan: {len(plan)} BUY/SELL rows")
    for p in plan:
        pnl_str = f"pnl={p['pnl']:.2f}" if p['pnl'] is not None else "pnl=-"
        log.info(f"  {p['trade_at']} {p['side']:5s} {p['symbol']} qty={p['qty']} "
                 f"px={p['price']} val={p['value']:.2f} {pnl_str} ({p['reason']})")

    if not args.apply:
        log.warning("DRY-RUN — re-run with --apply to delete existing BUY/SELL "
                    "ModelTrade rows and insert rebuild plan.")
        return 0

    # Apply: delete existing BUY/SELL rows, insert plan rows
    with db.get_session() as s:
        del_count = (s.query(ModelTrade)
                      .filter(ModelTrade.model_name == args.model)
                      .filter(ModelTrade.side.in_(["BUY", "SELL"]))
                      .delete(synchronize_session=False))
        log.info(f"Deleted {del_count} existing BUY/SELL ModelTrade rows")
        for p in plan:
            s.add(ModelTrade(
                model_name=args.model,
                side=p["side"],
                symbol=p["symbol"],
                qty=p["qty"],
                price=Decimal(str(p["price"])),
                value=Decimal(str(p["value"])),
                pnl=Decimal(str(p["pnl"])) if p["pnl"] is not None else None,
                reason=p["reason"],
                fyers_order_id=p["fyers_order_id"],
                trade_at=p["trade_at"],
            ))
        s.flush()
    log.info(f"{args.model}: COMMITTED {len(plan)} rebuilt rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
