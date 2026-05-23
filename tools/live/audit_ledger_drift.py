"""Daily ledger drift audit. Read-only.

Compares `model_ledger.cash` to the cash flow implied by `audit_orders`
(starting from `model_settings.invested_amount` minus realized losses).
If they diverge by more than ₹1, flags drift and exits non-zero so a cron
wrapper can alert.

Identity checked per model:
    expected_cash = invested_amount
                  - sum(audit_orders.qty * audit_orders.fill_price + charges_inr)  [BUYs]
                  + sum(audit_orders.fill_qty * audit_orders.fill_price - charges_inr)  [SELLs]

Drift > ₹1 means either:
  - record_buy/sell missed a fill (e.g. raised on 2nd same-symbol buy)
  - audit_orders has stale or missing data
  - someone manually patched ledger.cash without writing audit row

Usage:
    docker exec trading_system_app python -m tools.live.audit_ledger_drift
    docker exec trading_system_app python -m tools.live.audit_ledger_drift --model n20_daily_large_only --verbose
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("audit_ledger_drift")


def audit_one(s, model_name: str, verbose: bool) -> float:
    from sqlalchemy import text
    row = s.execute(text("""
        SELECT s.invested_amount AS alloc,
               l.cash AS cash,
               l.realized_pnl AS realized,
               l.open_symbol, l.open_qty, l.open_entry_px
        FROM model_settings s
        JOIN model_ledger l ON s.model_name = l.model_name
        WHERE s.model_name = :m
    """), {"m": model_name}).fetchone()
    if not row:
        log.warning(f"{model_name}: no ledger")
        return 0.0
    alloc = float(row.alloc or 0)
    cash = float(row.cash or 0)
    realized = float(row.realized or 0)
    open_qty = int(row.open_qty or 0)
    open_px = float(row.open_entry_px or 0)
    cost_basis = open_qty * open_px

    # Sum cash impacts from audit_orders (fill values, fall back to ordered).
    buy_rows = s.execute(text("""
        SELECT COALESCE(SUM(COALESCE(fill_qty, qty) * COALESCE(fill_price, ordered_price)), 0) AS notional,
               COALESCE(SUM(charges_inr), 0) AS chg
        FROM audit_orders
        WHERE model_name = :m AND side = 'BUY'
          AND status IN ('placed','filled','partial')
    """), {"m": model_name}).fetchone()
    sell_rows = s.execute(text("""
        SELECT COALESCE(SUM(COALESCE(fill_qty, qty) * COALESCE(fill_price, ordered_price)), 0) AS notional,
               COALESCE(SUM(charges_inr), 0) AS chg
        FROM audit_orders
        WHERE model_name = :m AND side = 'SELL'
          AND status IN ('placed','filled','partial')
    """), {"m": model_name}).fetchone()
    buy_notional = float(buy_rows.notional or 0)
    buy_chg_life = float(buy_rows.chg or 0)
    sell_notional = float(sell_rows.notional or 0)
    sell_chg_life = float(sell_rows.chg or 0)

    # Expected cash = alloc - cash_out + cash_in
    expected_cash = alloc - (buy_notional + buy_chg_life) + (sell_notional - sell_chg_life)
    cash_drift = cash - expected_cash

    # Reconcile identity (UI Form A):
    #   alloc = cash + cost_basis + buy_chg + sell_chg - realized_gross
    realized_gross = realized + sell_chg_life
    recon_sum = cash + cost_basis + buy_chg_life + sell_chg_life - realized_gross
    recon_drift = recon_sum - alloc

    status = "OK" if abs(cash_drift) < 1 and abs(recon_drift) < 1 else "DRIFT"
    log.info(
        f"[{status}] {model_name:30s} alloc={alloc:>9,.2f} "
        f"cash_db={cash:>9,.2f} cash_expected={expected_cash:>9,.2f} "
        f"cash_drift={cash_drift:+7,.2f} | recon_drift={recon_drift:+7,.2f}"
    )
    if verbose or status == "DRIFT":
        log.info(
            f"     ↳ buys_notional={buy_notional:,.2f} buy_chg={buy_chg_life:,.2f}  "
            f"sells_notional={sell_notional:,.2f} sell_chg={sell_chg_life:,.2f}  "
            f"realized_db={realized:,.2f} (gross={realized_gross:,.2f})  "
            f"open={row.open_symbol or 'flat'} {open_qty}@{open_px:.2f}"
        )
    return max(abs(cash_drift), abs(recon_drift))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None,
                    help="Audit only this model (default: all models)")
    ap.add_argument("--verbose", action="store_true",
                    help="Show breakdown for every model, not just drifted ones")
    ap.add_argument("--threshold", type=float, default=1.0,
                    help="Drift threshold in ₹ — exit 1 if any model exceeds")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    from src.models.database import get_database_manager
    from src.models.model_ledger_models import ModelLedger
    db = get_database_manager()
    max_drift = 0.0
    with db.get_session() as s:
        if args.model:
            max_drift = audit_one(s, args.model, args.verbose)
        else:
            names = [r.model_name for r in s.query(ModelLedger.model_name).all()]
            for name in sorted(names):
                d = audit_one(s, name, args.verbose)
                max_drift = max(max_drift, d)
    if max_drift > args.threshold:
        log.error(f"Max drift ₹{max_drift:.2f} exceeds threshold ₹{args.threshold}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
