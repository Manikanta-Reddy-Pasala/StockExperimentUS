"""
Historical Data Models for Enhanced Technical Analysis
Stores OHLCV data for comprehensive technical indicator calculations
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, Date, Boolean, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

try:
    from .stock_models import Base
except ImportError:
    from src.models.stock_models import Base


class HistoricalData(Base):
    """
    Historical OHLCV data for stocks - optimized for technical analysis
    Stores ALL available data from Fyers API plus calculated fields
    """
    __tablename__ = 'historical_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    # Core OHLCV Data from Fyers API (ALL 6 fields)
    timestamp = Column(BigInteger, nullable=False)  # Original Unix timestamp
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)

    # Calculated fields for enhanced analysis
    adj_close = Column(Float)  # Adjusted close for splits/dividends
    turnover = Column(Float)  # Daily turnover in INR (price * volume)
    price_change = Column(Float)  # Close - Open
    price_change_pct = Column(Float)  # (Close - Open) / Open * 100
    high_low_pct = Column(Float)  # (High - Low) / Close * 100
    body_pct = Column(Float)  # |Close - Open| / (High - Low) * 100
    upper_shadow_pct = Column(Float)  # Upper wick percentage
    lower_shadow_pct = Column(Float)  # Lower wick percentage

    # Volume analysis
    volume_sma_ratio = Column(Float)  # Volume / SMA(Volume, 20)
    price_volume_trend = Column(Float)  # PVT indicator value

    # Data quality and metadata
    is_adjusted = Column(Boolean, default=False)
    data_source = Column(String(20), default='fyers')
    api_resolution = Column(String(10))  # Original API resolution (1D, 5M, etc.)
    data_quality_score = Column(Float)  # 0-1 score for data completeness

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite indexes for performance
    __table_args__ = (
        Index('ix_historical_symbol_date', 'symbol', 'date'),
        Index('ix_historical_date_symbol', 'date', 'symbol'),
    )

    def __repr__(self):
        return f'<HistoricalData {self.symbol} {self.date}: {self.close}>'


class TechnicalIndicators(Base):
    """Daily SMA 50/200 cache used by the EMA 200/400 1H strategy for HTF gating."""
    __tablename__ = 'technical_indicators'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    sma_50 = Column(Float)
    sma_200 = Column(Float)

    calculation_date = Column(DateTime, default=datetime.utcnow)
    data_points_used = Column(Integer)

    __table_args__ = (
        Index('ix_technical_symbol_date', 'symbol', 'date'),
    )

    def __repr__(self):
        return f'<TechnicalIndicators {self.symbol} {self.date}>'


class HistoricalData1H(Base):
    """
    1-Hour OHLCV data for EMA 200/400 crossover strategy.
    """
    __tablename__ = 'historical_data_1h'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False)  # Candle open time (Unix UTC seconds)
    candle_time = Column(DateTime, nullable=False, index=True)  # IST datetime for readability

    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)

    # Cached EMA values for the crossover strategy
    ema_200 = Column(Float)
    ema_400 = Column(Float)

    data_source = Column(String(20), default='fyers')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('symbol', 'timestamp', name='uq_hist1h_symbol_ts'),
        Index('ix_hist1h_symbol_time', 'symbol', 'candle_time'),
    )

    def __repr__(self):
        return f'<HistoricalData1H {self.symbol} {self.candle_time}: {self.close}>'


class HistoricalData15M(Base):
    """
    15-minute OHLCV data — used only for the EMA 200/400 sustain check after
    a retest level break. Trend detection still runs on the 1H series.
    """
    __tablename__ = 'historical_data_15m'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False)
    candle_time = Column(DateTime, nullable=False, index=True)

    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)

    data_source = Column(String(20), default='fyers')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('symbol', 'timestamp', name='uq_hist15m_symbol_ts'),
        Index('ix_hist15m_symbol_time', 'symbol', 'candle_time'),
    )

    def __repr__(self):
        return f'<HistoricalData15M {self.symbol} {self.candle_time}: {self.close}>'


class EMACrossoverState(Base):
    """
    Per-user / per-symbol state for the EMA 200/400 1H crossover strategy.

    Trend: 'BUY' (EMA200 above EMA400), 'SELL' (EMA200 below EMA400), 'NONE'.
    Stage: 0=waiting crossover, 1=crossover seen (waiting break of crossover candle),
           2=alert1 fired, retest of EMA200 pending, 3=retest1 captured (entry1 armed),
           4=entry1 taken, waiting EMA400 touch, 5=retest2 captured (entry2 armed).
    """
    __tablename__ = 'ema_crossover_state'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)

    trend = Column(String(8), nullable=False, default='NONE')  # BUY / SELL / NONE
    stage = Column(Integer, nullable=False, default=0)

    # Crossover candle (where EMA200 crossed EMA400)
    crossover_ts = Column(BigInteger)
    crossover_high = Column(Float)
    crossover_low = Column(Float)

    # Retest 1 candle (EMA200 retest)
    retest1_ts = Column(BigInteger)
    retest1_high = Column(Float)
    retest1_low = Column(Float)

    # Retest 2 candle (EMA400 retest)
    retest2_ts = Column(BigInteger)
    retest2_high = Column(Float)
    retest2_low = Column(Float)

    # Entries taken
    entries_count = Column(Integer, default=0)
    entry1_price = Column(Float)
    entry1_time = Column(DateTime)
    entry2_price = Column(Float)
    entry2_time = Column(DateTime)

    # Risk management — last entry's SL/target shown for UI; authoritative
    # per-position state lives in positions_json.
    stop_loss = Column(Float)
    target_price = Column(Float)
    position_active = Column(Boolean, default=False)

    # v2 BTC rules state
    retest1_attempts = Column(Integer, nullable=False, default=0)
    retest2_attempts = Column(Integer, nullable=False, default=0)
    retest1_invalidated = Column(Boolean, nullable=False, default=False)
    positions_json = Column(JSONB, nullable=False, default=list)
    # Pending cross detection — wait sustain_minutes before triggering ENTRY.
    # Stores bar timestamp where retest level was first broken.
    retest1_pending_cross_ts = Column(BigInteger)
    retest2_pending_cross_ts = Column(BigInteger)
    # Tuning: count ALERT3 locks per cycle (capped via config.max_alert3_locks_per_cycle).
    alert3_locks_count = Column(Integer, nullable=False, default=0)
    # v1.4 sustain (single-bar edge cross): track previous bar's close per
    # retest level so the next bar can detect prev<=level<curr (edge).
    retest1_last_close = Column(Float)
    retest2_last_close = Column(Float)
    # v1.4 sideways check: count bars since retest candle locked; if price
    # breaks retest.low before retest.high within `sideways_check_bars` bars,
    # the retest is sideways → skip ENTRY1, advance to next stage.
    retest1_bars_since_lock = Column(Integer, nullable=False, default=0)
    retest2_bars_since_lock = Column(Integer, nullable=False, default=0)

    last_evaluated_ts = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'symbol', name='uq_ema_state_user_symbol'),
        Index('ix_ema_state_symbol_trend', 'symbol', 'trend'),
    )

    def __repr__(self):
        return f'<EMACrossoverState user={self.user_id} {self.symbol} {self.trend}/stage={self.stage}>'


class EMACrossoverSignal(Base):
    """Audit log of every signal/alert/entry emitted by the strategy."""
    __tablename__ = 'ema_crossover_signals'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)

    signal_type = Column(String(32), nullable=False)  # CROSSOVER, ALERT1, ALERT2, ALERT3, ENTRY1, ENTRY2, EXIT
    trend = Column(String(8), nullable=False)
    candle_ts = Column(BigInteger, nullable=False)
    candle_time = Column(DateTime, nullable=False)
    price = Column(Float)
    ema_200 = Column(Float)
    ema_400 = Column(Float)
    note = Column(String(255))

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ema_sig_symbol_time', 'symbol', 'candle_time'),
    )

    def __repr__(self):
        return f'<EMACrossoverSignal {self.symbol} {self.signal_type} @ {self.candle_time}>'


class MarketBenchmarks(Base):
    """
    Market benchmark data (NIFTY, SENSEX) for beta calculations
    Essential for relative performance analysis
    """
    __tablename__ = 'market_benchmarks'

    id = Column(Integer, primary_key=True)
    benchmark = Column(String(20), nullable=False, index=True)  # NIFTY50, SENSEX
    date = Column(Date, nullable=False, index=True)

    # OHLCV for benchmarks
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger)

    # Additional metrics
    market_cap = Column(Float)  # Total market cap
    pe_ratio = Column(Float)    # Market PE

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Composite indexes
    __table_args__ = (
        Index('ix_benchmark_date', 'benchmark', 'date'),
    )

    def __repr__(self):
        return f'<MarketBenchmark {self.benchmark} {self.date}: {self.close}>'


class DataQualityMetrics(Base):
    """
    Track data quality and completeness for each symbol
    Ensures reliable technical analysis calculations
    """
    __tablename__ = 'data_quality_metrics'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), unique=True, nullable=False, index=True)

    # Data coverage
    earliest_date = Column(Date)
    latest_date = Column(Date)
    total_days = Column(Integer)
    missing_days = Column(Integer)
    data_completeness = Column(Float)  # Percentage (0-100)

    # Data quality scores
    price_consistency_score = Column(Float)  # No unrealistic gaps
    volume_consistency_score = Column(Float)  # Volume patterns
    overall_quality_score = Column(Float)    # Combined score

    # Specific requirements for filtering
    has_200_day_history = Column(Boolean, default=False)
    has_1_year_history = Column(Boolean, default=False)
    meets_min_quality = Column(Boolean, default=False)

    # Update tracking
    last_quality_check = Column(DateTime, default=datetime.utcnow)
    last_data_update = Column(DateTime)

    def __repr__(self):
        return f'<DataQuality {self.symbol}: {self.data_completeness:.1f}%>'