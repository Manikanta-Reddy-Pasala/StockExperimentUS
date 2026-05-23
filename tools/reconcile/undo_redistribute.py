"""Undo the ₹140.10 × 4 deposit done by
`cnc_brokerage_backfill_and_redistribute.py` step 4. User clarified
that real invested capital is ₹1,20,000 (+ negligible UTKARSH ~₹15),
not ₹1,20,560.40. The ₹560.39 unallocated cash is Fyers wallet float,
not fresh model capital — should not inflate invested_amount.

Strategy:
- Find the most recent DEPOSIT trade per enabled model
- Reverse it: invested_amount -= amt, current_amount -= amt, cash -= amt
- Delete the DEPOSIT model_trades row
- Print before/after

Safe to run once. Re-running would over-subtract.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from src.models.database import get_database_manager


REDISTRIBUTE_AMT = Decimal("140.10")  # the per-model deposit done earlier


def main():
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.execute(text(
            "SELECT model_name, invested_amount, current_amount FROM model_settings "
            "WHERE enabled = TRUE ORDER BY model_name"
        )).fetchall()
        print("BEFORE undo:")
        for r in rows:
            print(f"  {r.model_name:40s} inv=₹{float(r.invested_amount):.2f} "
                  f"cur=₹{float(r.current_amount):.2f}")
        print()

        # Reverse each model's most-recent DEPOSIT trade
        for r in rows:
            # Update settings + ledger
            s.execute(text(
                "UPDATE model_settings SET "
                "invested_amount = invested_amount - :a, "
                "current_amount = current_amount - :a "
                "WHERE model_name = :m"
            ), {"a": float(REDISTRIBUTE_AMT), "m": r.model_name})
            s.execute(text(
                "UPDATE model_ledger SET cash = cash - :a WHERE model_name = :m"
            ), {"a": float(REDISTRIBUTE_AMT), "m": r.model_name})
            # Drop the DEPOSIT trade row for traceability
            s.execute(text(
                "DELETE FROM model_trades WHERE id IN ("
                "  SELECT id FROM model_trades "
                "  WHERE model_name = :m AND side = 'DEPOSIT' AND value = :a "
                "  ORDER BY id DESC LIMIT 1"
                ")"
            ), {"m": r.model_name, "a": float(REDISTRIBUTE_AMT)})
            print(f"  undone ₹{REDISTRIBUTE_AMT} for {r.model_name}")

        s.commit()
        print()

        rows = s.execute(text(
            "SELECT m.model_name, m.invested_amount, m.current_amount, l.cash "
            "FROM model_settings m LEFT JOIN model_ledger l "
            "  ON m.model_name = l.model_name "
            "WHERE m.enabled = TRUE ORDER BY m.model_name"
        )).fetchall()
        print("AFTER undo:")
        tot_inv = tot_cash = Decimal(0)
        for r in rows:
            inv = Decimal(str(r.invested_amount or 0))
            cur = Decimal(str(r.current_amount or 0))
            cash = Decimal(str(r.cash or 0))
            tot_inv += inv
            tot_cash += cash
            print(f"  {r.model_name:40s} inv=₹{float(inv):.2f} "
                  f"cur=₹{float(cur):.2f} cash=₹{float(cash):.2f}")
        print(f"  TOTAL invested: ₹{tot_inv:.2f}")
        print(f"  TOTAL cash:     ₹{tot_cash:.2f}")


if __name__ == "__main__":
    main()
