"""One-shot reconciliation: fix CNC brokerage over-charge + distribute
unallocated Fyers cash equally across enabled models.

Steps:
  1. Re-compute charges_inr + charges_breakdown for every audit_orders row
     with product=CNC using the corrected broker_charges.compute_charges
     (CNC brokerage now zero — Fyers free delivery).
  2. Refund the over-charge to the corresponding model_ledger.cash
     (synthetic phantom deduction that never happened in real Fyers).
  3. Pull live Fyers funds + holdings, compute unallocated cash gap
     (Fyers cash − sum of model_ledger.cash).
  4. Distribute the unallocated cash equally across the 4 enabled models
     via deposit() — increases invested_amount + current_amount + cash
     by the same delta per model.
  5. Print before/after balance sheet for verification.

Idempotent: if a CNC row has already been corrected (matches new compute),
no further refund happens. Safe to re-run.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

from sqlalchemy import text

from src.models.database import get_database_manager
from src.services.trading.model_ledger_service import deposit
from tools.live.broker_charges import compute_charges


def _q(d) -> Decimal:
    return Decimal(str(d or 0))


def _fyers_cash() -> Decimal:
    """Pull Available Balance via Fyers v3 /funds."""
    import requests

    db = get_database_manager()
    with db.get_session() as s:
        r = s.execute(text(
            "SELECT api_key, access_token, client_id FROM broker_configurations "
            "WHERE broker_name='fyers' AND user_id=1 AND is_active=true "
            "ORDER BY id DESC LIMIT 1"
        )).fetchone()
    if not r:
        raise RuntimeError("No active Fyers broker_configurations row for user_id=1")
    api_key = r.api_key or r.client_id
    headers = {"Authorization": f"{api_key}:{r.access_token}"}
    resp = requests.get("https://api-t1.fyers.in/api/v3/funds",
                        headers=headers, timeout=15)
    d = resp.json()
    for item in d.get("fund_limit", []):
        if item.get("title") == "Available Balance":
            return Decimal(str(item.get("equityAmount", 0)))
    raise RuntimeError(f"Available Balance not found in funds response: {d}")


def step1_backfill_cnc_charges():
    print("\n=== STEP 1: re-compute CNC audit_orders charges ===")
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.execute(text(
            "SELECT id, model_name, side, symbol, fill_qty, fill_price, "
            "product, charges_inr, charges_breakdown "
            "FROM audit_orders WHERE UPPER(product) IN ('CNC','DELIVERY','MARGIN') "
            "AND status IN ('placed','filled','partial') "
            "ORDER BY id"
        )).fetchall()
        if not rows:
            print("  no CNC rows found")
            return
        for r in rows:
            new_bd = compute_charges(r.side, int(r.fill_qty or 0),
                                     float(r.fill_price or 0), r.product or "CNC")
            new_total = _q(new_bd.get("total", 0))
            old_total = _q(r.charges_inr or 0)
            delta = old_total - new_total  # over-charge amount to refund
            print(f"  id={r.id} {r.model_name} {r.side} {r.symbol}: "
                  f"old=₹{old_total:.4f}  new=₹{new_total:.4f}  refund=₹{delta:.4f}")
            if delta <= Decimal("0.001"):
                print("    already correct, skip")
                continue
            s.execute(text(
                "UPDATE audit_orders SET charges_inr = :c, charges_breakdown = :b "
                "WHERE id = :id"
            ), {"c": float(new_total), "b": json.dumps(new_bd), "id": r.id})
            ledger = s.execute(text(
                "SELECT cash FROM model_ledger WHERE model_name = :m"
            ), {"m": r.model_name}).fetchone()
            if not ledger:
                print(f"    WARN: no ledger row for {r.model_name}")
                continue
            new_cash = _q(ledger.cash) + delta
            s.execute(text(
                "UPDATE model_ledger SET cash = :c WHERE model_name = :m"
            ), {"c": float(new_cash), "m": r.model_name})
            print(f"    {r.model_name}: cash ₹{float(ledger.cash):.2f} → "
                  f"₹{float(new_cash):.2f} (+₹{delta:.2f})")
        s.commit()


def step3_compute_unallocated() -> Decimal:
    print("\n=== STEP 2: compute Fyers ↔ system cash gap ===")
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.execute(text(
            "SELECT model_name, cash FROM model_ledger"
        )).fetchall()
    sys_cash = sum(_q(r.cash) for r in rows)
    fy_cash = _fyers_cash()
    gap = fy_cash - sys_cash
    print(f"  system_cash_sum: ₹{sys_cash:.2f}")
    print(f"  fyers_cash:      ₹{fy_cash:.2f}")
    print(f"  unallocated:     ₹{gap:.2f}")
    return gap


def step4_distribute(gap: Decimal):
    print("\n=== STEP 3: distribute unallocated equally across enabled models ===")
    if gap <= Decimal("0.50"):
        print(f"  gap ₹{gap:.2f} too small; skipping")
        return
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.execute(text(
            "SELECT model_name FROM model_settings WHERE enabled = TRUE "
            "ORDER BY model_name"
        )).fetchall()
    models = [r.model_name for r in rows]
    n = len(models)
    if n == 0:
        print("  no enabled models")
        return
    per_model = (gap / Decimal(n)).quantize(Decimal("0.01"))
    distributed = per_model * Decimal(n)
    residual = gap - distributed  # may be a few paise
    print(f"  {n} enabled models, ₹{per_model} per model "
          f"(residual ₹{residual:.4f} stays in Fyers cash)")
    for m in models:
        deposit(m, float(per_model))
        print(f"    deposited ₹{per_model} → {m}")


def step5_print_snapshot():
    print("\n=== STEP 4: final snapshot ===")
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.execute(text(
            "SELECT model_name, invested_amount, current_amount, enabled "
            "FROM model_settings ORDER BY model_name"
        )).fetchall()
        ledger = {r.model_name: r for r in s.execute(text(
            "SELECT model_name, cash, open_symbol, open_qty, open_entry_px, "
            "realized_pnl FROM model_ledger"
        )).fetchall()}
    tot_inv = Decimal(0)
    tot_cash = Decimal(0)
    for r in settings:
        L = ledger.get(r.model_name)
        cash = _q(L.cash) if L else Decimal(0)
        print(f"  {r.model_name:40s} inv=₹{float(r.invested_amount):10.2f} "
              f"cash=₹{float(cash):10.2f} en={r.enabled}")
        tot_inv += _q(r.invested_amount)
        tot_cash += cash
    fy_cash = _fyers_cash()
    print(f"  TOTAL invested: ₹{tot_inv:.2f}")
    print(f"  TOTAL cash:     ₹{tot_cash:.2f}")
    print(f"  Fyers cash:     ₹{fy_cash:.2f}")
    print(f"  remaining gap:  ₹{fy_cash - tot_cash:.2f}")


if __name__ == "__main__":
    step1_backfill_cnc_charges()
    gap = step3_compute_unallocated()
    step4_distribute(gap)
    step5_print_snapshot()
