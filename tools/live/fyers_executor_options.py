"""Fyers F&O multi-leg executor (Iron Condor / spread strategies).

Reads a 4-leg signal JSON (BUY/SELL × 4 option symbols) and places each leg
as a MARKET order with product=MARGIN (carry-forward F&O / NRML).

Always live. Use --dry-run for manual dry runs only.
Writes every fill to audit_orders so charges, slippage, and fill price are
tracked the same way as equity orders.

Designed for monthly Iron Condor holds (finnifty_ic_otm4_w300_lots5) but
generic enough to drive any 2-8 leg defined-risk options strategy.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _place_leg(svc, user_id: int, sig: Dict, product: str, dry: bool,
               use_limit_walk: bool = False) -> Dict:
    symbol = sig["symbol"]
    side = sig["side"].upper()
    qty = int(sig["qty"])
    tag = f"{sig.get('model', 'options')}:{sig.get('leg', '')}"[:20]
    if dry:
        ptype = "LIMIT-WALK" if use_limit_walk else "MARKET"
        log.info(f"DRY-RUN {side} {symbol} qty={qty} product={product} "
                 f"pricetype={ptype} tag={tag}")
        return {"status": "dry-run", "order_id": "DRY",
                "symbol": symbol, "side": side, "qty": qty}
    if use_limit_walk:
        from tools.live.option_depth_check import limit_walk
        return limit_walk(svc, user_id, symbol, side, qty, product, tag)
    try:
        res = svc.placeorder(
            user_id=user_id, symbol=symbol, quantity=str(qty),
            action=side, product=product, pricetype="MARKET",
            price="0", validity="DAY", tag=tag,
        )
    except Exception as e:
        log.error(f"placeorder {side} {symbol} FAILED: {e}")
        return {"status": "error", "error": str(e),
                "symbol": symbol, "side": side, "qty": qty}
    status = "ok"
    order_id = ""
    if isinstance(res, dict):
        order_id = (res.get("data") or {}).get("orderid") or res.get("orderid") or ""
        if str(res.get("s", "")).lower() not in ("ok", "success"):
            status = str(res.get("message", res.get("s", "unknown")))
    return {"status": status, "order_id": order_id, "raw": res,
            "symbol": symbol, "side": side, "qty": qty,
            "pricetype": "MARKET"}


def _audit_leg(model_name: str, fill: Dict, price: float, product: str,
               dry: bool, depth: Optional[Dict] = None,
               margin_inr: Optional[float] = None) -> None:
    try:
        from src.services.audit_service import write_order
    except ImportError:
        log.debug("audit_service.write_order not available, skipping audit")
        return
    depth = depth or {}
    try:
        write_order(
            model_name=model_name,
            symbol=fill["symbol"],
            side=fill["side"],
            qty=fill["qty"],
            ordered_price=price,
            fill_price=price if not dry else None,
            fill_qty=fill["qty"] if not dry else None,
            fyers_order_id=fill.get("order_id", ""),
            product=product,
            pricetype=fill.get("pricetype", "MARKET"),
            status="dry-run" if dry else fill.get("status", "unknown"),
            raw_response=fill.get("raw") if isinstance(fill.get("raw"), dict) else None,
            bid_at_entry=depth.get("bid"),
            ask_at_entry=depth.get("ask"),
            spread_pct_at_entry=depth.get("spread_pct"),
            volume_at_entry=depth.get("volume"),
            oi_at_entry=depth.get("oi"),
            margin_blocked_inr=margin_inr,
        )
    except Exception as e:
        log.debug(f"audit write failed: {e}")


def _utilized_funds(svc, user_id: int) -> Optional[float]:
    """Pull Fyers utilized-funds for margin-delta computation.

    Returns None on any failure — audit row will store NULL for margin.
    """
    if svc is None:
        return None
    try:
        resp = svc.funds(user_id=user_id)
    except Exception as e:
        log.debug(f"funds() failed: {e}")
        return None
    if not isinstance(resp, dict):
        return None
    # Fyers v3 funds shape: {"s":"ok","fund_limit":[{"id":N,"title":"...","equityAmount":...}]}
    rows = resp.get("fund_limit") or resp.get("data") or []
    if isinstance(rows, list):
        for r in rows:
            title = str(r.get("title", "")).lower()
            if "utilized" in title or "used" in title:
                v = r.get("equityAmount") or r.get("commodityAmount") or r.get("amount")
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    # Fallback: try top-level fields
    for k in ("utilized", "utilizedAmount", "marginUtilized"):
        if k in resp:
            try:
                return float(resp[k])
            except (TypeError, ValueError):
                pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signals", required=True,
                    help="Path to signal JSON (list of leg dicts)")
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--product", default="MARGIN",
                    help="Fyers product: MARGIN (NRML carry-forward, default) "
                         "or INTRADAY (MIS, square-off same day)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print orders, don't place. Manual override only.")
    ap.add_argument("--no-depth-gate", action="store_true",
                    help="Skip L1 depth check before placing.")
    ap.add_argument("--max-spread-pct", type=float, default=0.15,
                    help="Reject basket if any leg spread > this fraction "
                         "of mid-price (default 0.15 = 15%%).")
    ap.add_argument("--min-volume", type=int, default=500,
                    help="Min day volume per leg (default 500).")
    ap.add_argument("--min-oi", type=int, default=5000,
                    help="Min OI per leg (default 5000).")
    ap.add_argument("--no-limit-walk", action="store_true",
                    help="Use MARKET for all legs. Default: shorts MARKET, "
                         "longs LIMIT-walk (better slippage on thin wings).")
    args = ap.parse_args()

    sig_path = Path(args.signals)
    if not sig_path.exists():
        log.error(f"signals file not found: {sig_path}")
        return 2
    signals: List[Dict] = json.loads(sig_path.read_text())
    if not signals:
        log.info(f"{args.model_name}: empty signal list, nothing to execute.")
        return 0

    # Order legs so we SELL premium first (collect credit), then BUY wings.
    # On EXIT, BUY-back the shorts first, then SELL the wings.
    signals_sorted = sorted(signals, key=lambda s: 0 if s["side"].upper() == "SELL" else 1)

    svc = None
    if not args.dry_run:
        from src.services.brokers.fyers_service import FyersService
        svc = FyersService()
        cfg = svc.get_broker_config(args.user_id)
        if not cfg or not cfg.get("access_token"):
            log.error(f"No Fyers token for user_id={args.user_id} — aborting")
            return 2

    log.info(f"Executing {len(signals_sorted)} legs for {args.model_name} "
             f"(product={args.product}, live={live}, dry_run={args.dry_run})")

    # Pre-trade liquidity gate (only when we have a live svc — otherwise
    # nothing to query). Abort the basket if any leg fails — partial fills
    # in defined-risk strategies leave open undefined risk.
    depth_by_symbol: Dict[str, Dict] = {}
    if svc is not None and not args.no_depth_gate:
        from tools.live.option_depth_check import gate_basket
        ok, report = gate_basket(
            svc, args.user_id, signals_sorted,
            max_spread_pct=args.max_spread_pct,
            min_volume=args.min_volume,
            min_oi=args.min_oi,
        )
        for r in report:
            log.info(f"  depth {r['symbol']:30} side={r.get('side','?'):4} "
                     f"bid={r.get('bid',0)} ask={r.get('ask',0)} "
                     f"spread={r.get('spread_pct',0)}% vol={r.get('volume',0)} "
                     f"oi={r.get('oi',0)} -> {r['reason']}")
            depth_by_symbol[r["symbol"]] = r
        if not ok:
            log.error("DEPTH GATE FAILED — aborting basket")
            try:
                from src.services.audit_service import write_rebalance_decision
                write_rebalance_decision(
                    model_name=args.model_name, trigger="CRON",
                    decision="OPTIONS_SKIP_THIN",
                    reason="; ".join(f"{r['symbol']}:{r['reason']}"
                                     for r in report if not r["ok"])[:500],
                )
            except Exception:
                pass
            return 3

    # Snapshot Fyers utilized-funds before placing — basket margin delta
    # will be computed after all legs are placed and stamped on every row.
    util_before = _utilized_funds(svc, args.user_id)
    if util_before is not None:
        log.info(f"  margin: utilized-before = ₹{util_before:,.2f}")

    placed = 0
    errors = 0
    audit_queue: List[tuple] = []  # [(fill, price, depth), ...] for post-margin stamp
    for sig in signals_sorted:
        # SELL legs (shorts) — liquid strikes near ATM, MARKET is fine.
        # BUY legs (long wings) — thin strikes, use LIMIT-walk to control slip.
        use_walk = (not args.no_limit_walk) and sig["side"].upper() == "BUY"
        fill = _place_leg(svc, args.user_id, sig, args.product, args.dry_run,
                          use_limit_walk=use_walk)
        leg_depth = depth_by_symbol.get(sig["symbol"])
        audit_queue.append((fill, float(sig.get("price", 0) or 0), leg_depth))
        if fill["status"] in ("ok", "success", "dry-run"):
            placed += 1
            log.info(f"  {fill['side']:4} {fill['symbol']:30} qty={fill['qty']:>4} "
                     f"order_id={fill.get('order_id', '')}")
        else:
            errors += 1
            log.error(f"  FAIL {fill['side']} {fill['symbol']}: {fill['status']}")

    # Snapshot Fyers utilized-funds after — delta is the margin blocked by
    # this basket (Iron-Condor margin is netted, much smaller than per-leg sum).
    margin_basket: Optional[float] = None
    util_after = _utilized_funds(svc, args.user_id)
    if util_before is not None and util_after is not None:
        margin_basket = max(0.0, util_after - util_before)
        log.info(f"  margin: utilized-after = ₹{util_after:,.2f} "
                 f"delta = ₹{margin_basket:,.2f}")

    # Now write audit rows with full depth + basket margin.
    for fill, price, leg_depth in audit_queue:
        _audit_leg(args.model_name, fill, price, args.product, args.dry_run,
                   depth=leg_depth, margin_inr=margin_basket)

    log.info(f"Done: placed={placed} errors={errors} "
             f"(live={live}, dry_run={args.dry_run}, "
             f"model={args.model_name})")

    # HOLD-style audit so we have one row per cron invocation
    try:
        from src.services.audit_service import write_rebalance_decision
        write_rebalance_decision(
            model_name=args.model_name,
            trigger="CRON" if not args.dry_run else "DRY",
            decision="OPTIONS_OPEN" if placed > 0 and errors == 0 else (
                "OPTIONS_PARTIAL" if placed > 0 else "OPTIONS_FAIL"),
            reason=f"{placed} legs placed, {errors} errors",
        )
    except Exception as e:
        log.debug(f"rebal audit write failed: {e}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
