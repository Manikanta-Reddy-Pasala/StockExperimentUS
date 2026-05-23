"""Per-leg liquidity gate + LIMIT-walk helpers for F&O multi-leg executor.

Two responsibilities:
  1. Pre-trade depth check: pull L1 bid/ask/vol/OI for each leg, reject the
     entire basket if any leg is too thin (wide spread, low volume, low OI).
  2. LIMIT-walk: place limit at mid-price, step toward ask (BUY) or bid (SELL)
     every few seconds until filled or budget exhausted. Far safer than MARKET
     on illiquid wings where spreads can be 30-80% of premium.

Designed for FinNifty / Nifty Iron Condor wings. Shorts (high-volume strikes)
keep using MARKET in the parent executor; wings route through limit_walk here.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_MAX_SPREAD_PCT = 0.15   # 15% of mid
DEFAULT_MIN_VOLUME = 500        # day volume on that contract
DEFAULT_MIN_OI = 5_000          # open interest on that contract
TICK = 0.05                     # NSE option tick size


def _extract_l1(quote_resp: dict, symbol: str) -> Optional[Dict[str, float]]:
    """Pull bid/ask/ltp/vol from a Fyers quote response.

    Fyers v3 quotes return shape (varies by SDK wrapper):
        { "s": "ok", "d": [{"n": "<sym>", "v": {"bid": ..., "ask": ..., "lp": ...,
                                                  "volume": ..., "oi": ...}}] }
    """
    if not isinstance(quote_resp, dict):
        return None
    data = quote_resp.get("d") or quote_resp.get("data")
    if not data:
        return None
    if isinstance(data, list):
        item = next((x for x in data if x.get("n") == symbol or x.get("symbol") == symbol),
                    data[0] if data else None)
    else:
        item = data
    if not item:
        return None
    v = item.get("v") if isinstance(item.get("v"), dict) else item
    try:
        bid = float(v.get("bid") or v.get("bp") or 0)
        ask = float(v.get("ask") or v.get("ap") or 0)
        ltp = float(v.get("lp") or v.get("ltp") or v.get("c") or 0)
        vol = float(v.get("volume") or v.get("vol") or 0)
        oi = float(v.get("oi") or v.get("openInterest") or 0)
    except (TypeError, ValueError):
        return None
    return {"bid": bid, "ask": ask, "ltp": ltp, "volume": vol, "oi": oi}


def fetch_l1(svc, user_id: int, symbol: str) -> Optional[Dict[str, float]]:
    """Best-effort L1 quote pull. Returns None on any failure."""
    try:
        resp = svc.quotes(user_id=user_id, symbol=symbol)
    except Exception as e:
        log.warning(f"quotes({symbol}) failed: {e}")
        return None
    q = _extract_l1(resp, symbol)
    if not q:
        log.warning(f"could not parse L1 for {symbol}: {resp}")
    return q


def evaluate_leg(q: Dict[str, float]) -> Dict[str, float]:
    """Compute mid, spread, spread_pct from L1 quote."""
    bid, ask = q["bid"], q["ask"]
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else q.get("ltp", 0)
    spread = max(0.0, ask - bid)
    spread_pct = (spread / mid) if mid > 0 else 1.0
    return {"mid": mid, "spread": spread, "spread_pct": spread_pct}


def gate_basket(
    svc, user_id: int, signals: List[Dict],
    max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
    min_volume: float = DEFAULT_MIN_VOLUME,
    min_oi: float = DEFAULT_MIN_OI,
) -> Tuple[bool, List[Dict]]:
    """Check every leg. Return (ok, per-leg report).

    ok=False if ANY leg fails — caller should abort the whole basket
    (Iron Condor with a thin wing has uncapped risk in practice).
    """
    report: List[Dict] = []
    all_ok = True
    for sig in signals:
        sym = sig["symbol"]
        q = fetch_l1(svc, user_id, sym)
        if not q:
            report.append({"symbol": sym, "ok": False, "reason": "no_quote"})
            all_ok = False
            continue
        m = evaluate_leg(q)
        reasons: List[str] = []
        if m["spread_pct"] > max_spread_pct:
            reasons.append(f"spread {m['spread_pct']*100:.1f}%>{max_spread_pct*100:.0f}%")
        if q["volume"] < min_volume:
            reasons.append(f"vol {int(q['volume'])}<{int(min_volume)}")
        if q["oi"] < min_oi:
            reasons.append(f"oi {int(q['oi'])}<{int(min_oi)}")
        leg_ok = not reasons
        if not leg_ok:
            all_ok = False
        report.append({
            "symbol": sym, "side": sig.get("side"), "leg": sig.get("leg"),
            "bid": q["bid"], "ask": q["ask"], "ltp": q["ltp"],
            "mid": round(m["mid"], 2), "spread": round(m["spread"], 2),
            "spread_pct": round(m["spread_pct"] * 100, 1),
            "volume": int(q["volume"]), "oi": int(q["oi"]),
            "ok": leg_ok, "reason": ",".join(reasons) if reasons else "ok",
        })
    return all_ok, report


def _round_tick(p: float, tick: float = TICK) -> float:
    return round(round(p / tick) * tick, 2)


def _volume_tier(vol: float) -> str:
    """Bucket day-volume into a liquidity tier. Drives limit-walk pacing.

    Tiers calibrated against typical FinNifty option-chain day-volume:
      - thick: >5000 contracts traded — tight spread, MARKET-safe
      - normal: 1000-5000 — start at mid, walk in ticks
      - thin: 500-1000 — start one tick conservative, walk slow
      - none: <500 — depth-gate already rejects in basket mode
    """
    if vol >= 5000:
        return "thick"
    if vol >= 1000:
        return "normal"
    if vol >= 500:
        return "thin"
    return "none"


def limit_walk(
    svc, user_id: int, symbol: str, side: str, qty: int,
    product: str, tag: str,
    max_steps: int = 6, step_sleep: float = 3.0,
    aggressive_after: int = 3,
) -> Dict:
    """Place LIMIT at mid, walk toward fill side every step_sleep seconds.

    For BUY: start mid, step +TICK toward ask each iteration.
    For SELL: start mid, step -TICK toward bid each iteration.
    After `aggressive_after` steps, jump straight to ask (BUY) / bid (SELL).
    If still unfilled after max_steps, cancel pending and fall back to MARKET.

    The starting bid AND pacing both scale with observed leg volume — thin
    legs get a more conservative start (one tick away from mid in our favor)
    and slower walk, since aggressive market orders on illiquid wings can
    cost 30-80 % of premium in slippage. Caller-supplied overrides win:
    explicit max_steps / step_sleep / aggressive_after still apply.

    Returns dict matching _place_leg's contract.
    """
    side = side.upper()
    q = fetch_l1(svc, user_id, symbol)
    if not q or q["bid"] <= 0 or q["ask"] <= 0:
        log.warning(f"{symbol}: no L1 — falling back to MARKET immediately")
        return _place_market(svc, user_id, symbol, side, qty, product, tag)

    bid, ask = q["bid"], q["ask"]
    vol = q.get("volume", 0)
    tier = _volume_tier(vol)
    mid = _round_tick((bid + ask) / 2.0)

    # Volume-aware tuning: thinner book → start further from market in our
    # favour and walk slower. Defaults preserved for "normal" tier and when
    # caller passed non-default values.
    start_offset_ticks = 0
    if tier == "thin":
        start_offset_ticks = 1     # one tick more conservative
        if step_sleep == 3.0:
            step_sleep = 5.0
        if aggressive_after == 3:
            aggressive_after = 4
    elif tier == "thick":
        start_offset_ticks = 0
        if step_sleep == 3.0:
            step_sleep = 2.0       # liquid book, walk faster
        if aggressive_after == 3:
            aggressive_after = 2

    if start_offset_ticks > 0:
        adj = -TICK * start_offset_ticks if side == "BUY" else TICK * start_offset_ticks
        target = _round_tick(mid + adj)
    else:
        target = mid
    log.info(f"limit-walk {side} {symbol} bid={bid} ask={ask} mid={mid} "
             f"vol={int(vol)} tier={tier} start={target} qty={qty} "
             f"max_steps={max_steps} step_sleep={step_sleep}s "
             f"aggressive_after={aggressive_after}")

    order_id = ""
    last_resp: Dict = {}
    for step in range(max_steps):
        if step >= aggressive_after:
            target = ask if side == "BUY" else bid
        try:
            resp = svc.placeorder(
                user_id=user_id, symbol=symbol, quantity=str(qty),
                action=side, product=product, pricetype="LIMIT",
                price=str(target), validity="DAY", tag=tag,
            )
            last_resp = resp if isinstance(resp, dict) else {}
            order_id = ((last_resp.get("data") or {}).get("orderid")
                        or last_resp.get("orderid") or order_id)
        except Exception as e:
            log.warning(f"limit step {step} {symbol}@{target} failed: {e}")

        time.sleep(step_sleep)

        if _is_filled(svc, user_id, order_id):
            log.info(f"  filled {symbol} @ {target} (step {step})")
            return {"status": "ok", "order_id": order_id, "raw": last_resp,
                    "symbol": symbol, "side": side, "qty": qty,
                    "fill_price": target, "pricetype": "LIMIT"}

        try:
            svc.cancelorder(user_id=user_id, order_id=order_id)
        except Exception:
            pass

        step_dir = TICK if side == "BUY" else -TICK
        target = _round_tick(target + step_dir)
        if (side == "BUY" and target > ask) or (side == "SELL" and target < bid):
            target = ask if side == "BUY" else bid

    log.warning(f"limit-walk {symbol} exhausted {max_steps} steps — MARKET fallback")
    return _place_market(svc, user_id, symbol, side, qty, product, tag)


def _is_filled(svc, user_id: int, order_id: str) -> bool:
    if not order_id:
        return False
    try:
        ob = svc.orderbook(user_id=user_id)
    except Exception:
        return False
    rows = (ob.get("data") or {}).get("orderBook") or ob.get("orderBook") or []
    if isinstance(rows, dict):
        rows = rows.get("orders", []) or []
    for o in rows:
        oid = str(o.get("id") or o.get("orderid") or o.get("order_id") or "")
        if oid != str(order_id):
            continue
        status = str(o.get("status", "")).upper()
        if status in ("COMPLETE", "FILLED", "2"):
            return True
        try:
            if int(o.get("filledQty", 0) or 0) >= int(o.get("qty", 0) or 1):
                return True
        except (TypeError, ValueError):
            pass
    return False


def _place_market(svc, user_id: int, symbol: str, side: str, qty: int,
                  product: str, tag: str) -> Dict:
    try:
        resp = svc.placeorder(
            user_id=user_id, symbol=symbol, quantity=str(qty),
            action=side, product=product, pricetype="MARKET",
            price="0", validity="DAY", tag=tag,
        )
    except Exception as e:
        return {"status": "error", "error": str(e),
                "symbol": symbol, "side": side, "qty": qty}
    order_id = ""
    status = "ok"
    if isinstance(resp, dict):
        order_id = (resp.get("data") or {}).get("orderid") or resp.get("orderid") or ""
        if str(resp.get("s", "")).lower() not in ("ok", "success"):
            status = str(resp.get("message", resp.get("s", "unknown")))
    return {"status": status, "order_id": order_id, "raw": resp,
            "symbol": symbol, "side": side, "qty": qty,
            "pricetype": "MARKET"}


def slice_qty(total_qty: int, lot_size: int) -> List[int]:
    """Break total qty into per-lot slices for staggered order placement."""
    if lot_size <= 0 or total_qty <= lot_size:
        return [total_qty]
    n_lots = total_qty // lot_size
    return [lot_size] * n_lots
