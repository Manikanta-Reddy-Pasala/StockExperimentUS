"""
Enhanced Data Models for Stock Management
Adds comprehensive stock data storage and categorization
"""
from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, Enum, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

# Create separate base to avoid circular imports
Base = declarative_base()


class MarketCapCategory(enum.Enum):
    """Market capitalization categories."""
    LARGE_CAP = "large_cap"
    MID_CAP = "mid_cap"
    SMALL_CAP = "small_cap"


class Stock(Base):
    """Master stock information with categorization."""
    __tablename__ = 'stocks'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    exchange = Column(String(20), nullable=False, default='NSE')
    sector = Column(String(100))

    # Market capitalization data
    market_cap = Column(Float)  # in crores
    market_cap_category = Column(String(20), index=True)  # Use String instead of Enum for compatibility
    listing_date = Column(Date)  # IPO/listing date for listing age checks

    # Current market data
    current_price = Column(Float)
    volume = Column(BigInteger)  # Use BigInteger to handle large volume values

    # Fundamental ratios (basic set that matches actual table)
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    roe = Column(Float)  # Return on Equity
    debt_to_equity = Column(Float)
    dividend_yield = Column(Float)
    peg_ratio = Column(Float)  # Price/Earnings to Growth
    roa = Column(Float)  # Return on Assets
    operating_margin = Column(Float)
    net_margin = Column(Float)
    profit_margin = Column(Float)
    current_ratio = Column(Float)
    quick_ratio = Column(Float)
    revenue_growth = Column(Float)
    earnings_growth = Column(Float)
    eps = Column(Float)
    book_value = Column(Float)
    beta = Column(Float)

    # Volatility and Risk Metrics for Stage 1 Filtering
    atr_14 = Column(Float)  # Average True Range (14 days)
    atr_percentage = Column(Float)  # ATR as percentage of price
    historical_volatility_1y = Column(Float)  # 1-year historical volatility
    avg_daily_volume_20d = Column(Float)  # 20-day average volume (matches schema)
    avg_daily_turnover = Column(Float)  # Average daily turnover in crores
    bid_ask_spread = Column(Float)  # Bid-ask spread percentage
    trades_per_day = Column(Integer)  # Average trades per day
    liquidity_score = Column(Float)  # Liquidity score (0-1 scale)

    # Status and metadata
    is_active = Column(Boolean, default=True, index=True)
    is_tradeable = Column(Boolean, default=True)
    is_suspended = Column(Boolean, default=False)
    is_delisted = Column(Boolean, default=False)
    is_stage_listed = Column(Boolean, default=False)
    volatility_last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # For volatility update tracking
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # For stock data update tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Stock {self.symbol}: {self.name}>'


class SymbolMaster(Base):
    """Raw symbol master data from broker APIs."""
    __tablename__ = 'symbol_master'

    # Symbol identification - fytoken is the primary key (TRUE UNIQUE IDENTIFIER)
    fytoken = Column(String(50), primary_key=True, nullable=False)  # Fyers unique token (PRIMARY KEY)
    symbol = Column(String(50), nullable=False, index=True)  # NSE:SYMBOL-EQ
    name = Column(String(200), nullable=False)
    exchange = Column(String(20), nullable=False, index=True)  # NSE, BSE
    segment = Column(String(20), nullable=False)  # CM (Capital Market)
    instrument_type = Column(String(20), nullable=False)  # EQ (Equity)

    # Trading parameters
    lot_size = Column(Integer, default=1)
    tick_size = Column(Float, default=0.05)
    isin = Column(String(20))  # ISIN code

    # Data source and versioning
    data_source = Column(String(20), default='yfinance')
    source_updated = Column(String(20))  # Last updated timestamp from source
    download_date = Column(DateTime, default=datetime.utcnow)

    # Status flags
    is_active = Column(Boolean, default=True, index=True)
    is_equity = Column(Boolean, default=True, index=True)  # Only equity symbols

    # Verification status for Fyers API compatibility
    is_fyers_verified = Column(Boolean, default=False, index=True)
    verification_date = Column(DateTime)
    verification_error = Column(Text)
    last_quote_check = Column(DateTime)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint to prevent duplicate symbol-exchange combinations
    __table_args__ = (
        UniqueConstraint('symbol', 'exchange', name='_symbol_exchange_uc'),
    )

    def __repr__(self):
        return f'<SymbolMaster {self.symbol}: {self.name}>'


class DailySuggestedStock(Base):
    """Daily suggested stock picks from strategy screening."""
    __tablename__ = 'daily_suggested_stocks'
    __table_args__ = (
        UniqueConstraint('date', 'symbol', 'strategy', 'model_type', name='daily_suggested_stocks_date_symbol_strategy_model_type_key'),
    )

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    strategy = Column(String(50), nullable=False, default='ema_200_400')
    model_type = Column(String(20), nullable=False, default='crossover')
    stock_name = Column(String(200))
    current_price = Column(Float)
    market_cap = Column(Float)
    selection_score = Column(Float)
    rank = Column(Integer)
    target_price = Column(Float)
    stop_loss = Column(Float)
    recommendation = Column(String(20))
    reason = Column(Text)
    sector = Column(String(100))
    market_cap_category = Column(String(20))
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    roe = Column(Float)
    beta = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DailySuggestedStock {self.symbol} ({self.date})>'


class MarketDataSnapshot(Base):
    """Daily market data snapshots for analysis."""
    __tablename__ = 'market_data_snapshots'
    
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    
    # Market indices
    nifty_50 = Column(Float)
    sensex = Column(Float)
    nifty_midcap = Column(Float)
    nifty_smallcap = Column(Float)
    
    # Market statistics
    total_stocks_tracked = Column(Integer)
    large_cap_avg_change = Column(Float)
    mid_cap_avg_change = Column(Float)
    small_cap_avg_change = Column(Float)
    
    # Volume data
    total_volume = Column(Integer)
    advance_decline_ratio = Column(Float)
    
    # Metadata
    data_source = Column(String(20), default='yfinance')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint('snapshot_date', name='_daily_snapshot_uc'),
    )
