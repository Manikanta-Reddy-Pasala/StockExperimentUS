"""Reset a single model (or all 4 equity models) to a clean seed state.

Usage:
    docker exec trading_system_app python /app/tools/admin/reset_model_to_seed.py --all --seed 30000
    docker exec trading_system_app python /app/tools/admin/reset_model_to_seed.py --model n20_daily_large_only --seed 30000

Per-model isolation guarantee: each model trades only within its own
seed + its own realized P&L. Cannot use other models' cash. The reset
zeros out positions, realized_pnl, and trade counters, and sets
invested_amount = current_amount = cash = SEED. Legacy audit-trail
rows tagged BOOTSTRAP_* / REATTRIBUTED_* are purged.

Usage from user-facing settings UI: hit the "Reset to seed" button on
the per-model detail page (calls /admin/<m>/reset POST).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

sys.path.insert(0, "/app")
from src.models.database import DatabaseManager
from src.models.model_ledger_models import ModelLedger, ModelSettings, ModelTrade

EQUITY_MODELS = [
    "momentum_n100_top5_max1",
    "momentum_pseudo_n100_adv",
    "midcap_narrow_60d_breakout",
    "n20_daily_large_only",
]
LEGACY_REASONS = ("BOOTSTRAP_POSITION", "BOOTSTRAP_DEPOSIT", "REATTRIBUTED_PSEUDO")


def reset_model(db, model_name: str, seed: int) -> dict:
    settings = db.query(ModelSettings).filter_by(model_name=model_name).first()
    ledger = db.query(ModelLedger).filter_by(model_name=model_name).first()
    if not settings or not ledger:
        return {"model_name": model_name, "ok": False, "reason": "row missing"}

    snapshot = {
        "prev_invested": float(settings.invested_amount or 0),
        "prev_cash": float(ledger.cash or 0),
        "prev_nav": float(settings.current_amount or 0),
        "had_position": ledger.open_symbol,
    }

    settings.invested_amount = seed
    settings.current_amount = seed
    settings.enabled = True
    ledger.cash = seed
    ledger.open_symbol = None
    ledger.open_qty = None
    ledger.open_entry_px = None
    ledger.open_entry_date = None
    ledger.realized_pnl = 0
    ledger.total_trades = 0
    ledger.wins = 0
    ledger.losses = 0

    db.add(ModelTrade(
        model_name=model_name,
        side="DEPOSIT",
        symbol="-",
        qty=0,
        price=0.0,
        value=float(seed),
        pnl=None,
        reason="ISOLATION_RESET",
        trade_at=datetime.now(),
    ))

    return {"model_name": model_name, "ok": True, **snapshot, "new_seed": seed}


def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--all", action="store_true",
                     help="Reset all 4 equity models")
    grp.add_argument("--model", help="Reset a single model by name")
    ap.add_argument("--seed", type=int, default=30000,
                    help="Seed capital per model (default ₹30,000)")
    ap.add_argument("--purge-legacy", action="store_true",
                    help="Also delete legacy BOOTSTRAP/REATTRIBUTED audit rows")
    args = ap.parse_args()

    targets = EQUITY_MODELS if args.all else [args.model]

    dbm = DatabaseManager()
    with dbm.get_session() as db:
        results = [reset_model(db, m, args.seed) for m in targets]

        if args.purge_legacy:
            legacy = db.query(ModelTrade).filter(
                ModelTrade.reason.in_(LEGACY_REASONS)
            ).all()
            for t in legacy:
                print(f"  PURGE legacy: {t.model_name} {t.side} {t.symbol} reason={t.reason}")
                db.delete(t)

        db.commit()

        for r in results:
            if r["ok"]:
                print(f"  RESET {r['model_name']:30s} "
                      f"invested {r['prev_invested']:,.0f}→{r['new_seed']:,}, "
                      f"cash {r['prev_cash']:,.0f}→{r['new_seed']:,}, "
                      f"pos {'cleared' if r['had_position'] else 'none'}")
            else:
                print(f"  SKIP  {r['model_name']:30s} {r['reason']}")


if __name__ == "__main__":
    main()
