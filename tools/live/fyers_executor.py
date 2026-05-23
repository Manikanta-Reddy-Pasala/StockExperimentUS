"""Live Fyers executor — places real orders. Off by default.

Reads signals JSON. Applies risk_manager. Places Fyers LIMIT orders with
tolerance and a MARKET fallback. Writes order log + reconciles status.

Pass-ordering (Phase 2 Task 5):
  Pass 1  — All EXIT signals (STOP_HIT/TARGET_HIT/EXIT) first.
            Each sell is polled to FILLED before any buy proceeds.
            Any unfilled sell ABORTS the run (no phantom buys on phantom cash).
  Pass 2  — Reload `current_amount` from DB (post-sells), rebuild RiskManager,
            then process ENTRY1/ENTRY2 signals with refreshed sizing.

Order-placement (Phase 2 Task 6):
  place_limit_with_fallback() — LIMIT @ last_price ± tol_pct%, re-quote at
  half-window with retry_pct, MARKET as last resort. All knobs are on the
  RiskManager.cfg (LIMIT_TOL_PCT / LIMIT_RETRY_PCT / LIMIT_FALLBACK_S env).

Hard safeguards:
  - Requires user-id config + valid Fyers access_token in DB
  - Per-trade cap enforced via RiskManager
  - Daily-loss kill-switch via RiskManager
  - Backward-compat: if --model-name missing, falls back to env-based capital
  - --dry-run flag for manual paper runs

Usage:
  python tools/live/fyers_executor.py \
    --signals signals/2026-05-17_n20.json --user-id 1 \
    --model-name n20_daily_large_only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.live.risk_manager import RiskManager, Position  # noqa: E402

log = logging.getLogger("fyers_executor")


# --------- symbol helpers ---------

def to_fyers_symbol(plain: str) -> str:
    s = plain.upper()
    if s.startswith("NSE:"):
        return s
    return f"NSE:{s.replace('.NS', '')}-EQ"


# --------- low-level Fyers wrappers ---------

def _sanitize_tag(tag: str) -> str:
    """Fyers rejects orderTag with non-alphanumerics (error_code -50).
    Strip anything outside [A-Za-z0-9], cap to 20 chars to be safe."""
    import re
    cleaned = re.sub(r"[^A-Za-z0-9]", "", tag or "")
    return cleaned[:20] or "auto"


# Module-level context: set in main() so every nested _placeorder() can
# tag its audit row with the right model name without changing every
# place_limit_with_fallback signature.
_CURRENT_MODEL: Optional[str] = None


def _placeorder(svc, user_id: int, symbol: str, qty: int, side: str,
                pricetype: str = "MARKET", price: float = 0.0,
                product: str = "CNC", tag: str = "",
                _audit_model: Optional[str] = None) -> Dict:
    """Thin wrapper around FyersService.placeorder using the standardized API.

    Returns the response dict (with `status`, `data.orderid` on success).
    Never raises — exceptions are converted to {"status":"error", ...}.

    Default product = CNC (delivery, multi-day hold) since all four equity
    models (n100, pseudo-n100, midcap, n20) backtest as delivery — exits
    only when the signal rotates, not at end-of-day. INTRADAY (MIS) is
    available if a future strategy needs forced same-day square-off.

    _audit_model — if set, every placeorder call writes an audit_orders
    row capturing request/response. Optional so older callers still work.
    """
    fyers_sym = to_fyers_symbol(symbol)
    safe_tag = _sanitize_tag(tag)
    req = {
        "symbol": fyers_sym, "qty": int(qty), "side": side.upper(),
        "product": product, "pricetype": pricetype.upper(),
        "price": float(price), "tag": safe_tag,
    }
    try:
        res = svc.placeorder(
            user_id=user_id,
            symbol=fyers_sym,
            quantity=str(int(qty)),
            action=side.upper(),
            product=product,
            pricetype=pricetype.upper(),
            price=str(price) if pricetype.upper() != "MARKET" else "0",
            trigger_price="0",
            disclosed_quantity="0",
            validity="DAY",
            tag=safe_tag,
        )
    except Exception as e:
        res = {"status": "error", "message": str(e)}
    # Audit hook
    try:
        from src.services.audit_service import write_order
        status_ok = str((res or {}).get("status") or (res or {}).get("s") or "").lower() in ("ok", "success")
        oid = (res or {}).get("id") or ((res or {}).get("data") or {}).get("orderid") or ""
        write_order(
            model_name=_audit_model or _CURRENT_MODEL,
            symbol=fyers_sym, side=side.upper(), qty=int(qty),
            ordered_price=float(price), fill_price=None, fill_qty=None,
            product=product, pricetype=pricetype.upper(),
            status=("placed" if status_ok else "rejected"),
            fyers_order_id=oid,
            error_text=None if status_ok else (res or {}).get("message"),
            raw_request=req, raw_response=res,
        )
    except Exception:
        pass
    return res


def _extract_order_id(res: Dict) -> str:
    """Fyers responses vary between raw API ({s:ok,id:...}) and standardized
    wrapper ({status:success,data:{orderid:...}})."""
    if not isinstance(res, dict):
        return ""
    return (
        res.get("id")
        or res.get("orderId")
        or (res.get("data") or {}).get("orderid")
        or (res.get("data") or {}).get("id")
        or ""
    )


def _is_ok(res: Dict) -> bool:
    status = (res or {}).get("status") or (res or {}).get("s") or ""
    return str(status).lower() in ("ok", "success")


def _get_order_status(svc, user_id: int, order_id: str) -> Optional[Dict]:
    """Fetch order status by polling the order book and matching `id`.

    Returns the matched order dict (with `status` int) or None.

    Fyers status codes (per docs):
      1=cancelled, 2=traded/filled, 3=unused, 4=transit, 5=rejected,
      6=pending, 7=expired
    """
    try:
        ob = svc.orderbook(user_id=user_id)
        rows = (ob or {}).get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("orderBook") or rows.get("orders") or []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("orderid") or row.get("id") or row.get("orderId") or "")
            if rid and rid == str(order_id):
                return row
    except Exception as e:
        log.debug(f"orderbook fetch failed: {e}")
    return None


def _extract_traded_price(row: Dict) -> Optional[float]:
    """Pull average traded price from a Fyers orderbook row.

    Fyers field name varies by SDK version: `tradedPrice` (raw),
    `traded_price`, `avgPrice`, `avg_price`, `executedPrice`. Returns None
    if no field is present or value <= 0.
    """
    if not isinstance(row, dict):
        return None
    for key in ("tradedPrice", "traded_price", "avgPrice", "avg_price",
                "executedPrice", "executed_price", "fillPrice", "fill_price"):
        val = row.get(key)
        if val is None or val == "":
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return None


def _resolve_recent_order_id(svc, user_id: int, symbol: str, qty: int,
                             side: str) -> str:
    """Find the most recent order in the order book matching (symbol, qty, side).

    Used when placeorder returns success but data.orderid is empty
    (some Fyers SDK versions/sandbox responses behave this way).
    """
    try:
        ob = svc.orderbook(user_id=user_id) or {}
        rows = ob.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("orderBook") or rows.get("orders") or []
        side_code = 1 if side.upper() == "BUY" else -1
        # Newest first if possible
        rows = sorted(
            rows or [],
            key=lambda r: r.get("orderDateTime") or r.get("timestamp") or r.get("createdAt") or "",
            reverse=True,
        )
        side_upper = side.upper()
        for r in rows:
            if not isinstance(r, dict):
                continue
            sym = (r.get("symbol") or "").upper()
            if symbol.upper() not in sym and sym not in symbol.upper():
                continue
            if str(r.get("quantity") or r.get("qty") or "") != str(qty):
                continue
            # Fyers wrapped rows give 'action' (BUY/SELL string); raw rows
            # give 'side' (1/-1 int). Accept either.
            r_action = (r.get("action") or "").upper()
            r_side = r.get("side")
            if r_action and r_action != side_upper:
                continue
            if (not r_action) and r_side is not None and r_side != side_code:
                continue
            return str(r.get("orderid") or r.get("id") or r.get("orderId") or "")
    except Exception as e:
        log.debug(f"_resolve_recent_order_id failed: {e}")
    return ""


def _fyers_holds_symbol(svc, user_id: int, symbol: str) -> Tuple[bool, int, float]:
    """Pre-trade check: does Fyers already have a non-zero position in this
    symbol (holdings T+1+ OR same-day CNC positions)?

    Returns (held: bool, qty: int, avg_price: float). Guards against multi-fill
    races where ledger thinks 'flat' but Fyers actually has shares from a
    prior order that didn't get recorded. May 18 ADANIPOWER incident bug.
    Best-effort: returns (False, 0, 0.0) on API failure so callers can decide.
    """
    bare = (symbol or "").upper().replace("NSE:", "").replace("-EQ", "")
    if not bare:
        return False, 0, 0.0
    try:
        h = svc.holdings(user_id) or {}
        for row in (h.get("data") or []):
            if not isinstance(row, dict):
                continue
            sym = (row.get("symbol") or "").upper().replace("NSE:", "").replace("-EQ", "")
            if sym == bare:
                qty = int(float(row.get("quantity") or 0))
                avg = float(row.get("average_price") or 0)
                if qty > 0:
                    return True, qty, avg
    except Exception as e:
        log.debug(f"holdings fetch in pre-trade check failed: {e}")
    try:
        raw = svc._get_api_instance(user_id)._make_request("GET", "positions") or {}
        for row in (raw.get("data") or []):
            if not isinstance(row, dict):
                continue
            sym = (row.get("symbol") or "").upper().replace("NSE:", "").replace("-EQ", "")
            if sym != bare:
                continue
            qty = int(float(row.get("netQty") or 0))
            avg = float(row.get("buyAvg") or row.get("netAvg") or 0)
            if qty > 0:
                return True, qty, avg
    except Exception as e:
        log.debug(f"positions fetch in pre-trade check failed: {e}")
    return False, 0, 0.0


def _wait_for_fill(svc, user_id: int, order_id: str,
                   timeout_s: int = 60, poll_s: float = 2.0
                   ) -> Tuple[bool, str, Optional[float]]:
    """Poll Fyers order book until status is terminal.

    Returns (filled: bool, terminal_status: str, traded_price: float | None).
    `terminal_status` is one of: 'filled', 'cancelled', 'rejected', 'expired',
    'timeout', 'not_found'.
    `traded_price` is the average fill price reported by Fyers on a filled
    order; None when the order didn't fill or the field is absent.
    """
    if not order_id:
        return False, "not_found", None
    deadline = time.time() + timeout_s
    last_status = "unknown"
    # Service layer may return raw Fyers int OR mapped string. Treat both.
    # Per Fyers docs: 1=Cancelled, 2=Traded/Filled, 4=Transit, 5=Rejected,
    # 6=Pending. Mapped strings (api.py): COMPLETE/CANCELLED/REJECTED/PENDING.
    # Defensive: also catch filledQty == qty (Fyers v3 sometimes lags status).
    FILLED_STR = {"COMPLETE", "FILLED", "TRADED"}
    CANCELLED_STR = {"CANCELLED", "CANCELED"}
    REJECTED_STR = {"REJECTED"}
    EXPIRED_STR = {"EXPIRED"}
    while time.time() < deadline:
        row = _get_order_status(svc, user_id, order_id)
        if row:
            st = row.get("status")
            st_norm = (st.upper() if isinstance(st, str) else st)
            # filledQty == qty fallback (status lag protection)
            try:
                fq = int(row.get("filled_quantity") or row.get("filledQty") or 0)
                qq = int(row.get("quantity") or row.get("qty") or 0)
                if qq > 0 and fq >= qq:
                    return True, "filled", _extract_traded_price(row)
            except (TypeError, ValueError):
                pass
            if st_norm == 2 or st_norm in FILLED_STR:
                return True, "filled", _extract_traded_price(row)
            if st_norm == 1 or st_norm in CANCELLED_STR:
                return False, "cancelled", None
            if st_norm == 5 or st_norm in REJECTED_STR:
                return False, "rejected", None
            if st_norm == 7 or st_norm in EXPIRED_STR:
                return False, "expired", None
            last_status = f"status={st}"
        time.sleep(poll_s)
    log.warning(f"_wait_for_fill timeout after {timeout_s}s on order {order_id} (last={last_status})")
    return False, "timeout", None


def _cancel_order(svc, user_id: int, order_id: str) -> bool:
    if not order_id:
        return False
    try:
        res = svc.cancelorder(user_id=user_id, orderid=order_id)
        return _is_ok(res)
    except Exception as e:
        log.warning(f"cancel order {order_id} failed: {e}")
        return False


def _snap_tick(px: float, tick: float = 0.05) -> float:
    """Snap price to NSE equity tick size (default 0.05)."""
    return round(round(px / tick) * tick, 2)


def _modify_order_limit(svc, user_id: int, order_id: str, new_price: float) -> bool:
    """Try modify; if not supported, caller should cancel+replace."""
    try:
        snapped = _snap_tick(new_price)
        res = svc.modifyorder(user_id=user_id, orderid=order_id, price=str(snapped))
        return _is_ok(res)
    except Exception as e:
        log.debug(f"modifyorder failed ({e}); caller will cancel+replace")
        return False


def _fetch_live_ltp(svc, user_id: int, symbol: str) -> Optional[float]:
    """Pull current LTP from Fyers. Returns None on failure so caller falls
    back to the stale signal-file price."""
    try:
        res = svc.quotes(user_id=user_id, symbol=symbol)
        data = res.get("data") if isinstance(res, dict) else None
        if not data:
            return None
        ltp = float(data.get("ltp") or 0)
        return ltp if ltp > 0 else None
    except Exception as e:
        log.warning(f"live LTP fetch {symbol} failed: {e}")
        return None


# --------- LIMIT-with-tolerance + MARKET-fallback ---------

def place_limit_with_fallback(svc, user_id: int, symbol: str, qty: int,
                              side: str, last_price: float, rm_cfg,
                              tag: str = "") -> Dict:
    """Place a LIMIT order with tolerance; widen once; MARKET as last resort.

    Returns dict: {filled, status, order_id, fill_price (best-effort), reason}.

    Timeline (total = `rm_cfg.limit_fallback_s` seconds, default 20s):
      t=0      : place LIMIT @ tol_pct off last_price
      t=~50%   : if unfilled, cancel + replace with retry_pct (wider)
      t=full   : if still unfilled, cancel + place MARKET, log WARN
    """
    tol = float(rm_cfg.limit_tol_pct) / 100.0
    retry = float(rm_cfg.limit_retry_pct) / 100.0
    total_s = int(rm_cfg.limit_fallback_s)
    first_window_s = max(5, total_s // 2)
    second_window_s = max(5, total_s - first_window_s)

    if side.upper() == "BUY":
        first_px = _snap_tick(last_price * (1.0 + tol))
        retry_px = _snap_tick(last_price * (1.0 + retry))
    else:
        first_px = _snap_tick(last_price * (1.0 - tol))
        retry_px = _snap_tick(last_price * (1.0 - retry))

    log.info(f"  LIMIT {side} {symbol} qty={qty} px={first_px} "
             f"(last={last_price}, tol={rm_cfg.limit_tol_pct}%)")
    res = _placeorder(svc, user_id, symbol, qty, side,
                      pricetype="LIMIT", price=first_px, tag=tag)
    if not _is_ok(res):
        return {"filled": False, "status": "place_failed", "order_id": "",
                "fill_price": None, "reason": str(res)}
    order_id = _extract_order_id(res)
    # Fyers may return success + empty orderid synchronously; that still means
    # the order was accepted. Try to recover the real id from the order book
    # before we give up and short-circuit to MARKET.
    if not order_id:
        order_id = _resolve_recent_order_id(svc, user_id, symbol, qty, side)
    if not order_id:
        log.warning(f"  LIMIT {symbol} placed but no orderId returned — "
                    f"recording as placed (will rely on Fyers fills).")
        return {"filled": True, "status": "limit_no_id",
                "order_id": "", "fill_price": first_px,
                "reason": "no_orderid"}
    filled, term, traded_px = _wait_for_fill(svc, user_id, order_id,
                                              timeout_s=first_window_s, poll_s=2.0)
    if filled:
        return {"filled": True, "status": "limit_filled", "order_id": order_id,
                "fill_price": traded_px if traded_px is not None else first_px,
                "reason": "tol"}
    if term in ("rejected", "cancelled", "expired"):
        # Order is already gone — try a fresh widened LIMIT
        log.warning(f"  LIMIT {symbol} terminal={term}, retry with widened tol")
    else:
        # Still pending — try modify first, cancel+replace as fallback
        if not _modify_order_limit(svc, user_id, order_id, retry_px):
            _cancel_order(svc, user_id, order_id)
            res2 = _placeorder(svc, user_id, symbol, qty, side,
                               pricetype="LIMIT", price=retry_px, tag=tag)
            if _is_ok(res2):
                order_id = _extract_order_id(res2)
            else:
                log.error(f"  LIMIT retry place failed for {symbol}: {res2}")
        else:
            log.info(f"  LIMIT {symbol} modified to {retry_px}")

    log.info(f"  LIMIT {side} {symbol} re-quote px={retry_px} "
             f"(retry_tol={rm_cfg.limit_retry_pct}%)")
    filled, term, traded_px = _wait_for_fill(svc, user_id, order_id,
                                              timeout_s=second_window_s, poll_s=2.0)
    if filled:
        return {"filled": True, "status": "limit_retry_filled", "order_id": order_id,
                "fill_price": traded_px if traded_px is not None else retry_px,
                "reason": "retry_tol"}

    # MARKET fallback
    _cancel_order(svc, user_id, order_id)
    log.warning(f"  MARKET fallback for {side} {symbol} qty={qty} "
                f"(last={last_price}, prior order={order_id})")
    res3 = _placeorder(svc, user_id, symbol, qty, side, pricetype="MARKET", tag=tag)
    if not _is_ok(res3):
        return {"filled": False, "status": "market_failed", "order_id": "",
                "fill_price": None, "reason": str(res3)}
    market_id = _extract_order_id(res3)
    filled, term, traded_px = _wait_for_fill(svc, user_id, market_id,
                                              timeout_s=30, poll_s=2.0)
    return {
        "filled": filled,
        "status": "market_filled" if filled else f"market_{term}",
        "order_id": market_id,
        # Use Fyers-reported tradedPrice when available (real avg fill);
        # last_price is a placeholder if Fyers omits it on this SDK version.
        "fill_price": (traded_px if traded_px is not None
                       else (last_price if filled else None)),
        "reason": "market_fallback",
    }


# --------- Ledger hooks ---------

def _tg_safe(text: str):
    """Best-effort Telegram notify — never raises."""
    try:
        from tools.live.telegram_notify import send
        send(text)
    except Exception as e:
        log.debug(f"tg notify skipped: {e}")


def _backfill_audit_fill(order_id: str, fill_price: float, fill_qty: int,
                         svc=None, user_id: int = 1):
    """Update audit_orders with real Fyers tradedPrice + approx formula charges.

    svc/user_id retained for call-site compatibility — no longer used.
    """
    _ = (svc, user_id)
    if not order_id or fill_price is None:
        return
    try:
        from src.services.audit_service import update_order_fill
        update_order_fill(order_id, fill_price=float(fill_price),
                          fill_qty=int(fill_qty), status="filled")
    except Exception as e:
        log.debug(f"audit update_order_fill failed: {e}")


def _record_model_buy(model_name, symbol, qty, price, order_id, svc=None, user_id: int = 1):
    _backfill_audit_fill(order_id, price, qty, svc=svc, user_id=user_id)
    if not model_name:
        return
    try:
        from src.services.trading.model_ledger_service import record_buy
        record_buy(model_name, symbol, qty, price, fyers_order_id=order_id)
        log.info(f"  ledger: recorded BUY for {model_name}")
        _tg_safe(
            f"✅ *BUY {model_name}*\n"
            f"`{symbol}` x{qty} @ ₹{float(price):.2f} = ₹{float(qty)*float(price):,.0f}\n"
            f"order_id=`{order_id or '—'}`"
        )
    except Exception as e:
        log.warning(f"  ledger record_buy failed for {model_name}: {e}")
        _tg_safe(f"⚠️ BUY {model_name} {symbol} x{qty} placed but ledger write FAILED: {e}")


def _record_model_sell(model_name, exit_price, reason, order_id, qty=None,
                       svc=None, user_id: int = 1):
    if qty is not None:
        _backfill_audit_fill(order_id, exit_price, qty, svc=svc, user_id=user_id)
    if not model_name:
        return
    try:
        from src.services.trading.model_ledger_service import record_sell
        record_sell(model_name, exit_price, reason, fyers_order_id=order_id)
        log.info(f"  ledger: recorded SELL for {model_name}")
        _tg_safe(
            f"💰 *SELL {model_name}*\n"
            f"@ ₹{float(exit_price):.2f}  reason=`{reason}`\n"
            f"order_id=`{order_id or '—'}`"
        )
    except Exception as e:
        log.warning(f"  ledger record_sell failed for {model_name}: {e}")
        _tg_safe(f"⚠️ SELL {model_name} order placed but ledger write FAILED: {e}")


# --------- main ---------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signals", required=True)
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--model-name", default=None,
                    help="Per-model ledger routing. If set, capital comes from "
                         "model_settings.current_amount (Phase 2 Task 4) and "
                         "every BUY/SELL is recorded in model_ledger DB.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print orders, don't place. Manual override only.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Make model name visible to nested helpers (audit_orders rows).
    global _CURRENT_MODEL
    _CURRENT_MODEL = args.model_name

    # Pre-flight data quality gate. Written by data_scheduler at 09:00 IST.
    # If today's historical_data coverage is below threshold, abort entries.
    if not args.dry_run and os.environ.get("SKIP_DQ_GATE", "false").lower() != "true":
        gate_path = "/app/logs/data_quality_gate.json"
        if os.path.exists(gate_path):
            try:
                with open(gate_path) as _gf:
                    _gate = json.load(_gf)
                if not _gate.get("ok"):
                    log.error(f"Data quality gate FAILED: {_gate.get('msg')} — "
                              f"aborting trade execution. Set SKIP_DQ_GATE=true to override.")
                    try:
                        from tools.live.telegram_notify import send as _tg
                        _tg(f"🛑 *Trade execution aborted*\nData quality gate: {_gate.get('msg')}")
                    except Exception:
                        pass
                    return 3
            except Exception as _e:
                log.warning(f"data_quality_gate read failed: {_e} — proceeding")

    # ---- Build RiskManager (per-model if provided, else env) ----
    rm = RiskManager.for_model_or_env(args.model_name)
    log.info(f"Risk: model={args.model_name or '(env)'} "
             f"capital=₹{rm.cfg.capital_inr:,} "
             f"max_concurrent={rm.cfg.max_concurrent} live={live} "
             f"dry_run={args.dry_run} "
             f"limit_tol={rm.cfg.limit_tol_pct}% "
             f"retry_tol={rm.cfg.limit_retry_pct}% "
             f"fallback_s={rm.cfg.limit_fallback_s}")

    with open(args.signals) as f:
        signals = json.load(f)

    if not args.dry_run:
        from src.services.brokers.fyers_service import FyersService
        svc = FyersService()
        cfg = svc.get_broker_config(args.user_id)
        if not cfg or not cfg.get("access_token"):
            log.error(f"No Fyers token for user_id={args.user_id} — aborting")
            return 2
    else:
        svc = None

    # Load open positions from DB model_ledger (single source of truth).
    # Per-model row keyed by model_name. record_buy / record_sell maintain
    # open_symbol / open_qty / open_entry_px. File ledger removed 2026-05-22.
    open_positions: List[Position] = []
    if args.model_name:
        try:
            from src.models.database import get_database_manager
            from src.models.model_ledger_models import ModelLedger
            db = get_database_manager()
            with db.get_session() as _s:
                _l = _s.query(ModelLedger).filter_by(
                    model_name=args.model_name).first()
                if _l and _l.open_symbol and _l.open_qty:
                    open_positions.append(Position(
                        symbol=_l.open_symbol,
                        qty=int(_l.open_qty),
                        entry_price=float(_l.open_entry_px or 0),
                        side="BUY",
                    ))
        except Exception as _le:
            log.warning(f"DB open_positions load failed: {_le}; "
                        "treating as flat")

    def _save_ledger():
        # No-op: record_buy / record_sell persist DB state. In-memory
        # open_positions kept only for intra-execution sizing.
        return

    def _append_history(rec: dict):
        # No-op: model_trades table is canonical history. Inserted by
        # record_buy / record_sell in model_ledger_service.
        return

    # Partition signals into exits and entries (preserve order within each)
    exit_signals = [s for s in signals
                    if s.get("signal") in ("STOP_HIT", "TARGET_HIT", "EXIT")]
    entry_signals = [s for s in signals
                     if s.get("signal") in ("ENTRY1", "ENTRY2")]
    other_signals = [s for s in signals
                     if s.get("signal") not in (
                         "STOP_HIT", "TARGET_HIT", "EXIT", "ENTRY1", "ENTRY2"
                     )]

    log.info(f"Signal mix: exits={len(exit_signals)} entries={len(entry_signals)} "
             f"other={len(other_signals)}")

    placed = 0
    closed = 0
    skipped = 0

    # ---- PASS 1: EXITS FIRST (block on each fill) ----
    for sig in exit_signals:
        sig_type = sig.get("signal")
        sym = sig["symbol"]
        signal_price = float(sig.get("price") or 0)
        live_px = None if args.dry_run else _fetch_live_ltp(svc, args.user_id, sym)
        price = live_px if live_px else signal_price
        if live_px:
            log.info(f"  live LTP {sym}={live_px} (signal={signal_price})")
        held = next((p for p in open_positions if p.symbol == sym), None)
        if held is None:
            log.info(f"SKIP exit {sym}: not held")
            skipped += 1
            continue
        exit_side = "SELL" if held.side == "BUY" else "BUY"
        order_id = "DRY"
        status = "dry-run"
        fill_price = price

        if args.dry_run:
            log.info(f"DRY-RUN PASS-1 EXIT {sym} qty={held.qty} "
                     f"side={exit_side} @ ~{price} (would LIMIT then MARKET)")
        else:
            res = place_limit_with_fallback(
                svc, args.user_id, sym, held.qty, exit_side,
                last_price=price, rm_cfg=rm.cfg,
                tag=f"exit:{sig_type}",
            )
            status = res.get("status", "unknown")
            order_id = res.get("order_id", "")
            if not res.get("filled"):
                reason_txt = res.get("reason") or status
                log.error(f"EXIT NOT FILLED {sym}: status={status} reason={reason_txt}"
                          f" — ABORTING ENTRIES to avoid phantom-cash buys")
                _tg_safe(
                    f"🛑 *EXIT NOT FILLED — entries ABORTED*\n"
                    f"Model: `{args.model_name or '(env)'}`\n"
                    f"Symbol: `{sym}` qty={held.qty} @ ₹{price:,.2f}\n"
                    f"Status: `{status}`\n"
                    f"Reason: {reason_txt}\n"
                    f"Held position retained; no new entries this cycle."
                )
                # Best-effort save of what we did so far, then bail.
                return 3
            fill_price = res.get("fill_price") or price

        pnl = (fill_price - held.entry_price) * held.qty * (
            1 if held.side == "BUY" else -1
        )
        model_for_signal = args.model_name or sig.get("model", "momentum_n100_top5_max1")
        _append_history({
            "ts": datetime.now().isoformat(),
            "event": "EXIT", "reason": sig_type, "pass": 1,
            "symbol": sym, "qty": held.qty,
            "entry_price": held.entry_price, "exit_price": fill_price,
            "pnl": round(pnl, 2),
            "order_id": order_id, "status": status,
            "model": model_for_signal,
        })
        if not args.dry_run:
            _record_model_sell(model_for_signal, fill_price,
                               sig.get("reason", sig_type), order_id,
                               qty=held.qty, svc=svc, user_id=args.user_id)
        open_positions = [p for p in open_positions if p.symbol != sym]
        _save_ledger()
        log.info(f"{'DRY-RUN' if args.dry_run else 'CLOSED'} PASS-1 {sym} qty={held.qty} "
                 f"entry={held.entry_price} exit={fill_price} pnl=₹{pnl:.0f} "
                 f"reason={sig_type}")
        closed += 1

    # ---- After all sells confirmed: rebuild RiskManager from refreshed DB ----
    if closed > 0 and args.model_name and not args.dry_run:
        rm = RiskManager.for_model_or_env(args.model_name)
        log.info(f"Risk RELOADED post-sells: capital=₹{rm.cfg.capital_inr:,} "
                 f"(after {closed} exit fills)")

    # ---- PASS 2: ENTRIES with refreshed sizing ----
    for sig in entry_signals:
        sym = sig["symbol"]
        signal_price = float(sig.get("price") or 0)
        live_px = None if args.dry_run else _fetch_live_ltp(svc, args.user_id, sym)
        price = live_px if live_px else signal_price
        if live_px:
            log.info(f"  live LTP {sym}={live_px} (signal={signal_price}, "
                     f"delta={((live_px/signal_price-1)*100 if signal_price else 0):+.2f}%)")
        side = sig["side"]

        # Pre-trade Fyers position check (BUY only). Guards against ledger ↔
        # Fyers desync from prior multi-fill races. If Fyers already holds
        # this symbol, abort the new BUY — model logic expects single-position
        # per cycle; another order would compound exposure (May 18 incident).
        if side == "BUY" and not args.dry_run:
            held, fyers_qty, fyers_avg = _fyers_holds_symbol(svc, args.user_id, sym)
            if held:
                log.error(
                    f"SKIP BUY {sym}: Fyers already holds {fyers_qty}@{fyers_avg:.2f} "
                    f"(ledger thinks flat or different). Possible prior fill not "
                    f"recorded — investigate before re-entering."
                )
                _tg_safe(
                    f"🛑 *Ledger/Fyers DRIFT*\n"
                    f"Model: `{args.model_name or '(env)'}`\n"
                    f"Symbol: `{sym}`\n"
                    f"Fyers holds: {fyers_qty} @ ₹{fyers_avg:.2f}\n"
                    f"Ledger thinks flat or different — BUY skipped.\n"
                    f"Manual reconciliation needed."
                )
                skipped += 1
                try:
                    from src.services.audit_service import write_rebalance_decision
                    write_rebalance_decision(
                        model_name=args.model_name or "(env)",
                        trigger="CRON",
                        decision="SKIP_FYERS_ALREADY_HOLDS",
                        reason=f"Fyers position {fyers_qty}@{fyers_avg:.2f} on {sym} "
                               f"— ledger/Fyers drift, manual recon needed",
                        rank1_symbol=sym, rank1_price=price,
                    )
                except Exception:
                    pass
                continue

        ok, reason = rm.can_enter(sym, price, side, open_positions)
        if not ok:
            log.info(f"SKIP {sym}: {reason}")
            skipped += 1
            try:
                from src.services.audit_service import write_rebalance_decision
                write_rebalance_decision(
                    model_name=args.model_name or "(env)",
                    trigger="CRON" if not args.dry_run else "DRY",
                    decision="SKIP_CANNOT_ENTER", reason=reason,
                    rank1_symbol=sym, rank1_price=price,
                )
            except Exception:
                pass
            continue
        qty = rm.size_position(price, open_positions)
        if qty < 1:
            # Compute the gap so the notification can quote actual shortfall.
            used_inr = sum(p.qty * p.entry_price for p in open_positions)
            cash_avail = rm.cfg.capital_inr - used_inr
            try:
                from tools.live.broker_charges import compute_charges
                approx_chg = float(
                    compute_charges("BUY", 1, float(price), "CNC").get("total", 0))
            except Exception:
                approx_chg = 20.0
            needed_for_one = float(price) + approx_chg
            log.info(
                f"SKIP {sym}: qty<1 (cash=₹{cash_avail:,.2f}, "
                f"needed≥₹{needed_for_one:,.2f} for 1 share + approx chg)"
            )
            skipped += 1
            try:
                from src.services.audit_service import write_rebalance_decision
                write_rebalance_decision(
                    model_name=args.model_name or "(env)",
                    trigger="CRON" if not args.dry_run else "DRY",
                    decision="SKIP_QTY_ZERO",
                    reason=(f"qty<1 at price ₹{price:.2f}, cash=₹{cash_avail:,.2f}, "
                            f"needed≥₹{needed_for_one:,.2f}"),
                    rank1_symbol=sym, rank1_price=price,
                    qty_sized=0, qty_clamped=0, clamp_reason="CASH",
                )
            except Exception:
                pass
            _tg_safe(
                f"⚠️ *Insufficient cash — order skipped*\n"
                f"Model: `{args.model_name or '(env)'}`\n"
                f"Symbol: `{sym}` @ ₹{float(price):,.2f}\n"
                f"Available cash: ₹{cash_avail:,.2f}\n"
                f"Needed (≥1 share + approx chg): ₹{needed_for_one:,.2f}\n"
                f"Short by: ₹{max(0.0, needed_for_one - cash_avail):,.2f}"
            )
            continue

        # Decision audit — BUY allowed
        try:
            from src.services.audit_service import write_rebalance_decision
            held_obj = next((p for p in open_positions), None)
            write_rebalance_decision(
                model_name=args.model_name or "(env)",
                trigger="CRON" if not args.dry_run else "DRY",
                decision="OPEN" if not held_obj else "ROTATE",
                reason=f"emit ENTRY {sig.get('signal')}",
                held_symbol=held_obj.symbol if held_obj else None,
                held_qty=held_obj.qty if held_obj else None,
                held_entry_px=held_obj.entry_price if held_obj else None,
                rank1_symbol=sym, rank1_price=price,
                qty_sized=qty, qty_clamped=qty, clamp_reason="NONE",
            )
        except Exception:
            pass

        order_id = "DRY"
        status = "dry-run"
        fill_price = price

        if args.dry_run:
            log.info(f"DRY-RUN PASS-2 ENTRY {sym} qty={qty} "
                     f"side={side} @ ~{price} (would LIMIT then MARKET)")
        else:
            res = place_limit_with_fallback(
                svc, args.user_id, sym, qty, side,
                last_price=price, rm_cfg=rm.cfg,
                tag=f"entry:{sig.get('signal')}",
            )
            status = res.get("status", "unknown")
            order_id = res.get("order_id", "")
            if not res.get("filled"):
                reason_txt = res.get("reason") or status
                log.error(f"ENTRY NOT FILLED {sym}: status={status} reason={reason_txt}"
                          f" — skipping this symbol, continuing")
                _tg_safe(
                    f"❌ *ENTRY NOT FILLED*\n"
                    f"Model: `{args.model_name or '(env)'}`\n"
                    f"Symbol: `{sym}` qty={qty} @ ₹{price:,.2f}\n"
                    f"Status: `{status}`\n"
                    f"Reason: {reason_txt}"
                )
                skipped += 1
                continue
            fill_price = res.get("fill_price") or price

        entry_ts = datetime.now().isoformat()
        model_for_signal = args.model_name or sig.get("model", "momentum_n100_top5_max1")
        _append_history({
            "ts": entry_ts, "event": "ENTRY", "signal": sig.get("signal"),
            "pass": 2,
            "symbol": sym, "side": side, "qty": qty, "price": fill_price,
            "sl": sig.get("sl"), "target": sig.get("target"),
            "order_id": order_id, "status": status,
            "model": model_for_signal,
        })
        if not args.dry_run and side == "BUY":
            _record_model_buy(model_for_signal, sym, qty, fill_price, order_id,
                              svc=svc, user_id=args.user_id)
        log.info(f"{'DRY-RUN' if args.dry_run else 'PLACED'} PASS-2 {side} {sym} "
                 f"qty={qty} @ {fill_price} status={status}")
        placed += 1
        new_pos = Position(
            symbol=sym, qty=qty, entry_price=fill_price, side=side,
            sl=float(sig.get("sl", 0) or 0),
            target=float(sig.get("target", 0) or 0),
        )
        try:
            object.__setattr__(new_pos, "entry_ts", entry_ts)
        except Exception:
            pass
        open_positions.append(new_pos)
        _save_ledger()

    log.info(f"Done: placed={placed} closed={closed} skipped={skipped} "
             f"(live={live}, dry_run={args.dry_run}, "
             f"model={args.model_name or '(env)'})")

    # HOLD audit — when cron runs but no entry/exit was taken, still log
    # the decision so audit_rebalance_decisions has one row per (model, day).
    if placed == 0 and closed == 0 and skipped == 0:
        try:
            from src.services.audit_service import write_rebalance_decision
            held_obj = open_positions[0] if open_positions else None
            write_rebalance_decision(
                model_name=args.model_name or "(env)",
                trigger="CRON" if not args.dry_run else "DRY",
                decision="HOLD",
                reason="no entry/exit signals emitted today",
                held_symbol=held_obj.symbol if held_obj else None,
                held_qty=held_obj.qty if held_obj else None,
                held_entry_px=held_obj.entry_price if held_obj else None,
            )
        except Exception as e:
            log.debug(f"HOLD audit write failed: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
