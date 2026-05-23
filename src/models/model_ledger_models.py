"""Per-model capital + ledger tracking.

Each enabled trading model gets:
  - ModelSettings row: user-entered allocated capital, enable flag
  - ModelLedger row: cash balance, current open position, realized PnL
  - ModelTrade rows: per-fill audit log

Designed for N models. Add a model = insert a row, no schema changes.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, Date, ForeignKey,
)
from sqlalchemy.orm import relationship

from .stock_models import Base


class ModelSettings(Base):
    """User-controlled per-model settings.

    Capital model (post 2026-05-17 split):
      invested_amount — cumulative principal in (deposits − withdrawals).
                        Used as denominator in return-% calc.
      current_amount  — latest NAV snapshot (cash + open MTM).
                        Updated by record_buy / record_sell / MTM refresh.
    """
    __tablename__ = "model_settings"

    model_name = Column(String(64), primary_key=True)
    enabled = Column(Boolean, default=True, nullable=False)
    invested_amount = Column(Numeric(14, 2), nullable=False)  # principal in
    current_amount = Column(Numeric(14, 2), nullable=False, default=0)  # NAV
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelLedger(Base):
    """Per-model cash + open position + cumulative stats."""
    __tablename__ = "model_ledger"

    model_name = Column(String(64), ForeignKey("model_settings.model_name"),
                       primary_key=True)
    cash = Column(Numeric(14, 2), nullable=False, default=0)
    open_symbol = Column(String(64))           # null when flat
    open_qty = Column(Integer)
    open_entry_px = Column(Numeric(14, 4))
    open_entry_date = Column(Date)
    realized_pnl = Column(Numeric(14, 2), default=0)
    total_trades = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelTrade(Base):
    """Audit log of every BUY/SELL routed through a model ledger."""
    __tablename__ = "model_trades"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(64), ForeignKey("model_settings.model_name"),
                       nullable=False, index=True)
    side = Column(String(16), nullable=False)  # BUY | SELL | DEPOSIT | WITHDRAW
    symbol = Column(String(64), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Numeric(14, 4), nullable=False)
    value = Column(Numeric(14, 2), nullable=False)
    pnl = Column(Numeric(14, 2))               # only on SELL
    reason = Column(String(32))                # ENTRY | TARGET | TRAIL | SMA | MAX_HOLD
    fyers_order_id = Column(String(64))
    # Naive timestamp in container's local time (TZ=Asia/Kolkata → IST).
    # UI fmtIST helper treats naive ISO as already-IST and doesn't re-shift.
    trade_at = Column(DateTime, default=datetime.now, index=True)


# ---------------------------------------------------------------------------
# SQLAlchemy event listeners — buffer 'set' events into the parent session,
# flush into audit_config_changes only AFTER the session commits.
#
# Earlier version called write_config_change() directly inside the 'set'
# event; that opened a *new* session while the parent session was mid-flush,
# which detached the ModelSettings row and broke toggle-enabled with
# 'Instance not bound to a Session'. We now stash deltas on session.info
# and write them in an after_commit hook, where the parent session is safely
# closed.
# ---------------------------------------------------------------------------
try:
    from sqlalchemy import event as _sa_event
    from sqlalchemy.orm import Session as _SASession

    _SETTINGS_FIELDS = ("enabled", "invested_amount", "current_amount", "description")
    _LEDGER_FIELDS = (
        "cash", "open_symbol", "open_qty", "open_entry_px",
        "open_entry_date", "realized_pnl",
    )

    def _buffer_change(target, field, old_v, new_v, reason):
        try:
            sess = _SASession.object_session(target)
            if sess is None:
                return
            sess.info.setdefault("_audit_buffer", []).append({
                "model_name": getattr(target, "model_name", None),
                "field": field, "old": old_v, "new": new_v, "reason": reason,
            })
        except Exception:
            pass

    def _settings_attr_changed(target, value, oldvalue, initiator):
        if oldvalue == value or oldvalue is None:
            return
        if initiator.key not in _SETTINGS_FIELDS:
            return
        _buffer_change(target, initiator.key, oldvalue, value, "SETTINGS_UPDATE")

    def _ledger_attr_changed(target, value, oldvalue, initiator):
        if oldvalue == value or oldvalue is None:
            return
        if initiator.key not in _LEDGER_FIELDS:
            return
        _buffer_change(target, initiator.key, oldvalue, value, "LEDGER_UPDATE")

    @_sa_event.listens_for(_SASession, "after_commit")
    def _flush_audit_buffer(session):
        buf = session.info.pop("_audit_buffer", None)
        if not buf:
            return
        # Open a fresh session for the audit writes — never reuse the
        # parent (it just committed, attribute reads on its objects are
        # detached). audit_service.write_config_change opens its own.
        for ch in buf:
            try:
                from src.services.audit_service import write_config_change
                write_config_change(ch["model_name"], ch["field"],
                                    ch["old"], ch["new"], ch["reason"])
            except Exception:
                pass

    for _f in _SETTINGS_FIELDS:
        _sa_event.listen(getattr(ModelSettings, _f), "set",
                         _settings_attr_changed, retval=False)
    for _f in _LEDGER_FIELDS:
        _sa_event.listen(getattr(ModelLedger, _f), "set",
                         _ledger_attr_changed, retval=False)
except Exception:
    pass
