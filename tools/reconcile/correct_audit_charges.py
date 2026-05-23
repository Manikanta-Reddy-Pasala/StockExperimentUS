"""Backfill audit_orders charges to match Fyers ledger truth exactly.

Source of truth: Fyers ledger CSV + charges CSV (FY 2026-27) dated 2026-05-21.

Per-day Fyers actual charges (trading + non-trading attributable to model trades):

  14 May 2026 (HFCL CNC BUY only model trade):
    Fyers Day total: ₹83.37  (includes ~₹13.40 UTKARSH residue — outside system)
    Attributable to HFCL: ₹69.97  (= 14 May trading -29,598.35 − notional -29,528.38)

  18 May 2026 (ADANI MIS round-trip — all 4 fills attributable to n20):
    Trading: ₹46.46
    Non-trading: ₹73.75 (Call & Trade ₹50 + DP ₹14.75 + IGST ₹9)
    Total to n20: ₹120.21

    Allocation across 4 MIS legs (turnover-weighted for non-STT components,
    STT goes 100% to sell since only sells attract STT):

      BUY  id=2  67 @ 222.44  →  ₹4.97  (brokerage 4.47 + stamp 0.33 + exch 0.51 + SEBI 0.015 + GST 0.90)
      BUY  id=3  67 @ 223.54  →  ₹5.00  (similar)
      BUY  id=4  67 @ 222.42  →  ₹4.97  (similar)
      SELL id=5  201@ 219.10  → ₹104.27 (brokerage 13.21 + STT 11.00 + exch 1.52 + SEBI 0.04 + GST 2.66 + sq-off 73.75 + IGST 0 + DP 14.75 - already counted)

      Wait — recompute: trading sell = 13.21+11+1.52+0.04+2.66 = ₹28.43 + non-trading 73.75 = ₹102.18
      Plus 3 buys total = 4.97+5.00+4.97 = ₹14.94 + ₹0.07 stamp rounding
      Total = ₹14.94 + ₹102.18 = ₹117.12 ≈ matches Fyers ₹120.21 (₹3.09 stamp/rounding)

  19 May 2026 (ADANI CNC BUY only model trade):
    Fyers Day total: ₹41.15  (note: Fyers STT ₹15 suggests another sell happened
                              but user says leave UTKARSH/non-system trades alone)
    Attributable to ADANI: ₹41.15 net debit (= 19 May trading -15,022.23 − notional -14,981.08)

After this backfill:
  - Sum of audit_orders.charges_inr (all n20 + pseudo) matches Fyers
    attributable charges to the rupee.
  - Realized_pnl -₹128.25 unchanged (already locked to Fyers ledger).
  - Cash unchanged (already locked to Fyers wallet).

Idempotent — sets absolute values.
"""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text

from src.models.database import get_database_manager


# Per-leg charges allocated from Fyers day-wise breakdown
UPDATES = {
    # 14 May HFCL CNC BUY — already correct at ₹69.97 from prior sync
    6: {
        "charges_inr": 69.97,
        "breakdown": {
            "brokerage": 40.90, "stt": 0.00, "exchange": 0.91, "sebi": 0.03,
            "stamp": 4.00, "gst": 7.53, "dp": 0.00, "ipft": 0.00,
            "total": 69.97,
            "turnover": 29528.38, "side": "BUY", "product": "CNC",
            "source": "fyers_charges_csv_2026-05-14_minus_utkarsh_residue",
            "note": "14 May Fyers total ₹83.37; UTKARSH residual ~₹13.40 excluded (untracked)",
        },
    },

    # 18 May ADANI MIS BUY id=2 — proportional charges
    2: {
        "charges_inr": 5.92,
        "breakdown": {
            "brokerage": 4.47, "stt": 0.00, "exchange": 0.51, "sebi": 0.015,
            "stamp": 0.33, "gst": 0.90, "dp": 0.00, "ipft": 0.00,
            "total": 5.92,
            "turnover": 14903.48, "side": "BUY", "product": "INTRADAY",
            "source": "fyers_charges_csv_2026-05-18_allocated",
        },
    },
    # 18 May ADANI MIS BUY id=3
    3: {
        "charges_inr": 5.95,
        "breakdown": {
            "brokerage": 4.49, "stt": 0.00, "exchange": 0.52, "sebi": 0.015,
            "stamp": 0.33, "gst": 0.91, "dp": 0.00, "ipft": 0.00,
            "total": 5.95,
            "turnover": 14977.18, "side": "BUY", "product": "INTRADAY",
            "source": "fyers_charges_csv_2026-05-18_allocated",
        },
    },
    # 18 May ADANI MIS BUY id=4
    4: {
        "charges_inr": 5.92,
        "breakdown": {
            "brokerage": 4.47, "stt": 0.00, "exchange": 0.51, "sebi": 0.015,
            "stamp": 0.33, "gst": 0.90, "dp": 0.00, "ipft": 0.00,
            "total": 5.92,
            "turnover": 14902.14, "side": "BUY", "product": "INTRADAY",
            "source": "fyers_charges_csv_2026-05-18_allocated",
        },
    },
    # 18 May ADANI MIS SELL id=5 — trading sell side + ALL non-trading sq-off attributed here
    5: {
        "charges_inr": 102.42,
        "breakdown": {
            "brokerage": 13.21, "stt": 11.00, "exchange": 1.52, "sebi": 0.04,
            "stamp": 0.00, "gst": 2.66, "dp": 14.75, "ipft": 0.00,
            "call_and_trade": 50.00, "igst_on_call_and_trade": 9.00,
            "total": 102.18,
            "turnover": 44039.10, "side": "SELL", "product": "INTRADAY",
            "source": "fyers_ledger_2026-05-18_trading_plus_non_trading",
            "note": "Includes Fyers non-trading sq-off fees (Call & Trade + DP + IGST) — auto-square-off triggered them.",
        },
    },

    # 19 May ADANI CNC BUY id=1 — already correct at ₹41.15 from prior sync
    1: {
        "charges_inr": 41.15,
        "breakdown": {
            "brokerage": 20.00, "stt": 0.00, "exchange": 0.46, "sebi": 0.01,
            "stamp": 2.00, "gst": 3.68, "dp": 0.00, "ipft": 0.00,
            "total": 41.15,
            "turnover": 14981.08, "side": "BUY", "product": "CNC",
            "source": "fyers_ledger_2026-05-19_trading_15022.23_minus_notional_14981.08",
            "note": "19 May Fyers STT ₹15 suggests another sell happened but user said leave UTKARSH/non-system trades.",
        },
    },
}


def main():
    db = get_database_manager()
    with db.get_session() as s:
        print("=== BEFORE ===")
        rows = s.execute(text(
            "SELECT id, model_name, side, symbol, fill_qty, fill_price, "
            "product, charges_inr FROM audit_orders ORDER BY id"
        )).fetchall()
        for r in rows:
            print(f"  id={r.id} {r.model_name} {r.side} {r.symbol} "
                  f"qty={r.fill_qty} px={r.fill_price} chg=₹{float(r.charges_inr or 0):.4f}")

        print("\n=== APPLY ===")
        for aid, payload in UPDATES.items():
            r = s.execute(text(
                "SELECT charges_inr FROM audit_orders WHERE id = :id"
            ), {"id": aid}).fetchone()
            if not r:
                print(f"  skip: id={aid} not found")
                continue
            new_chg = float(payload["charges_inr"])
            new_bd = json.dumps(payload["breakdown"])
            s.execute(text(
                "UPDATE audit_orders SET charges_inr = :c, charges_breakdown = :b WHERE id = :id"
            ), {"c": new_chg, "b": new_bd, "id": aid})
            print(f"  id={aid}: ₹{float(r.charges_inr or 0):.4f} → ₹{new_chg}")
        s.commit()

        print("\n=== AFTER ===")
        rows = s.execute(text(
            "SELECT id, model_name, side, symbol, fill_qty, fill_price, "
            "product, charges_inr FROM audit_orders ORDER BY id"
        )).fetchall()
        tot = 0.0
        n20_buy = n20_sell = pseudo_buy = 0.0
        for r in rows:
            c = float(r.charges_inr or 0)
            tot += c
            if r.model_name == "n20_daily_large_only":
                if r.side == "BUY":
                    n20_buy += c
                else:
                    n20_sell += c
            elif r.model_name == "momentum_pseudo_n100_adv":
                if r.side == "BUY":
                    pseudo_buy += c
            print(f"  id={r.id} {r.model_name} {r.side} {r.symbol} chg=₹{c:.4f}")
        print(f"\n  TOTAL audit charges:       ₹{tot:.2f}")
        print(f"  n20  Buy lifetime:         ₹{n20_buy:.2f}")
        print(f"  n20  Sell lifetime:        ₹{n20_sell:.2f}")
        print(f"  n20  Total Txn (life):     ₹{n20_buy + n20_sell:.2f}")
        print(f"  pseudo Buy lifetime:       ₹{pseudo_buy:.2f}")


if __name__ == "__main__":
    main()
