"""Recompute ModelTrade.value + pnl + ModelLedger.cash + realized_pnl
using the current approximate compute_charges formula.

Why: charges are now treated as approximate (formula-based, not Fyers-exact).
Historical ModelTrade rows + audit_orders had drifted between formula values,
Fyers cash-delta values, and manual sync values. This reconciler resets every
field to a single source of truth: the current compute_charges formula.

Algorithm (per model, chronological):
  Walk trades oldest→newest. Maintain open_qty + weighted entry_px.
    DEPOSIT: cash += value
    WITHDRAW: cash -= value
    BUY:
      buy_chg = compute_charges("BUY", qty, price, "CNC")
      cost    = qty*price + buy_chg
      cash   -= cost
      weighted entry_px = ((prev_qty*prev_px) + (qty*price)) / (prev_qty+qty)
      open_qty += qty
      row.value = cost ; row.pnl = NULL
    SELL:
      sell_chg = compute_charges("SELL", qty, price, "CNC")
      net      = qty*price - sell_chg
      cash    += net
      pnl      = net - qty*entry_px
      realized_pnl += pnl
      open_qty = 0 ; entry_px = 0
      row.value = net ; row.pnl = pnl

After loop, update ModelLedger.cash + realized_pnl + total_trades + wins + losses.

Idempotent: re-runnable. Dry-run mode supported.
"""
from __future__ import annotations
import argparse
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.models.database import get_database_manager  # noqa: E402
from src.models.model_ledger_models import ModelLedger, ModelTrade  # noqa: E402
from tools.live.broker_charges import compute_charges  # noqa: E402


def _chg(side: str, qty: int, price: float) -> Decimal:
    if qty < 1 or price <= 0:
        return Decimal("0")
    br = compute_charges(side, qty, float(price), "CNC")
    return Decimal(str(br.get("total", 0)))


def recompute_model(model_name: str, dry_run: bool = False) -> dict:
    db = get_database_manager()
    with db.get_session() as s:
        trades = (s.query(ModelTrade)
                    .filter_by(model_name=model_name)
                    .order_by(ModelTrade.trade_at.asc(),
                              ModelTrade.id.asc())
                    .all())
        if not trades:
            return {"model": model_name, "trades": 0, "skipped": True}

        cash = Decimal("0")
        realized = Decimal("0")
        open_qty = Decimal("0")
        entry_px = Decimal("0")
        total_trades = 0
        wins = 0
        losses = 0
        changes = []

        for t in trades:
            side = (t.side or "").upper()
            qty = int(t.qty or 0)
            price = Decimal(str(t.price or 0))

            if side == "DEPOSIT":
                cash += Decimal(str(t.value or 0))
                continue
            if side == "WITHDRAW":
                cash -= Decimal(str(t.value or 0))
                continue

            if side == "BUY":
                buy_chg = _chg("BUY", qty, float(price))
                cost = Decimal(str(qty)) * price + buy_chg
                cash -= cost
                # weighted avg entry
                new_open = open_qty + Decimal(str(qty))
                if new_open > 0:
                    entry_px = ((open_qty * entry_px) +
                                (Decimal(str(qty)) * price)) / new_open
                open_qty = new_open
                new_value = cost
                new_pnl = None
            elif side == "SELL":
                sell_chg = _chg("SELL", qty, float(price))
                net = Decimal(str(qty)) * price - sell_chg
                cash += net
                pnl = net - Decimal(str(qty)) * entry_px
                realized += pnl
                total_trades += 1
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
                open_qty = Decimal("0")
                entry_px = Decimal("0")
                new_value = net
                new_pnl = pnl
            else:
                continue

            old_value = t.value
            old_pnl = t.pnl
            row_changed = (
                Decimal(str(old_value or 0)).quantize(Decimal("0.0001"))
                != new_value.quantize(Decimal("0.0001"))
            ) or (
                (old_pnl is None) != (new_pnl is None)
            ) or (
                old_pnl is not None and new_pnl is not None and
                Decimal(str(old_pnl)).quantize(Decimal("0.0001"))
                != new_pnl.quantize(Decimal("0.0001"))
            )
            if row_changed:
                changes.append({
                    "id": t.id, "side": side, "qty": qty,
                    "price": float(price),
                    "old_value": float(old_value or 0),
                    "new_value": float(new_value),
                    "old_pnl": float(old_pnl) if old_pnl is not None else None,
                    "new_pnl": float(new_pnl) if new_pnl is not None else None,
                })
                if not dry_run:
                    t.value = new_value
                    t.pnl = new_pnl

        # Update ledger totals
        ledger_changed = False
        ledger = (s.query(ModelLedger)
                    .filter_by(model_name=model_name).first())
        if ledger is not None:
            old_cash = Decimal(str(ledger.cash or 0))
            old_real = Decimal(str(ledger.realized_pnl or 0))
            if (old_cash.quantize(Decimal("0.0001"))
                != cash.quantize(Decimal("0.0001"))
                or old_real.quantize(Decimal("0.0001"))
                != realized.quantize(Decimal("0.0001"))
                or (ledger.total_trades or 0) != total_trades
                or (ledger.wins or 0) != wins
                or (ledger.losses or 0) != losses):
                ledger_changed = True
                if not dry_run:
                    ledger.cash = cash
                    ledger.realized_pnl = realized
                    ledger.total_trades = total_trades
                    ledger.wins = wins
                    ledger.losses = losses

        if not dry_run:
            s.commit()

        return {
            "model": model_name,
            "trades": len(trades),
            "row_changes": len(changes),
            "ledger_changed": ledger_changed,
            "new_cash": float(cash),
            "new_realized": float(realized),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "open_qty": float(open_qty),
            "entry_px": float(entry_px),
            "sample_changes": changes[:5],
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="Limit to one model name")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show changes without writing")
    args = ap.parse_args()

    db = get_database_manager()
    with db.get_session() as s:
        models = [m[0] for m in s.query(ModelLedger.model_name).all()]
        if args.model:
            models = [m for m in models if m == args.model]

    if not models:
        print("No models matched.")
        return

    print(f"{'DRY-RUN: ' if args.dry_run else ''}"
          f"Recomputing trade pnl for {len(models)} model(s) "
          f"via approx formula...\n")
    for m in models:
        try:
            r = recompute_model(m, dry_run=args.dry_run)
        except Exception as e:
            print(f"  {m}: ERROR — {e}")
            continue
        if r.get("skipped"):
            print(f"  {m}: no trades, skipped")
            continue
        print(f"  {m}:")
        print(f"    trades={r['trades']}  row_changes={r['row_changes']}  "
              f"ledger_changed={r['ledger_changed']}")
        print(f"    new cash=₹{r['new_cash']:,.2f}  "
              f"realized=₹{r['new_realized']:,.2f}  "
              f"W/L={r['wins']}/{r['losses']}  open={r['open_qty']:.0f}")
        for c in r.get("sample_changes", []):
            old_pnl = ('—' if c['old_pnl'] is None
                       else f"₹{c['old_pnl']:,.2f}")
            new_pnl = ('—' if c['new_pnl'] is None
                       else f"₹{c['new_pnl']:,.2f}")
            print(f"      id={c['id']} {c['side']} {c['qty']}@{c['price']}: "
                  f"val ₹{c['old_value']:,.2f}→₹{c['new_value']:,.2f}, "
                  f"pnl {old_pnl}→{new_pnl}")
    print(("\nDRY-RUN complete — no writes." if args.dry_run
           else "\nWrites committed."))


if __name__ == "__main__":
    main()
