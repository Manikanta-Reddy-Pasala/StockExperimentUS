"""Sync model_ledger cash + realized + audit_orders charges to actual
Fyers ledger truth (from /web/reports/ledger UI).

Hard-coded values come from Fyers ledger images dated 2026-05-21:

  14 May 2026  Trading debit ₹29,598.35  (HFCL CNC buy, qty 203 @ 145.46)
    notional 29,528.38 + actual Fyers charges 69.97 → cash out 29,598.35
  18 May 2026  Trading debit ₹54.50 + Non-trading ₹73.75 (₹50 Call&Trade + ₹14.75 DP + ₹9 IGST)
    net cash out 128.25 = realized loss for n20 MIS round-trip (3 buys + 1 sell)
  19 May 2026  Trading debit ₹15,022.23 (ADANI CNC buy, qty 68 @ 220.31)
    notional 14,981.08 + actual Fyers charges 41.15 → cash out 15,022.23

Effects:
  - audit_orders id=6 (HFCL):       charges_inr 5.67 → 69.97
  - audit_orders id=1 (ADANI CNC):  charges_inr 2.87 → 41.15
  - model_ledger pseudo.cash:       465.95 → 401.65 (refund -64.30)
  - model_ledger n20.cash:        14,224.83 → 14,849.52 (refund +624.69)
  - model_ledger n20.realized_pnl: -772.14 → -128.25 (gain 643.89)

After this, total system cash == Fyers Available Balance exactly:
  midcap 30,000 + n100 30,000 + pseudo 401.65 + n20 14,849.52 = 75,251.17 ✓

MIS audit rows (id=2..5) left as-is — their synthetic per-trade charges
are approximations; canonical truth lives in the 18 May trading/non-trading
ledger sum (₹128.25), already booked as n20.realized_pnl.

Run once. Idempotent: re-running won't double-apply because values are
absolute, not delta-based.
"""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text

from src.models.database import get_database_manager


# Values pulled from Fyers ledger screenshots dated 2026-05-21
FYERS_TRUTH = {
    "audit_charges": {
        # audit_orders.id : (new_charges_inr, summary)
        6: (Decimal("69.97"), "HFCL CNC buy — Fyers ledger 14 May trading 29,598.35 − notional 29,528.38"),
        1: (Decimal("41.15"), "ADANI CNC buy — Fyers ledger 19 May trading 15,022.23 − notional 14,981.08"),
    },
    "ledger_cash": {
        "momentum_pseudo_n100_adv": Decimal("401.65"),
        "n20_daily_large_only":     Decimal("14849.52"),
    },
    "ledger_realized": {
        "n20_daily_large_only": Decimal("-128.25"),
    },
}


def main():
    db = get_database_manager()
    with db.get_session() as s:
        print("=== BEFORE ===")
        rows = s.execute(text(
            "SELECT model_name, cash, realized_pnl FROM model_ledger ORDER BY model_name"
        )).fetchall()
        for r in rows:
            print(f"  {r.model_name:40s} cash=₹{float(r.cash or 0):10.2f} "
                  f"realized=₹{float(r.realized_pnl or 0):8.2f}")
        for aid, (_v, _label) in FYERS_TRUTH["audit_charges"].items():
            r = s.execute(text(
                "SELECT id, side, symbol, charges_inr FROM audit_orders WHERE id = :id"
            ), {"id": aid}).fetchone()
            if r:
                print(f"  audit id={aid} {r.side} {r.symbol}: chg ₹{float(r.charges_inr or 0):.4f}")

        print("\n=== APPLY ===")
        # 1. Update audit_orders charges
        for aid, (new_chg, label) in FYERS_TRUTH["audit_charges"].items():
            r = s.execute(text(
                "SELECT charges_inr, charges_breakdown FROM audit_orders WHERE id = :id"
            ), {"id": aid}).fetchone()
            if not r:
                print(f"  skip: audit_orders id={aid} not found")
                continue
            old_bd = r.charges_breakdown or {}
            new_bd = dict(old_bd) if isinstance(old_bd, dict) else {}
            new_bd["total"] = float(new_chg)
            new_bd["note"] = label
            new_bd["source"] = "fyers_ledger_2026-05-21"
            s.execute(text(
                "UPDATE audit_orders SET charges_inr = :c, charges_breakdown = :b WHERE id = :id"
            ), {"c": float(new_chg), "b": json.dumps(new_bd), "id": aid})
            print(f"  audit id={aid}: charges_inr ₹{float(r.charges_inr or 0):.4f} → ₹{new_chg}")

        # 2. Set model_ledger.cash to Fyers truth
        for mname, new_cash in FYERS_TRUTH["ledger_cash"].items():
            r = s.execute(text(
                "SELECT cash FROM model_ledger WHERE model_name = :m"
            ), {"m": mname}).fetchone()
            if not r:
                print(f"  skip: model_ledger {mname} not found")
                continue
            s.execute(text(
                "UPDATE model_ledger SET cash = :c WHERE model_name = :m"
            ), {"c": float(new_cash), "m": mname})
            print(f"  ledger {mname}.cash: ₹{float(r.cash or 0):.2f} → ₹{new_cash}")

        # 3. Set model_ledger.realized_pnl to Fyers truth
        for mname, new_rl in FYERS_TRUTH["ledger_realized"].items():
            r = s.execute(text(
                "SELECT realized_pnl FROM model_ledger WHERE model_name = :m"
            ), {"m": mname}).fetchone()
            if not r:
                continue
            s.execute(text(
                "UPDATE model_ledger SET realized_pnl = :v WHERE model_name = :m"
            ), {"v": float(new_rl), "m": mname})
            print(f"  ledger {mname}.realized_pnl: ₹{float(r.realized_pnl or 0):.2f} → ₹{new_rl}")

        # 4. Reset model_settings.current_amount cache (recomputed elsewhere on live MTM)
        for mname in FYERS_TRUTH["ledger_cash"]:
            s.execute(text(
                "UPDATE model_settings SET current_amount = invested_amount WHERE model_name = :m"
            ), {"m": mname})

        s.commit()

        print("\n=== AFTER ===")
        rows = s.execute(text(
            "SELECT model_name, cash, realized_pnl FROM model_ledger ORDER BY model_name"
        )).fetchall()
        tot_cash = Decimal(0)
        for r in rows:
            cash = Decimal(str(r.cash or 0))
            tot_cash += cash
            print(f"  {r.model_name:40s} cash=₹{float(cash):10.2f} "
                  f"realized=₹{float(r.realized_pnl or 0):8.2f}")
        print(f"  TOTAL cash: ₹{tot_cash:,.2f}")


if __name__ == "__main__":
    main()
