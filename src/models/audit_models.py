"""Audit tables for trading-decision forensics.

All timestamps are naive (container TZ=Asia/Kolkata → IST) to match the
rest of the schema. JSONB columns hold model-specific metadata so
schema doesn't have to grow per-model.

Phases:
  1. audit_orders, audit_rebalance_decisions  (executor lifecycle)
  2. audit_model_rankings, audit_model_signals  (signal lifecycle)
  3. audit_config_changes, audit_data_quality, audit_system_events
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Date, Boolean, Text,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.models.model_ledger_models import Base


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------

class AuditOrder(Base):
    """Every Fyers placeorder request + response — order forensics + slippage."""
    __tablename__ = "audit_orders"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(64), index=True)          # NULL for non-model orders
    signal_id = Column(Integer)                          # FK → audit_model_signals (loose, no constraint)
    placed_at = Column(DateTime, default=datetime.now, index=True)
    fyers_order_id = Column(String(64), index=True)
    symbol = Column(String(64), index=True)
    side = Column(String(8))                             # BUY / SELL
    qty = Column(Integer)
    ordered_price = Column(Numeric(14, 4))
    fill_price = Column(Numeric(14, 4))
    fill_qty = Column(Integer)
    product = Column(String(16))                         # CNC / INTRADAY / MARGIN
    pricetype = Column(String(16))                       # LIMIT / MARKET
    status = Column(String(24))                          # placed / filled / partial / rejected / cancelled / no_orderid
    slippage_inr = Column(Numeric(14, 4))                # fill_qty * (fill_price - ordered_price), BUY-positive=bad
    error_text = Column(Text)
    raw_request = Column(JSONB)
    raw_response = Column(JSONB)
    # Broker charges (computed via tools/live/broker_charges.py — SEBI rates).
    # Total rupees + full breakdown JSON (brokerage/stt/exchange/sebi/stamp/gst/dp).
    charges_inr = Column(Numeric(14, 4))
    charges_breakdown = Column(JSONB)
    # Depth-gate snapshot at signal time (F&O multi-leg executor only).
    # Equity orders leave these NULL.
    bid_at_entry = Column(Numeric(14, 4))
    ask_at_entry = Column(Numeric(14, 4))
    spread_pct_at_entry = Column(Numeric(8, 4))
    volume_at_entry = Column(Integer)
    oi_at_entry = Column(Integer)
    # Basket margin (Fyers utilized-funds delta). Same value on every leg of
    # the same basket — aggregate with MAX, not SUM.
    margin_blocked_inr = Column(Numeric(14, 4))


class AuditRebalanceDecision(Base):
    """Reasoning trail for each rebalance attempt — HOLD vs ROTATE vs SKIP."""
    __tablename__ = "audit_rebalance_decisions"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(64), index=True)
    decided_at = Column(DateTime, default=datetime.now, index=True)
    trigger = Column(String(16))                         # CRON / MANUAL_UI / API
    held_symbol = Column(String(64))
    held_qty = Column(Integer)
    held_entry_px = Column(Numeric(14, 4))
    held_mtm_px = Column(Numeric(14, 4))
    rank1_symbol = Column(String(64))
    rank1_price = Column(Numeric(14, 4))
    decision = Column(String(32))                        # HOLD / ROTATE / OPEN / SKIP_NO_SIGNAL / SKIP_CAP_BREACH
    reason = Column(Text)
    qty_sized = Column(Integer)
    qty_clamped = Column(Integer)                        # qty after RiskManager clamp
    clamp_reason = Column(String(32))                    # CASH / MAX_PER_TRADE / MAX_TOTAL_BUY / NONE


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

class AuditModelRanking(Base):
    """Daily top-N snapshot per model — what was ranked, why."""
    __tablename__ = "audit_model_rankings"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(64), index=True)
    ranked_at = Column(DateTime, default=datetime.now)   # when live_signal ran
    trading_date = Column(Date, index=True)              # session this ranks for
    universe_size = Column(Integer)
    qualifying_count = Column(Integer)                   # e.g. midcap breakouts that fired
    rank = Column(Integer)                               # 1..N
    symbol = Column(String(64))
    name = Column(String(128))
    score = Column(Numeric(14, 4))                       # model-specific
    price = Column(Numeric(14, 4))
    extra = Column(JSONB)                                # vol_ratio, near_miss, etc.


Index("ix_audit_rankings_model_date", AuditModelRanking.model_name, AuditModelRanking.trading_date)


class AuditModelSignal(Base):
    """Every signal emitted — BUY/SELL/HOLD outcomes."""
    __tablename__ = "audit_model_signals"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(64), index=True)
    emitted_at = Column(DateTime, default=datetime.now, index=True)
    trading_date = Column(Date, index=True)
    signal_type = Column(String(32))                     # ENTRY1 / STOP_HIT / TARGET_HIT / EXIT / HOLD / NO_SIGNAL
    symbol = Column(String(64))
    side = Column(String(8))                             # BUY / SELL / NONE
    price = Column(Numeric(14, 4))                       # planned at signal time
    qty_planned = Column(Integer)
    reason = Column(String(128))
    extra = Column(JSONB)


# ---------------------------------------------------------------------------
# Phase 3
# ---------------------------------------------------------------------------

class AuditConfigChange(Base):
    """Settings + ledger field deltas — capital changes, enables/disables, seeds."""
    __tablename__ = "audit_config_changes"

    id = Column(Integer, primary_key=True)
    changed_at = Column(DateTime, default=datetime.now, index=True)
    changed_by = Column(String(64))                      # user_id / 'system' / 'cron'
    model_name = Column(String(64), index=True)
    field = Column(String(64))
    old_value = Column(JSONB)
    new_value = Column(JSONB)
    reason = Column(String(64))                          # DEPOSIT / WITHDRAW / SEED / RESET / LINK_FYERS_POSITION / TOGGLE / RECORD_BUY / RECORD_SELL


class AuditDataQuality(Base):
    """Daily snapshot of /admin/system/models-status — track coverage over time."""
    __tablename__ = "audit_data_quality"

    id = Column(Integer, primary_key=True)
    snapshot_at = Column(DateTime, default=datetime.now, index=True)
    model_name = Column(String(64), index=True)
    universe_size = Column(Integer)
    universe_age_days = Column(Integer)
    coverage_pct = Column(Numeric(5, 2))
    stale_days = Column(Integer)
    data_sufficient = Column(Boolean)
    wired = Column(Boolean)
    raw_items = Column(JSONB)                            # full checks list


class AuditSystemEvent(Base):
    """Boot, scheduler, token refresh, deploy markers."""
    __tablename__ = "audit_system_events"

    id = Column(Integer, primary_key=True)
    event_at = Column(DateTime, default=datetime.now, index=True)
    event_type = Column(String(32), index=True)          # BOOT / TOKEN_REFRESH / CRON_FIRED / DEPLOY / FYERS_AUTH_FAIL
    component = Column(String(64))                       # data_scheduler / trading_system / executor
    metadata_json = Column("metadata", JSONB)            # 'metadata' is reserved on SA Base; column kept as 'metadata' in DB
