"""
Data Models for the Automated Trading System
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from flask_login import UserMixin

# Import enhanced stock models and use their Base
from .stock_models import (
    Stock, MarketDataSnapshot, MarketCapCategory,
    SymbolMaster, DailySuggestedStock, Base
)

# Per-model ledger tables (capital, position, PnL, trades — multi-model ready)
from .model_ledger_models import ModelSettings, ModelLedger, ModelTrade  # noqa: F401

# Audit tables — Base.metadata.create_all() picks them up on app boot.
from .audit_models import (  # noqa: F401
    AuditOrder, AuditRebalanceDecision,
    AuditModelRanking, AuditModelSignal,
    AuditConfigChange, AuditDataQuality, AuditSystemEvent,
)



class User(UserMixin, Base):
    """User authentication and profile information."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    first_name = Column(String(50))
    last_name = Column(String(50))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_mock_trading_mode = Column(Boolean, default=True)  # Mock trading enabled by default
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    last_activity = Column(DateTime)
    
    # Relationships with other models
    orders = relationship("Order", back_populates="user")
    trades = relationship("Trade", back_populates="user")
    positions = relationship("Position", back_populates="user")
    holdings = relationship("Holding", back_populates="user")
    strategies = relationship("Strategy", back_populates="user")
    configurations = relationship("Configuration", back_populates="user")
    logs = relationship("Log", back_populates="user")
    suggested_stocks = relationship("SuggestedStock", back_populates="user")
    broker_configurations = relationship("BrokerConfiguration", back_populates="user")
    strategy_settings = relationship("UserStrategySettings", back_populates="user")
    auto_trading_settings = relationship("AutoTradingSettings", back_populates="user", uselist=False)
    auto_trading_executions = relationship("AutoTradingExecution", back_populates="user")
    order_performances = relationship("OrderPerformance", back_populates="user")
    webauthn_credentials = relationship("WebAuthnCredential", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f'<User {self.username}>'


class WebAuthnCredential(Base):
    """WebAuthn/Passkey credential storage for passwordless authentication."""
    __tablename__ = 'webauthn_credentials'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    credential_id = Column(LargeBinary, unique=True, nullable=False)  # Raw credential ID bytes
    public_key = Column(LargeBinary, nullable=False)  # COSE public key bytes
    sign_count = Column(Integer, default=0)  # Signature counter for clone detection
    device_name = Column(String(255), default='Passkey')  # User-friendly device name
    transports = Column(Text)  # JSON array of transports: ["usb", "ble", "nfc", "internal"]
    aaguid = Column(String(36))  # Authenticator AAGUID for device identification
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)

    # Relationship
    user = relationship("User", back_populates="webauthn_credentials")

    def __repr__(self):
        return f'<WebAuthnCredential {self.device_name} for user {self.user_id}>'


class Instrument(Base):
    """Tradable securities with metadata."""
    __tablename__ = 'instruments'
    
    id = Column(Integer, primary_key=True)
    exchange_token = Column(String(50), unique=True, nullable=False)
    tradingsymbol = Column(String(50), nullable=False)
    name = Column(String(100))
    exchange = Column(String(20))
    instrument_type = Column(String(20))
    segment = Column(String(20))
    tick_size = Column(Float)
    lot_size = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship with market data
    market_data = relationship("MarketData", back_populates="instrument")


class MarketData(Base):
    """Price, volume, and quote data."""
    __tablename__ = 'market_data'
    
    id = Column(Integer, primary_key=True)
    instrument_id = Column(Integer, ForeignKey('instruments.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    close_price = Column(Float)
    volume = Column(Integer)
    last_price = Column(Float)
    last_quantity = Column(Integer)
    average_price = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship with instrument
    instrument = relationship("Instrument", back_populates="market_data")


class Order(Base):
    """Order details and state tracking."""
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    order_id = Column(String(50), unique=True, nullable=False)
    parent_order_id = Column(String(50))
    exchange_order_id = Column(String(50))
    tradingsymbol = Column(String(50), nullable=False)
    exchange = Column(String(20))
    instrument_token = Column(String(50))
    product = Column(String(10))
    order_type = Column(String(10))
    transaction_type = Column(String(10))
    quantity = Column(Integer)
    disclosed_quantity = Column(Integer)
    price = Column(Float)
    trigger_price = Column(Float)
    average_price = Column(Float)
    filled_quantity = Column(Integer)
    pending_quantity = Column(Integer)
    order_status = Column(String(20))
    status_message = Column(Text)
    tag = Column(String(100))
    placed_at = Column(DateTime)
    placed_by = Column(String(50))
    variety = Column(String(20))
    is_mock_order = Column(Boolean, default=False)  # Mock order flag
    strategy = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="orders")
    trades = relationship("Trade", back_populates="order")


class Trade(Base):
    """Executed trades with fill details."""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    trade_id = Column(String(50), unique=True, nullable=False)
    order_id = Column(String(50), ForeignKey('orders.order_id'), nullable=False)
    exchange_order_id = Column(String(50))
    tradingsymbol = Column(String(50))
    exchange = Column(String(20))
    instrument_token = Column(String(50))
    transaction_type = Column(String(10))
    quantity = Column(Integer)
    price = Column(Float)
    filled_quantity = Column(Integer)
    order_price = Column(Float)
    trade_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="trades")
    order = relationship("Order", back_populates="trades")


class Position(Base):
    """Current portfolio positions."""
    __tablename__ = 'positions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    tradingsymbol = Column(String(50), nullable=False)
    exchange = Column(String(20))
    instrument_token = Column(String(50))
    product = Column(String(10))
    quantity = Column(Integer)
    overnight_quantity = Column(Integer)
    multiplier = Column(Integer)
    average_price = Column(Float)
    close_price = Column(Float)
    last_price = Column(Float)
    value = Column(Float)
    pnl = Column(Float)
    m2m = Column(Float)
    unrealised = Column(Float)
    realised = Column(Float)
    buy_quantity = Column(Integer)
    buy_price = Column(Float)
    buy_value = Column(Float)
    buy_m2m = Column(Float)
    sell_quantity = Column(Integer)
    sell_price = Column(Float)
    sell_value = Column(Float)
    sell_m2m = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with user
    user = relationship("User", back_populates="positions")


class Holding(Base):
    """Portfolio holdings (long-term investments)."""
    __tablename__ = 'holdings'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    tradingsymbol = Column(String(50), nullable=False)
    exchange = Column(String(20))
    instrument_token = Column(String(50))
    product = Column(String(10))
    quantity = Column(Integer)
    average_price = Column(Float)
    last_price = Column(Float)
    market_value = Column(Float)
    invested_value = Column(Float)
    pnl = Column(Float)
    pnl_percentage = Column(Float)
    holding_type = Column(String(10))  # T1, T0, etc.
    authorized_date = Column(String(20))
    authorized_quantity = Column(Integer)
    opening_quantity = Column(Integer)
    holding_quantity = Column(Integer)
    collateral_quantity = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with user
    user = relationship("User", back_populates="holdings")


class Strategy(Base):
    """Strategy selection parameters."""
    __tablename__ = 'strategies'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    parameters = Column(Text)  # JSON string of strategy parameters
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with user
    user = relationship("User", back_populates="strategies")


class Configuration(Base):
    """System settings and thresholds."""
    __tablename__ = 'configurations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # NULL for global configs
    key = Column(String(100), nullable=False)
    value = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with user (optional for global configs)
    user = relationship("User", back_populates="configurations")
    
    # Unique constraint: key should be unique per user (or globally if user_id is NULL)
    __table_args__ = (
        UniqueConstraint('user_id', 'key', name='_user_key_uc'),
    )


class UserStrategySettings(Base):
    """User-specific strategy settings and preferences."""
    __tablename__ = 'user_strategy_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    strategy_name = Column(String(100), nullable=False)  # 'default_risk', 'high_risk'
    is_active = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)  # User can enable/disable
    priority = Column(Integer, default=1)  # Display order
    custom_parameters = Column(Text)  # JSON string for custom strategy parameters
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    
    # Unique constraint to ensure one setting per user per strategy
    __table_args__ = (
        UniqueConstraint('user_id', 'strategy_name', name='unique_user_strategy'),
    )
    
    def __repr__(self):
        return f'<UserStrategySettings user_id={self.user_id} strategy={self.strategy_name} active={self.is_active}>'


class Log(Base):
    """Audit trail and system events."""
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # NULL for system logs
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String(20))
    module = Column(String(50))
    message = Column(Text)
    details = Column(Text)  # JSON string of additional details
    
    # Relationship with user (optional for system logs)
    user = relationship("User", back_populates="logs")


class SuggestedStock(Base):
    """Suggested stocks with performance tracking."""
    __tablename__ = 'suggested_stocks'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    symbol = Column(String(50), nullable=False)
    selection_date = Column(DateTime, default=datetime.utcnow)
    selection_price = Column(Float)
    current_price = Column(Float)
    quantity = Column(Integer)
    strategy_name = Column(String(100))
    status = Column(String(20), default='Active')  # Active, Sold, Expired
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with user
    user = relationship("User", back_populates="suggested_stocks")


class ScreenedStock(Base):
    """Stocks that passed screening criteria."""
    __tablename__ = 'screened_stocks'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False)
    name = Column(String(100))
    sector = Column(String(50))
    exchange = Column(String(20))
    market_cap = Column(Float)
    current_price = Column(Float)
    screening_date = Column(DateTime, default=datetime.utcnow)
    screening_criteria = Column(Text)  # JSON string of criteria used
    financial_data = Column(Text)  # JSON string of financial metrics
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    strategy_selections = relationship("StrategySelection", back_populates="screened_stock")


class StrategySelection(Base):
    """Stocks selected by specific strategies."""
    __tablename__ = 'strategy_selections'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    screened_stock_id = Column(Integer, ForeignKey('screened_stocks.id'), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    selection_date = Column(DateTime, default=datetime.utcnow)
    selection_score = Column(Float)  # Strategy-specific score
    allocation_percentage = Column(Float)  # Portfolio allocation percentage
    position_size = Column(Integer)  # Number of shares
    status = Column(String(20), default='Selected')  # Selected, Executed, Exited
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    screened_stock = relationship("ScreenedStock", back_populates="strategy_selections")
    dry_run_positions = relationship("DryRunPosition", back_populates="strategy_selection")


class DryRunPortfolio(Base):
    """Dry run portfolio for strategy testing."""
    __tablename__ = 'dry_run_portfolios'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    portfolio_id = Column(String(100), unique=True, nullable=False)
    strategy_name = Column(String(100), nullable=False)
    initial_capital = Column(Float, nullable=False)
    current_capital = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User")
    positions = relationship("DryRunPosition", back_populates="portfolio")
    performance_snapshots = relationship("DryRunPerformance", back_populates="portfolio")


class DryRunPosition(Base):
    """Positions in dry run portfolios."""
    __tablename__ = 'dry_run_positions'
    
    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('dry_run_portfolios.id'), nullable=False)
    strategy_selection_id = Column(Integer, ForeignKey('strategy_selections.id'), nullable=False)
    symbol = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)
    average_price = Column(Float)
    unrealized_pnl = Column(Float)
    realized_pnl = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    portfolio = relationship("DryRunPortfolio", back_populates="positions")
    strategy_selection = relationship("StrategySelection", back_populates="dry_run_positions")


class DryRunPerformance(Base):
    """Performance snapshots for dry run portfolios."""
    __tablename__ = 'dry_run_performance'
    
    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('dry_run_portfolios.id'), nullable=False)
    snapshot_date = Column(DateTime, default=datetime.utcnow)
    portfolio_value = Column(Float, nullable=False)
    total_return = Column(Float, nullable=False)
    return_percentage = Column(Float, nullable=False)
    num_positions = Column(Integer, nullable=False)
    performance_metrics = Column(Text)  # JSON string of detailed metrics
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    portfolio = relationship("DryRunPortfolio", back_populates="performance_snapshots")


class ExecutionLog(Base):
    """Log of trading workflow executions."""
    __tablename__ = 'execution_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    execution_id = Column(String(100), unique=True, nullable=False)
    execution_type = Column(String(50), nullable=False)  # 'complete_workflow', 'dry_run', 'screening_only'
    status = Column(String(20), nullable=False)  # 'success', 'error', 'partial'
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration_seconds = Column(Float)
    screened_stocks_count = Column(Integer, default=0)
    strategies_executed = Column(Text)  # JSON string of strategy names
    results_summary = Column(Text)  # JSON string of execution results
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")


class AIAnalysis(Base):
    """AI analysis results from ChatGPT."""
    __tablename__ = 'ai_analyses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    analysis_type = Column(String(50), nullable=False)  # 'stock', 'portfolio', 'strategy_comparison'
    target_id = Column(String(100))  # Stock symbol, strategy name, etc.
    analysis_data = Column(Text, nullable=False)  # JSON string of analysis results
    confidence_score = Column(Float)
    recommendation = Column(String(20))  # BUY, HOLD, SELL
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")


class BrokerConfiguration(Base):
    """Broker configuration and credentials."""
    __tablename__ = 'broker_configurations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # NULL for global configs
    broker_name = Column(String(50), nullable=False)  # 'fyers'
    client_id = Column(String(100))
    access_token = Column(Text)
    refresh_token = Column(Text)
    api_key = Column(String(200))
    api_secret = Column(Text)
    redirect_url = Column(String(500))
    app_type = Column(String(20))  # '100' for web, '2' for mobile
    is_active = Column(Boolean, default=True)
    is_connected = Column(Boolean, default=False)
    last_connection_test = Column(DateTime)
    connection_status = Column(String(20))  # 'connected', 'disconnected', 'error'
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with user (optional for global configs)
    user = relationship("User")
    
    # Unique constraint: broker_name should be unique per user (or globally if user_id is NULL)
    __table_args__ = (
        UniqueConstraint('user_id', 'broker_name', name='_user_broker_uc'),
    )


class AutoTradingSettings(Base):
    """Auto-trading settings and weekly limits."""
    __tablename__ = 'auto_trading_settings'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)
    is_enabled = Column(Boolean, default=False)  # Auto-trading enabled/disabled
    max_amount_per_week = Column(Float, default=10000.0)  # Max investment per week (₹)
    max_buys_per_week = Column(Integer, default=5)  # Max number of trades per week
    preferred_strategies = Column(Text)  # JSON array of preferred strategies: ['default_risk', 'high_risk']
    minimum_confidence_score = Column(Float, default=0.7)  # Minimum confidence score
    minimum_market_sentiment = Column(Float, default=0.0)  # Minimum market sentiment (-1 to 1)
    auto_stop_loss_enabled = Column(Boolean, default=True)  # Auto set stop-loss
    auto_target_price_enabled = Column(Boolean, default=True)  # Auto set target price
    execution_time = Column(String(10), default='09:20')  # Time to execute (HH:MM format, market opens 9:15 AM)
    trading_mode = Column(String(20), default='swing')  # 'swing', 'day', 'both'
    virtual_capital = Column(Float, default=100000.0)    # Legacy AutoTradingSettings field; live ledger uses model_settings.invested_amount
    # Per-user EMA 200/400 strategy overrides. JSONB blob; merged onto
    # StrategyConfig defaults at runtime by EMACrossoverRunner.
    ema_strategy_config = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")
    executions = relationship("AutoTradingExecution", back_populates="settings")

    def __repr__(self):
        return f'<AutoTradingSettings user_id={self.user_id} enabled={self.is_enabled}>'


class AutoTradingExecution(Base):
    """Log of auto-trading executions."""
    __tablename__ = 'auto_trading_executions'

    id = Column(Integer, primary_key=True)
    settings_id = Column(Integer, ForeignKey('auto_trading_settings.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    execution_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), nullable=False)  # 'success', 'skipped', 'failed', 'partial'

    # Market sentiment at execution time
    market_sentiment_type = Column(String(20))  # 'greedy', 'fear', 'neutral'
    market_sentiment_score = Column(Float)
    ai_confidence = Column(Float)

    # Weekly limits check
    weekly_amount_spent = Column(Float, default=0.0)
    weekly_buys_count = Column(Integer, default=0)
    remaining_weekly_amount = Column(Float)
    remaining_weekly_buys = Column(Integer)

    # Account balance check
    account_balance = Column(Float)
    available_to_invest = Column(Float)

    # Execution results
    orders_created = Column(Integer, default=0)
    total_amount_invested = Column(Float, default=0.0)
    selected_strategies = Column(Text)  # JSON array of strategies used
    execution_details = Column(Text)  # JSON string of execution details
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    settings = relationship("AutoTradingSettings", back_populates="executions")
    user = relationship("User")
    orders = relationship("OrderPerformance", back_populates="auto_execution")

    def __repr__(self):
        return f'<AutoTradingExecution id={self.id} user_id={self.user_id} status={self.status}>'


class OrderPerformance(Base):
    """Track order performance and metrics."""
    __tablename__ = 'order_performance'

    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), ForeignKey('orders.order_id'), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    auto_execution_id = Column(Integer, ForeignKey('auto_trading_executions.id'), nullable=True)

    # Order details at creation
    symbol = Column(String(50), nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    original_quantity = Column(Integer)                    # Quantity at entry (never changes)
    remaining_quantity = Column(Integer)                   # Quantity still held
    stop_loss = Column(Float)
    target_price = Column(Float)
    target_price_1 = Column(Float)                         # Partial-exit target 1 (legacy slot, currently unused)
    target_price_2 = Column(Float)                         # Partial-exit target 2 (legacy slot, currently unused)
    target_price_3 = Column(Float)                         # Partial-exit target 3 (legacy slot, currently unused)
    strategy = Column(String(50))
    trading_type = Column(String(20), default='swing')     # 'swing' or 'day'

    # Partial exit tracking (legacy slots — EMA 200/400 strategy uses single 15% partial)
    partial_exit_1_done = Column(Boolean, default=False)
    partial_exit_2_done = Column(Boolean, default=False)
    partial_exit_3_done = Column(Boolean, default=False)
    partial_pnl_realized = Column(Float, default=0.0)      # Running sum of partial exit P&L

    # Current status
    current_price = Column(Float)
    current_value = Column(Float)
    unrealized_pnl = Column(Float)
    unrealized_pnl_pct = Column(Float)

    # Exit details (when order is closed)
    exit_price = Column(Float)
    exit_date = Column(DateTime)
    exit_reason = Column(String(50))  # 'stop_loss', 'target_reached', 'manual', 'time_based'
    realized_pnl = Column(Float)
    realized_pnl_pct = Column(Float)

    # Performance metrics
    days_held = Column(Integer)
    max_profit_reached = Column(Float)  # Maximum profit during holding period
    max_loss_reached = Column(Float)    # Maximum loss during holding period
    prediction_accuracy = Column(Float)  # How accurate was ML prediction

    # Status tracking
    is_active = Column(Boolean, default=True)
    is_profitable = Column(Boolean)
    performance_rating = Column(String(20))  # 'excellent', 'good', 'poor', 'loss'

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_checked_at = Column(DateTime)

    # Relationships
    order = relationship("Order")
    user = relationship("User")
    auto_execution = relationship("AutoTradingExecution", back_populates="orders")
    daily_snapshots = relationship("OrderPerformanceSnapshot", back_populates="order_performance")

    def __repr__(self):
        return f'<OrderPerformance order_id={self.order_id} symbol={self.symbol} pnl={self.unrealized_pnl}>'


class OrderPerformanceSnapshot(Base):
    """Daily snapshots of order performance."""
    __tablename__ = 'order_performance_snapshots'

    id = Column(Integer, primary_key=True)
    order_performance_id = Column(Integer, ForeignKey('order_performance.id'), nullable=False)
    snapshot_date = Column(DateTime, default=datetime.utcnow)

    # Price and value at snapshot time
    price = Column(Float, nullable=False)
    value = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False)
    unrealized_pnl_pct = Column(Float, nullable=False)

    # Additional metrics
    days_since_entry = Column(Integer)
    price_change_from_entry_pct = Column(Float)
    distance_to_target_pct = Column(Float)
    distance_to_stoploss_pct = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    order_performance = relationship("OrderPerformance", back_populates="daily_snapshots")

    def __repr__(self):
        return f'<OrderPerformanceSnapshot id={self.id} date={self.snapshot_date} pnl={self.unrealized_pnl}>'
