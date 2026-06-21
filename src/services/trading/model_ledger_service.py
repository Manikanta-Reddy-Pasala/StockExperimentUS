"""Per-model capital ledger service.

Business logic owning:
  - settings (allocated capital, enabled flag) for each trading model
  - cash + open-position state for each model
  - trade audit log
  - portfolio aggregate stats

Used by live executors (route every buy/sell through ledger), admin/settings
UI (display + edit), and dashboard (per-model + portfolio totals).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import text

from src.models.database import get_database_manager
from src.models.model_ledger_models import (
    ModelLedger, ModelSettings, ModelTrade,
)

log = logging.getLogger(__name__)


def _normalize_symbol(sym: str) -> str:
    """Normalize bare symbol (HFCL) to Fyers form (NSE:HFCL-EQ) for
    consistent MTM lookup against historical_data table (Fyers symbols)."""
    if not sym or ":" in sym:
        return sym
    return f"NSE:{sym}-EQ"


# Models the system knows about. Adding a new model = append here.
# `enabled` controls auto-seeding default (per-row UI toggle still wins later).
# `default_capital` ₹30K = small live test slug; user can deposit more via UI.
KNOWN_MODELS = [
    # The system is reduced to EXACTLY TWO observer-mode (signal-only) models.
    # Both are cash (NO leverage, lev 1.0), PIT-aware backtest, QQQ 200d regime
    # gate, weekly rebalance. OBSERVER: signals only — NO orders, NO executor.
    {
        "name": "momentum_sp100",
        "default_capital": 30000,
        "enabled": True,
        "description": "OBSERVER (cash): n40 S&P100 top-3 of top-50 ADV by blend momentum, weekly, QQQ regime, weights .733/.133/.133. PIT ~107% CAGR / 33.5% DD. No leverage/orders.",
    },
    {
        "name": "retest_sp500",
        "default_capital": 30000,
        "enabled": True,
        "description": "OBSERVER (cash): India retest on S&P500 PIT, top-2 of top-120 ADV, BLEND momentum, retest zone, weekly, QQQ regime. PIT ~112% CAGR / 34% DD / Calmar 3.30. No leverage/orders.",
    },
]


def ensure_models_seeded() -> None:
    """Create settings+ledger rows for any KNOWN_MODELS missing from DB.

    Safe to call repeatedly. Allocated capital defaults to the value above
    but user can edit via settings UI without losing trade history.
    """
    db = get_database_manager()
    with db.get_session() as s:
        for m in KNOWN_MODELS:
            existing = s.query(ModelSettings).filter_by(model_name=m["name"]).first()
            if existing:
                continue
            s.add(ModelSettings(
                model_name=m["name"],
                enabled=m.get("enabled", True),
                invested_amount=Decimal(m["default_capital"]),
                current_amount=Decimal(m["default_capital"]),
                description=m["description"],
            ))
            # Flush so settings row exists before ledger FK
            s.flush()
            s.add(ModelLedger(
                model_name=m["name"],
                cash=Decimal(m["default_capital"]),
                realized_pnl=Decimal(0),
                total_trades=0,
                wins=0,
                losses=0,
            ))
            s.flush()
            log.info(f"Seeded ledger for {m['name']} cap={m['default_capital']} "
                     f"enabled={m.get('enabled', True)}")


# ---- Settings ----

def get_all_settings() -> List[Dict]:
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.query(ModelSettings).order_by(ModelSettings.model_name).all()
        return [_settings_dict(r) for r in rows]


def deposit(model_name: str, amount: float) -> Dict:
    """Add fresh capital to a model.

    Effects:
      invested_amount += amount   (principal in)
      current_amount  += amount   (NAV, before any market move)
      cash            += amount   (immediately deployable)

    Use case: monthly top-up from user's bank. Other models untouched.
    """
    if amount <= 0:
        raise ValueError("deposit amount must be > 0")
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        ledger = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not settings or not ledger:
            raise ValueError(f"Unknown model: {model_name}")
        delta = Decimal(str(amount))
        settings.invested_amount = (settings.invested_amount or Decimal(0)) + delta
        settings.current_amount = (settings.current_amount or Decimal(0)) + delta
        ledger.cash = (ledger.cash or Decimal(0)) + delta
        s.add(ModelTrade(
            model_name=model_name,
            side="DEPOSIT",
            symbol="-",
            qty=0,
            price=Decimal(0),
            value=delta,
            reason="DEPOSIT",
        ))
        log.info(f"{model_name}: deposit ₹{amount:,.0f} (invested now "
                 f"₹{float(settings.invested_amount):,.0f}, current "
                 f"₹{float(settings.current_amount):,.0f}, cash "
                 f"₹{float(ledger.cash):,.0f})")
        return {
            "settings": _settings_dict(settings),
            "ledger": _ledger_dict(ledger),
        }


def withdraw(model_name: str, amount: float) -> Dict:
    """Pull cash out of a model.

    Effects:
      invested_amount -= amount   (principal out; floored at 0)
      current_amount  -= amount   (NAV cache)
      cash            -= amount

    Safety: refuses if cash < amount.
    """
    if amount <= 0:
        raise ValueError("withdraw amount must be > 0")
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        ledger = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not settings or not ledger:
            raise ValueError(f"Unknown model: {model_name}")
        delta = Decimal(str(amount))
        if ledger.cash < delta:
            raise ValueError(
                f"Insufficient cash in {model_name}: have ₹{float(ledger.cash):,.0f}, "
                f"want to withdraw ₹{amount:,.0f}"
            )
        ledger.cash = ledger.cash - delta
        settings.invested_amount = max(
            Decimal(0), (settings.invested_amount or Decimal(0)) - delta
        )
        settings.current_amount = max(
            Decimal(0), (settings.current_amount or Decimal(0)) - delta
        )
        s.add(ModelTrade(
            model_name=model_name,
            side="WITHDRAW",
            symbol="-",
            qty=0,
            price=Decimal(0),
            value=delta,
            reason="WITHDRAW",
        ))
        log.info(f"{model_name}: withdraw ₹{amount:,.0f} (invested now "
                 f"₹{float(settings.invested_amount):,.0f}, current "
                 f"₹{float(settings.current_amount):,.0f}, cash "
                 f"₹{float(ledger.cash):,.0f})")
        return {
            "settings": _settings_dict(settings),
            "ledger": _ledger_dict(ledger),
        }


def auto_bootstrap_from_json_ledger(json_path: str, model_name: str,
                                    cash_buffer: float = 0.0) -> Dict:
    """Migrate legacy JSON ledger (e.g. momrot_ledger.json) into model_ledger.

    For each open position in the JSON:
      - Sets model's allocated_capital = sum(qty * entry_price) + cash_buffer
      - Adds cash_buffer to ledger.cash (= leftover from last buy)
      - Seeds model_ledger.open_symbol/qty/entry_px/date

    If the model already has allocated_capital > 0 or open_symbol, refuses
    unless reset_model was called first.

    Returns the seeded ledger snapshot.
    """
    import json
    from datetime import date as _date

    try:
        with open(json_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Legacy ledger file not found: {json_path}")

    open_positions = data.get("open", [])
    if not open_positions:
        raise ValueError(f"No open positions in {json_path}")

    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        ledger = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not settings or not ledger:
            raise ValueError(f"Unknown model: {model_name}")
        if ledger.open_symbol:
            raise ValueError(
                f"{model_name} already has open position {ledger.open_symbol}, "
                f"reset first"
            )

        # Take the first open position (mc=1 model)
        p = open_positions[0]
        symbol = p["symbol"]
        qty = int(p["qty"])
        entry_px = float(p["entry_price"])
        cost = Decimal(str(qty)) * Decimal(str(entry_px))
        total_allocated = cost + Decimal(str(cash_buffer))

        # Increase invested_amount + current_amount + ledger cash by buffer
        # (cash leftover), then deduct position cost (now in market value).
        settings.invested_amount = (settings.invested_amount or Decimal(0)) + total_allocated
        settings.current_amount = (settings.current_amount or Decimal(0)) + total_allocated
        ledger.cash = (ledger.cash or Decimal(0)) + total_allocated

        # Seed position (eats cost from cash, leaves cash_buffer)
        # Normalize symbol to Fyers format (NSE:XXX-EQ) so MTM lookup
        # against historical_data table works — that table stores Fyers form.
        ledger.open_symbol = _normalize_symbol(symbol)
        ledger.open_qty = qty
        ledger.open_entry_px = Decimal(str(entry_px))
        # entry_date from JSON if present, else today
        entry_ts = p.get("entry_ts") or data.get("updated_at")
        if entry_ts:
            try:
                ledger.open_entry_date = datetime.fromisoformat(entry_ts.split("T")[0]).date()
            except Exception:
                ledger.open_entry_date = _date.today()
        else:
            ledger.open_entry_date = _date.today()
        ledger.cash = ledger.cash - cost

        # Audit trail
        s.add(ModelTrade(
            model_name=model_name,
            side="DEPOSIT",
            symbol="-",
            qty=0,
            price=Decimal(0),
            value=total_allocated,
            reason="BOOTSTRAP_DEPOSIT",
        ))
        s.add(ModelTrade(
            model_name=model_name,
            side="BUY",
            symbol=symbol,
            qty=qty,
            price=Decimal(str(entry_px)),
            value=cost,
            reason="BOOTSTRAP_POSITION",
        ))
        log.info(
            f"Bootstrapped {model_name}: position {symbol} x{qty} @ ₹{entry_px} "
            f"(cost ₹{float(cost):,.0f}) + cash buffer ₹{cash_buffer:,.0f} "
            f"= total deposited ₹{float(total_allocated):,.0f}"
        )
        return {
            "settings": _settings_dict(settings),
            "ledger": _ledger_dict(ledger),
            "bootstrapped_position": {
                "symbol": symbol, "qty": qty, "entry_px": entry_px,
                "cost": float(cost),
            },
            "cash_buffer": cash_buffer,
        }


def reset_model(model_name: str) -> Dict:
    """Hard reset: zero invested_amount + current_amount, zero cash, zero
    realized_pnl, clear open position, reset counters. Trade audit log is NOT
    deleted (history kept). Use to start fresh before depositing real cost basis.
    """
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        ledger = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not settings or not ledger:
            raise ValueError(f"Unknown model: {model_name}")
        settings.invested_amount = Decimal(0)
        settings.current_amount = Decimal(0)
        ledger.cash = Decimal(0)
        ledger.realized_pnl = Decimal(0)
        ledger.total_trades = 0
        ledger.wins = 0
        ledger.losses = 0
        ledger.open_symbol = None
        ledger.open_qty = None
        ledger.open_entry_px = None
        ledger.open_entry_date = None
        log.info(f"{model_name}: model reset to zero")
        return {
            "settings": _settings_dict(settings),
            "ledger": _ledger_dict(ledger),
        }


def set_enabled(model_name: str, enabled: bool) -> Dict:
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        if not settings:
            raise ValueError(f"Unknown model: {model_name}")
        settings.enabled = enabled
        return _settings_dict(settings)


# ---- Ledger snapshot ----

def get_ledger(model_name: str) -> Optional[Dict]:
    db = get_database_manager()
    with db.get_session() as s:
        l = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not l:
            return None
        return _ledger_dict(l)


def get_all_ledgers() -> List[Dict]:
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.query(ModelLedger).order_by(ModelLedger.model_name).all()
        return [_ledger_dict(r) for r in rows]


# ---- Bootstrap an existing position (e.g. momentum_n100 already live) ----

def seed_position(model_name: str, symbol: str, qty: int,
                  entry_px: float, entry_date_str: str) -> Dict:
    """Manually seed a model's open position (no Fyers order placed)."""
    db = get_database_manager()
    with db.get_session() as s:
        l = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not l:
            raise ValueError(f"Unknown model: {model_name}")
        if l.open_symbol:
            raise ValueError(
                f"{model_name} already has open position {l.open_symbol}, "
                f"reset first"
            )
        cost = Decimal(str(qty)) * Decimal(str(entry_px))
        if l.cash < cost:
            raise ValueError(
                f"Not enough cash in {model_name} ledger "
                f"(₹{float(l.cash):,.0f}) to seed position cost ₹{float(cost):,.0f}"
            )
        norm = _normalize_symbol(symbol)
        l.open_symbol = norm
        l.open_qty = qty
        l.open_entry_px = Decimal(str(entry_px))
        l.open_entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
        l.cash = l.cash - cost
        s.add(ModelTrade(
            model_name=model_name,
            side="BUY",
            symbol=norm,
            qty=qty,
            price=Decimal(str(entry_px)),
            value=cost,
            reason="SEED",
        ))
        return _ledger_dict(l)


def reset_position(model_name: str) -> Dict:
    """Mark position as flat, returning estimated NAV back to cash.

    DOES NOT place any Fyers order — manual reconciliation tool only.
    """
    db = get_database_manager()
    with db.get_session() as s:
        l = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not l or not l.open_symbol:
            return _ledger_dict(l) if l else None
        cost = Decimal(str(l.open_qty)) * l.open_entry_px
        l.cash = l.cash + cost
        l.open_symbol = None
        l.open_qty = None
        l.open_entry_px = None
        l.open_entry_date = None
        return _ledger_dict(l)


# ---- Live buy/sell hooks (called by executor) ----

def _compute_real_charges(side: str, qty: int, price: float,
                          product: str = "CNC") -> Decimal:
    """Return full SEBI-rate charges total (brokerage+STT+exchange+SEBI+stamp+GST+DP).

    Falls back to a flat-rate approximation if the calculator isn't importable
    (defensive — module is in tools/, not src/).
    """
    try:
        from tools.live.broker_charges import compute_charges
        br = compute_charges(side, qty, price, product)
        return Decimal(str(br.get("total", 0)))
    except Exception:
        approx = Decimal("20")
        if side.upper() == "SELL":
            approx += Decimal(str(qty)) * Decimal(str(price)) * Decimal("0.001")
        return approx


def record_buy(model_name: str, symbol: str, qty: int, price: float,
               brokerage: float = None, fyers_order_id: str = None,
               product: str = "CNC") -> Dict:
    """Record a BUY fill.

    Cash flow: cash -= (qty*price + charges)
    NAV flow:  current_amount -= charges
               (qty*price stays as position value, so net NAV moves only by fees)

    Same-symbol behavior: ACCUMULATES into the open position (qty += new_qty,
    entry_px = weighted average). Different-symbol while holding still raises.
    Accumulation matters when an upstream race / UI bug / retry path produces
    multiple Fyers fills on the same symbol — the previous "raise on already
    holding" guard dropped 2nd+ fills, leaving Fyers and ledger out of sync
    (the May 18 ADANIPOWER incident lost track of ~134 shares this way).

    charges = full SEBI-rate broker_charges.compute_charges (brokerage + exchange
    + SEBI + stamp + GST), not the legacy ₹20 flat. brokerage kwarg is ignored —
    kept for back-compat with older call sites.
    """
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        l = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not l or not settings:
            raise ValueError(f"Unknown model: {model_name}")
        norm = _normalize_symbol(symbol)
        # Different-symbol guard remains — model logic owns single-symbol per
        # position; rotating to a different symbol must SELL first.
        if l.open_symbol and l.open_symbol != norm:
            raise ValueError(
                f"{model_name}: already holding {l.open_symbol}, cannot buy {norm}"
            )
        qty_d = Decimal(str(qty))
        price_d = Decimal(str(price))
        charges = _compute_real_charges("BUY", qty, price, product)
        cost = qty_d * price_d + charges
        if l.cash < cost:
            # Fyers fill already executed — cannot raise, ledger MUST follow
            # broker truth or drift forever. Log shortfall + allow cash dip
            # (rare edge: slippage > sizer's charges buffer).
            shortfall = float(cost - l.cash)
            log.warning(
                f"{model_name}: cash shortfall ₹{shortfall:,.2f} on BUY "
                f"{qty}x{symbol}@{price} (cost=₹{float(cost):,.2f}, "
                f"cash=₹{float(l.cash):,.2f}) — ledger absorbs"
            )
            try:
                from tools.live.telegram_notify import send as _tg
                _tg(
                    f"⚠️ *Post-fill cash shortfall absorbed*\n"
                    f"Model: `{model_name}`\n"
                    f"Symbol: `{symbol}` x{qty} @ ₹{float(price):,.2f}\n"
                    f"Cost: ₹{float(cost):,.2f}  Cash: ₹{float(l.cash):,.2f}\n"
                    f"Short: ₹{shortfall:,.2f} — ledger cash will go negative"
                )
            except Exception:
                pass
        l.cash = l.cash - cost
        if l.open_symbol == norm and l.open_qty:
            # Accumulate same-symbol fill: weighted-average entry price.
            prev_qty = Decimal(str(l.open_qty))
            prev_px = l.open_entry_px or Decimal(0)
            total_qty = prev_qty + qty_d
            new_avg = ((prev_qty * prev_px) + (qty_d * price_d)) / total_qty
            l.open_qty = int(total_qty)
            l.open_entry_px = new_avg
            # open_entry_date stays as original (earliest fill) for hold-period
            # accounting; weighted avg doesn't change first-entry date.
            log.info(
                f"{model_name}: ACCUMULATED {norm} +{qty}@{price} "
                f"(was {int(prev_qty)}@{float(prev_px):.4f}, "
                f"now {int(total_qty)}@{float(new_avg):.4f})"
            )
        else:
            l.open_symbol = norm
            l.open_qty = qty
            l.open_entry_px = price_d
            l.open_entry_date = date.today()
        settings.current_amount = (settings.current_amount or Decimal(0)) - charges
        s.add(ModelTrade(
            model_name=model_name,
            side="BUY",
            symbol=norm,
            qty=qty,
            price=price_d,
            value=cost,
            reason="ENTRY",
            fyers_order_id=fyers_order_id,
        ))
        return _ledger_dict(l)


def record_sell(model_name: str, exit_price: float, reason: str,
                brokerage: float = None, stt_pct: float = None,
                fyers_order_id: str = None, product: str = "CNC") -> Dict:
    """Record a SELL fill.

    Cash flow: cash += (qty*exit_price - charges)
    NAV flow:  current_amount = cash (position flat, no open MTM)
               — recomputed from cash because we just realized the trade.

    charges = full SEBI-rate broker_charges.compute_charges (incl. STT, DP, GST).
    brokerage + stt_pct kwargs are ignored — kept for back-compat.
    """
    db = get_database_manager()
    with db.get_session() as s:
        settings = s.query(ModelSettings).filter_by(model_name=model_name).first()
        l = s.query(ModelLedger).filter_by(model_name=model_name).first()
        if not l or not l.open_symbol or not settings:
            raise ValueError(f"{model_name}: no open position")
        qty = l.open_qty
        entry_px = l.open_entry_px
        proc = Decimal(str(qty)) * Decimal(str(exit_price))
        fees = _compute_real_charges("SELL", qty, float(exit_price), product)
        net = proc - fees
        # P&L = exit proceeds (net of sell-side charges) minus entry cost. Entry
        # cost in the ledger already reflects buy-side charges (cash was
        # decremented by qty*entry_px + buy_charges at record_buy time), so the
        # cumulative realized_pnl across a round-trip captures BOTH legs.
        pnl = net - (Decimal(str(qty)) * entry_px)
        l.cash = l.cash + net
        l.realized_pnl = (l.realized_pnl or Decimal(0)) + pnl
        l.total_trades = (l.total_trades or 0) + 1
        if pnl > 0:
            l.wins = (l.wins or 0) + 1
        else:
            l.losses = (l.losses or 0) + 1
        symbol = l.open_symbol
        l.open_symbol = None
        l.open_qty = None
        l.open_entry_px = None
        l.open_entry_date = None
        # Position flat — current_amount snaps to cash (no open MTM)
        settings.current_amount = l.cash
        s.add(ModelTrade(
            model_name=model_name,
            side="SELL",
            symbol=symbol,
            qty=qty,
            price=Decimal(str(exit_price)),
            value=net,
            pnl=pnl,
            reason=reason,
            fyers_order_id=fyers_order_id,
        ))
        return _ledger_dict(l)


# ---- Trade history ----

def get_trades(model_name: str, limit: int = 50) -> List[Dict]:
    db = get_database_manager()
    with db.get_session() as s:
        rows = (s.query(ModelTrade)
                  .filter_by(model_name=model_name)
                  .order_by(ModelTrade.trade_at.desc())
                  .limit(limit).all())
        return [_trade_dict(r) for r in rows]


# ---- Aggregate ----

def get_portfolio_stats(price_lookup=None) -> Dict:
    """Return per-model stats + portfolio total.

    price_lookup: optional callable(symbol) -> last_price for MTM of open
    positions. If None, uses last entry price as proxy.
    """
    db = get_database_manager()
    with db.get_session() as s:
        settings_rows = {x.model_name: x for x in s.query(ModelSettings).all()}
        ledger_rows = s.query(ModelLedger).all()

        models = []
        total_allocated = Decimal(0)
        total_nav = Decimal(0)
        total_realized = Decimal(0)
        total_trades = 0

        for l in ledger_rows:
            cfg = settings_rows.get(l.model_name)
            cash = l.cash or Decimal(0)
            pos_value = Decimal(0)
            mtm_price = None
            if l.open_symbol and l.open_qty:
                if price_lookup:
                    try:
                        mtm_price = price_lookup(l.open_symbol)
                    except Exception:
                        mtm_price = None
                if mtm_price is None and l.open_entry_px:
                    mtm_price = float(l.open_entry_px)
                if mtm_price is not None:
                    pos_value = Decimal(str(mtm_price)) * Decimal(str(l.open_qty))

            nav = cash + pos_value
            invested = cfg.invested_amount if cfg else Decimal(0)
            current_cache = cfg.current_amount if cfg else Decimal(0)
            pnl_total = nav - invested
            return_pct = (
                float(pnl_total / invested * 100) if invested > 0 else 0
            )

            models.append({
                "model_name": l.model_name,
                "enabled": bool(cfg and cfg.enabled),
                "invested_amount": float(invested),
                "current_amount": float(current_cache),
                # Legacy alias for any UI still reading old field name
                "allocated_capital": float(invested),
                "cash": float(cash),
                "position_value": float(pos_value),
                "nav": float(nav),
                "pnl_total": float(pnl_total),
                "return_pct": round(return_pct, 2),
                "realized_pnl": float(l.realized_pnl or 0),
                "open_symbol": l.open_symbol,
                "open_qty": l.open_qty,
                "open_entry_px": float(l.open_entry_px) if l.open_entry_px else None,
                "open_entry_date": l.open_entry_date.isoformat() if l.open_entry_date else None,
                "open_mtm_price": mtm_price,
                "total_trades": l.total_trades or 0,
                "wins": l.wins or 0,
                "losses": l.losses or 0,
                "win_rate_pct": round(
                    100.0 * (l.wins or 0) / max(1, l.total_trades or 0), 1
                ),
            })

            total_allocated += invested
            total_nav += nav
            total_realized += l.realized_pnl or Decimal(0)
            total_trades += l.total_trades or 0

        total_pnl = total_nav - total_allocated
        total_return_pct = (
            float(total_pnl / total_allocated * 100) if total_allocated > 0 else 0
        )

        return {
            "models": models,
            "total": {
                "invested_amount": float(total_allocated),
                "current_amount": float(total_nav),
                # Legacy aliases
                "allocated_capital": float(total_allocated),
                "nav": float(total_nav),
                "pnl_total": float(total_pnl),
                "return_pct": round(total_return_pct, 2),
                "realized_pnl": float(total_realized),
                "total_trades": total_trades,
            },
            "as_of": datetime.now().isoformat(),  # IST (container TZ=Asia/Kolkata)
        }


# ---- internal helpers ----

def _settings_dict(s: ModelSettings) -> Dict:
    return {
        "model_name": s.model_name,
        "enabled": s.enabled,
        "invested_amount": float(s.invested_amount or 0),
        "current_amount": float(s.current_amount or 0),
        # Legacy alias for any caller still using old field name
        "allocated_capital": float(s.invested_amount or 0),
        "description": s.description,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _ledger_dict(l: ModelLedger) -> Dict:
    return {
        "model_name": l.model_name,
        "cash": float(l.cash or 0),
        "open_symbol": l.open_symbol,
        "open_qty": l.open_qty,
        "open_entry_px": float(l.open_entry_px) if l.open_entry_px else None,
        "open_entry_date": l.open_entry_date.isoformat() if l.open_entry_date else None,
        "realized_pnl": float(l.realized_pnl or 0),
        "total_trades": l.total_trades or 0,
        "wins": l.wins or 0,
        "losses": l.losses or 0,
        "win_rate_pct": round(
            100.0 * (l.wins or 0) / max(1, l.total_trades or 0), 1
        ),
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
    }


def _trade_dict(t: ModelTrade) -> Dict:
    return {
        "id": t.id,
        "model_name": t.model_name,
        "side": t.side,
        "symbol": t.symbol,
        "qty": t.qty,
        "price": float(t.price),
        "value": float(t.value),
        "pnl": float(t.pnl) if t.pnl is not None else None,
        "reason": t.reason,
        "fyers_order_id": t.fyers_order_id,
        "trade_at": t.trade_at.isoformat() if t.trade_at else None,
    }
