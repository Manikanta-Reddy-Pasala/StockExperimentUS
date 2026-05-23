-- Database initialization script
-- This script ensures all tables are created properly

-- Create the trading_system database if it doesn't exist
-- (This is handled by POSTGRES_DB environment variable)

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create tables (these will be created by SQLAlchemy, but we can add them here as backup)
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    is_mock_trading_mode BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    last_activity TIMESTAMP
);

-- Create admin user if it doesn't exist
-- Password hash for 'admin123' using bcrypt
INSERT INTO users (username, email, password_hash, first_name, last_name, is_active, is_admin, created_at)
VALUES (
    'admin',
    'admin@trading-system.com',
    '$2b$12$C4TAPNHIUChvMlPrxow22u4evaMMKVqdWlAZ7m6ZpQUovjg0fF7JW', -- admin123
    'System',
    'Administrator',
    TRUE,
    TRUE,
    CURRENT_TIMESTAMP
) ON CONFLICT (username) DO NOTHING;

-- Create other essential tables (these will be created by SQLAlchemy)
CREATE TABLE IF NOT EXISTS instruments (
    id SERIAL PRIMARY KEY,
    exchange_token VARCHAR(50) UNIQUE NOT NULL,
    tradingsymbol VARCHAR(50) NOT NULL,
    name VARCHAR(100),
    exchange VARCHAR(20),
    instrument_type VARCHAR(20),
    segment VARCHAR(20),
    lot_size INTEGER DEFAULT 1,
    tick_size DECIMAL(10,4) DEFAULT 0.05,
    expiry_date DATE,
    strike_price DECIMAL(10,2),
    option_type VARCHAR(2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    order_id VARCHAR(50) UNIQUE NOT NULL,
    parent_order_id VARCHAR(50),
    exchange_order_id VARCHAR(50),
    tradingsymbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(20),
    instrument_token VARCHAR(50),
    product VARCHAR(10),
    order_type VARCHAR(10),
    transaction_type VARCHAR(10),
    quantity INTEGER,
    disclosed_quantity INTEGER,
    price DECIMAL(10,2),
    trigger_price DECIMAL(10,2),
    average_price DECIMAL(10,2),
    filled_quantity INTEGER,
    pending_quantity INTEGER,
    order_status VARCHAR(20),
    status_message TEXT,
    tag VARCHAR(100),
    placed_at TIMESTAMP,
    placed_by VARCHAR(50),
    variety VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    trade_id VARCHAR(50) UNIQUE NOT NULL,
    order_id VARCHAR(50) REFERENCES orders(order_id),
    exchange_order_id VARCHAR(50),
    tradingsymbol VARCHAR(50),
    exchange VARCHAR(20),
    instrument_token VARCHAR(50),
    transaction_type VARCHAR(10),
    quantity INTEGER,
    price DECIMAL(10,2),
    filled_quantity INTEGER,
    order_price DECIMAL(10,2),
    trade_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tradingsymbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(20),
    instrument_token VARCHAR(50),
    product VARCHAR(10),
    quantity INTEGER,
    overnight_quantity INTEGER,
    multiplier INTEGER,
    average_price DECIMAL(10,2),
    close_price DECIMAL(10,2),
    last_price DECIMAL(10,2),
    value DECIMAL(15,2),
    pnl DECIMAL(15,2),
    m2m DECIMAL(15,2),
    unrealised DECIMAL(15,2),
    realised DECIMAL(15,2),
    buy_quantity INTEGER,
    buy_price DECIMAL(10,2),
    buy_value DECIMAL(15,2),
    buy_m2m DECIMAL(15,2),
    sell_quantity INTEGER,
    sell_price DECIMAL(10,2),
    sell_value DECIMAL(15,2),
    sell_m2m DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    parameters JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suggested_stocks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    recommendation VARCHAR(20),
    target_price DECIMAL(10,2),
    stop_loss DECIMAL(10,2),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configurations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    key VARCHAR(100) NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, key)
);

CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    module VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broker_configurations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    broker_name VARCHAR(50) NOT NULL,
    client_id VARCHAR(100),
    access_token TEXT,
    refresh_token TEXT,
    api_key VARCHAR(200),
    api_secret TEXT,
    redirect_url VARCHAR(500),
    app_type VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    is_connected BOOLEAN DEFAULT FALSE,
    last_connection_test TIMESTAMP,
    connection_status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, broker_name)
);

-- Stock Strategy Tables
-- Note: Stocks table contains only verified stocks with live API data
-- Verification is handled in symbol_master table before stock creation
CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    exchange VARCHAR(20) NOT NULL DEFAULT 'NSE',
    sector VARCHAR(100),
    market_cap DOUBLE PRECISION,  -- in crores, matches SQLAlchemy Float
    market_cap_category VARCHAR(20),
    listing_date DATE,
    current_price DOUBLE PRECISION,  -- matches SQLAlchemy Float
    volume BIGINT,  -- Handle high volume stocks like IDEA (2.6B+ volume)
    pe_ratio DOUBLE PRECISION,  -- matches SQLAlchemy Float
    pb_ratio DOUBLE PRECISION,  -- matches SQLAlchemy Float
    roe DOUBLE PRECISION,  -- matches SQLAlchemy Float
    debt_to_equity DOUBLE PRECISION,  -- matches SQLAlchemy Float
    dividend_yield DOUBLE PRECISION,  -- matches SQLAlchemy Float
    peg_ratio DOUBLE PRECISION,
    roa DOUBLE PRECISION,
    operating_margin DOUBLE PRECISION,
    net_margin DOUBLE PRECISION,
    profit_margin DOUBLE PRECISION,
    current_ratio DOUBLE PRECISION,
    quick_ratio DOUBLE PRECISION,
    revenue_growth DOUBLE PRECISION,
    earnings_growth DOUBLE PRECISION,
    eps DOUBLE PRECISION,
    book_value DOUBLE PRECISION,
    beta DOUBLE PRECISION,  -- matches SQLAlchemy Float
    -- Volatility and risk metrics
    atr_14 DOUBLE PRECISION,  -- Average True Range (14-day period)
    atr_percentage DOUBLE PRECISION,  -- ATR as percentage of current price
    historical_volatility_1y DOUBLE PRECISION,  -- Annualized historical volatility
    bid_ask_spread DOUBLE PRECISION,  -- Estimated bid-ask spread
    avg_daily_volume_20d DOUBLE PRECISION,  -- 20-day average daily volume
    avg_daily_turnover DOUBLE PRECISION,  -- Average daily turnover in crores
    trades_per_day INTEGER,  -- Average trades per day
    liquidity_score DOUBLE PRECISION,  -- Liquidity score (0-1 scale) for Stage 1 filtering
    volatility_last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- For tracking volatility updates
    volatility DECIMAL(10,6),  -- Calculated volatility for the stock
    is_active BOOLEAN DEFAULT TRUE,
    is_tradeable BOOLEAN DEFAULT TRUE,
    is_suspended BOOLEAN DEFAULT FALSE,
    is_delisted BOOLEAN DEFAULT FALSE,
    is_stage_listed BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for stocks table (matches SQLAlchemy model)
CREATE INDEX IF NOT EXISTS ix_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS ix_stocks_market_cap_category ON stocks(market_cap_category);
CREATE INDEX IF NOT EXISTS ix_stocks_is_active ON stocks(is_active);

-- Symbol Master table for raw broker data (fytoken as primary key)
-- This table stores all symbols from Fyers API and handles verification
-- Only verified symbols (is_fyers_verified = true) are promoted to stocks table
CREATE TABLE IF NOT EXISTS symbol_master (
    fytoken VARCHAR(50) PRIMARY KEY NOT NULL,  -- Fyers unique token as primary key
    symbol VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    segment VARCHAR(20) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL,
    lot_size INTEGER DEFAULT 1,
    tick_size DOUBLE PRECISION DEFAULT 0.05,  -- matches SQLAlchemy Float
    isin VARCHAR(20),
    data_source VARCHAR(20) DEFAULT 'fyers',
    source_updated VARCHAR(20),
    download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_equity BOOLEAN DEFAULT TRUE,
    -- Verification columns - validates symbols work with Fyers API quotes
    is_fyers_verified BOOLEAN DEFAULT FALSE,
    verification_date TIMESTAMP,
    verification_error TEXT,
    last_quote_check TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Unique constraint to prevent duplicate symbol-exchange combinations
    CONSTRAINT _symbol_exchange_uc UNIQUE(symbol, exchange)
);

-- Indexes for symbol_master table (matches SQLAlchemy model)
CREATE INDEX IF NOT EXISTS ix_symbol_master_symbol ON symbol_master(symbol);
CREATE INDEX IF NOT EXISTS ix_symbol_master_exchange ON symbol_master(exchange);
CREATE INDEX IF NOT EXISTS ix_symbol_master_is_active ON symbol_master(is_active);
CREATE INDEX IF NOT EXISTS ix_symbol_master_is_equity ON symbol_master(is_equity);
CREATE INDEX IF NOT EXISTS ix_symbol_master_is_fyers_verified ON symbol_master(is_fyers_verified);

-- Market Data Snapshots table
CREATE TABLE IF NOT EXISTS market_data_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date VARCHAR(10) NOT NULL,
    nifty_50 DECIMAL(10,2),
    sensex DECIMAL(10,2),
    nifty_midcap DECIMAL(10,2),
    nifty_smallcap DECIMAL(10,2),
    total_stocks_tracked INTEGER,
    large_cap_avg_change DECIMAL(10,4),
    mid_cap_avg_change DECIMAL(10,4),
    small_cap_avg_change DECIMAL(10,4),
    total_volume BIGINT,
    advance_decline_ratio DECIMAL(10,4),
    data_source VARCHAR(20) DEFAULT 'fyers',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date)
);

-- Portfolio Performance Tracking Tables (Broker-Aware)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    broker_name VARCHAR(50) NOT NULL,
    snapshot_date DATE NOT NULL,
    portfolio_value DECIMAL(15,2) NOT NULL,
    cash_balance DECIMAL(15,2) DEFAULT 0.0,
    total_invested DECIMAL(15,2) DEFAULT 0.0,
    total_pnl DECIMAL(15,2) DEFAULT 0.0,
    day_pnl DECIMAL(15,2) DEFAULT 0.0,
    return_percent DECIMAL(8,4) DEFAULT 0.0,
    holdings_data JSONB,
    positions_data JSONB,
    performance_metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, broker_name, snapshot_date)
);

CREATE TABLE IF NOT EXISTS portfolio_performance_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    broker_name VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    portfolio_value DECIMAL(15,2) NOT NULL,
    daily_return DECIMAL(8,4) DEFAULT 0.0,
    cumulative_return DECIMAL(8,4) DEFAULT 0.0,
    drawdown DECIMAL(8,4) DEFAULT 0.0,
    volatility DECIMAL(8,4) DEFAULT 0.0,
    sharpe_ratio DECIMAL(8,4) DEFAULT 0.0,
    max_drawdown DECIMAL(8,4) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    best_day DECIMAL(8,4) DEFAULT 0.0,
    worst_day DECIMAL(8,4) DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, broker_name, date)
);

-- ML Training and Model Management Tables


-- Historical Data Tables for Enhanced Technical Analysis
-- Historical OHLCV data for comprehensive technical indicator calculations
-- Stores ALL available data from Fyers API plus calculated fields
CREATE TABLE IF NOT EXISTS historical_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,

    -- Core OHLCV Data from Fyers API (ALL 6 fields)
    timestamp BIGINT NOT NULL,  -- Original Unix timestamp
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,

    -- Calculated fields for enhanced analysis
    adj_close DOUBLE PRECISION,  -- Adjusted close for splits/dividends
    turnover DOUBLE PRECISION,  -- Daily turnover in INR (price * volume)
    price_change DOUBLE PRECISION,  -- Close - Open
    price_change_pct DOUBLE PRECISION,  -- (Close - Open) / Open * 100
    high_low_pct DOUBLE PRECISION,  -- (High - Low) / Close * 100
    body_pct DOUBLE PRECISION,  -- |Close - Open| / (High - Low) * 100
    upper_shadow_pct DOUBLE PRECISION,  -- Upper wick percentage
    lower_shadow_pct DOUBLE PRECISION,  -- Lower wick percentage

    -- Volume analysis
    volume_sma_ratio DOUBLE PRECISION,  -- Volume / SMA(Volume, 20)
    price_volume_trend DOUBLE PRECISION,  -- PVT indicator value

    -- Data quality and metadata
    is_adjusted BOOLEAN DEFAULT FALSE,
    data_source VARCHAR(20) DEFAULT 'fyers',
    api_resolution VARCHAR(10),  -- Original API resolution (1D, 5M, etc.)
    data_quality_score DOUBLE PRECISION,  -- 0-1 score for data completeness

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(symbol, date)
);

-- Pre-calculated technical indicators for performance
CREATE TABLE IF NOT EXISTS technical_indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,

    -- Context indicators (daily) used by HTF gating
    sma_50 DOUBLE PRECISION,
    sma_200 DOUBLE PRECISION,

    calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_points_used INTEGER,
    UNIQUE(symbol, date)
);

-- Market benchmark data for beta calculations
CREATE TABLE IF NOT EXISTS market_benchmarks (
    id SERIAL PRIMARY KEY,
    benchmark VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT,
    market_cap DOUBLE PRECISION,
    pe_ratio DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(benchmark, date)
);

-- Data quality tracking
CREATE TABLE IF NOT EXISTS data_quality_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) UNIQUE NOT NULL,
    earliest_date DATE,
    latest_date DATE,
    total_days INTEGER,
    missing_days INTEGER,
    data_completeness DOUBLE PRECISION,
    price_consistency_score DOUBLE PRECISION,
    volume_consistency_score DOUBLE PRECISION,
    overall_quality_score DOUBLE PRECISION,
    has_200_day_history BOOLEAN DEFAULT FALSE,
    has_1_year_history BOOLEAN DEFAULT FALSE,
    meets_min_quality BOOLEAN DEFAULT FALSE,
    last_quality_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_data_update TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_market_cap_category ON stocks(market_cap_category);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_broker_date ON portfolio_snapshots(user_id, broker_name, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_broker_date ON portfolio_performance_history(user_id, broker_name, date);

CREATE INDEX IF NOT EXISTS idx_symbol_master_symbol ON symbol_master(symbol);
CREATE INDEX IF NOT EXISTS idx_symbol_master_exchange ON symbol_master(exchange);
CREATE INDEX IF NOT EXISTS idx_symbol_master_active ON symbol_master(is_active, is_equity);
CREATE INDEX IF NOT EXISTS idx_symbol_master_verified ON symbol_master(is_fyers_verified);
CREATE INDEX IF NOT EXISTS idx_market_data_snapshots_date ON market_data_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_stocks_active ON stocks(is_active, is_tradeable);
CREATE INDEX IF NOT EXISTS idx_stocks_market_cap ON stocks(market_cap);
-- Volatility indexes for screening performance
CREATE INDEX IF NOT EXISTS idx_stocks_atr_percentage ON stocks(atr_percentage);
CREATE INDEX IF NOT EXISTS idx_stocks_beta ON stocks(beta);
CREATE INDEX IF NOT EXISTS idx_stocks_historical_volatility ON stocks(historical_volatility_1y);
CREATE INDEX IF NOT EXISTS idx_stocks_avg_volume_20d ON stocks(avg_daily_volume_20d);
CREATE INDEX IF NOT EXISTS idx_stocks_volatility_last_updated ON stocks(volatility_last_updated);

-- Historical Data Indexes for Performance (matches SQLAlchemy model)
CREATE INDEX IF NOT EXISTS idx_historical_symbol ON historical_data(symbol);
CREATE INDEX IF NOT EXISTS idx_historical_date ON historical_data(date);
CREATE INDEX IF NOT EXISTS idx_historical_symbol_date ON historical_data(symbol, date);
CREATE INDEX IF NOT EXISTS idx_historical_date_desc ON historical_data(date DESC);
CREATE INDEX IF NOT EXISTS idx_historical_symbol_date_desc ON historical_data(symbol, date DESC);
-- Composite indexes from SQLAlchemy model
CREATE INDEX IF NOT EXISTS ix_historical_symbol_date ON historical_data(symbol, date);
CREATE INDEX IF NOT EXISTS ix_historical_date_symbol ON historical_data(date, symbol);

-- Technical Indicators Indexes
CREATE INDEX IF NOT EXISTS idx_technical_symbol ON technical_indicators(symbol);
CREATE INDEX IF NOT EXISTS idx_technical_date ON technical_indicators(date);
CREATE INDEX IF NOT EXISTS idx_technical_symbol_date ON technical_indicators(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technical_symbol_date_desc ON technical_indicators(symbol, date DESC);

COMMENT ON TABLE technical_indicators IS 'Daily SMA cache (50/200) used by the EMA 200/400 1H strategy for HTF trend gating.';

-- Market Benchmarks Indexes
CREATE INDEX IF NOT EXISTS idx_benchmark_name ON market_benchmarks(benchmark);
CREATE INDEX IF NOT EXISTS idx_benchmark_date ON market_benchmarks(date);
CREATE INDEX IF NOT EXISTS idx_benchmark_name_date ON market_benchmarks(benchmark, date);
CREATE INDEX IF NOT EXISTS idx_benchmark_date_desc ON market_benchmarks(date DESC);

-- Data Quality Indexes
CREATE INDEX IF NOT EXISTS idx_quality_symbol ON data_quality_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_quality_has_1year ON data_quality_metrics(has_1_year_history);
CREATE INDEX IF NOT EXISTS idx_quality_meets_min ON data_quality_metrics(meets_min_quality);

-- Pipeline Tracking Table for Saga Pattern
CREATE TABLE IF NOT EXISTS pipeline_tracking (
    id SERIAL PRIMARY KEY,
    step_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    records_processed INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    failure_reason TEXT,
    last_error TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(step_name)
);


-- Pipeline Tracking Indexes
CREATE INDEX IF NOT EXISTS idx_pipeline_tracking_step ON pipeline_tracking(step_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_tracking_status ON pipeline_tracking(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_tracking_started_at ON pipeline_tracking(started_at);

-- Admin Task Tracking Table for UI persistence
CREATE TABLE IF NOT EXISTS admin_task_tracking (
    task_id VARCHAR(100) PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    status VARCHAR(20) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    steps JSONB DEFAULT '[]'::jsonb,
    output TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Admin Task Tracking Indexes
CREATE INDEX IF NOT EXISTS idx_admin_task_status ON admin_task_tracking(status);
CREATE INDEX IF NOT EXISTS idx_admin_task_created ON admin_task_tracking(created_at DESC);

-- ============================================================================
-- AUTO-TRADING TABLES
-- Handles auto-trading settings, execution tracking, and performance monitoring
-- ============================================================================

-- Auto-Trading Settings Table
CREATE TABLE IF NOT EXISTS auto_trading_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    is_enabled BOOLEAN DEFAULT FALSE,
    max_amount_per_week FLOAT DEFAULT 10000.0,
    max_buys_per_week INTEGER DEFAULT 5,
    preferred_strategies TEXT,  -- JSON array
    minimum_confidence_score FLOAT DEFAULT 0.7,
    minimum_market_sentiment FLOAT DEFAULT 0.0,
    auto_stop_loss_enabled BOOLEAN DEFAULT TRUE,
    auto_target_price_enabled BOOLEAN DEFAULT TRUE,
    execution_time VARCHAR(10) DEFAULT '09:20',  -- Market opens at 9:15 AM, execute 5 min later
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Auto-Trading Settings Index
CREATE INDEX IF NOT EXISTS idx_auto_trading_settings_user ON auto_trading_settings(user_id);

-- Auto-Trading Executions Table
CREATE TABLE IF NOT EXISTS auto_trading_executions (
    id SERIAL PRIMARY KEY,
    settings_id INTEGER NOT NULL REFERENCES auto_trading_settings(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    execution_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,  -- 'success', 'skipped', 'failed', 'partial'

    -- Market sentiment
    market_sentiment_type VARCHAR(20),
    market_sentiment_score FLOAT,
    ai_confidence FLOAT,

    -- Weekly limits
    weekly_amount_spent FLOAT DEFAULT 0.0,
    weekly_buys_count INTEGER DEFAULT 0,
    remaining_weekly_amount FLOAT,
    remaining_weekly_buys INTEGER,

    -- Account balance
    account_balance FLOAT,
    available_to_invest FLOAT,

    -- Results
    orders_created INTEGER DEFAULT 0,
    total_amount_invested FLOAT DEFAULT 0.0,
    selected_strategies TEXT,  -- JSON array
    execution_details TEXT,  -- JSON
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Auto-Trading Executions Indexes
CREATE INDEX IF NOT EXISTS idx_auto_trading_executions_user ON auto_trading_executions(user_id);
CREATE INDEX IF NOT EXISTS idx_auto_trading_executions_date ON auto_trading_executions(execution_date);
CREATE INDEX IF NOT EXISTS idx_auto_trading_executions_status ON auto_trading_executions(status);

-- Order Performance Table
CREATE TABLE IF NOT EXISTS order_performance (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    auto_execution_id INTEGER REFERENCES auto_trading_executions(id) ON DELETE SET NULL,

    -- Order details
    symbol VARCHAR(50) NOT NULL,
    entry_price FLOAT NOT NULL,
    quantity INTEGER NOT NULL,
    stop_loss FLOAT,
    target_price FLOAT,

    -- Current status
    current_price FLOAT,
    current_value FLOAT,
    unrealized_pnl FLOAT,
    unrealized_pnl_pct FLOAT,

    -- Exit details
    exit_price FLOAT,
    exit_date TIMESTAMP,
    exit_reason VARCHAR(50),
    realized_pnl FLOAT,
    realized_pnl_pct FLOAT,

    -- Performance metrics
    days_held INTEGER,
    max_profit_reached FLOAT,
    max_loss_reached FLOAT,
    prediction_accuracy FLOAT,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_profitable BOOLEAN,
    performance_rating VARCHAR(20),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP
);

-- Order Performance Indexes
CREATE INDEX IF NOT EXISTS idx_order_performance_user ON order_performance(user_id);
CREATE INDEX IF NOT EXISTS idx_order_performance_symbol ON order_performance(symbol);
CREATE INDEX IF NOT EXISTS idx_order_performance_active ON order_performance(is_active);
CREATE INDEX IF NOT EXISTS idx_order_performance_execution ON order_performance(auto_execution_id);

-- Order Performance Snapshots Table
CREATE TABLE IF NOT EXISTS order_performance_snapshots (
    id SERIAL PRIMARY KEY,
    order_performance_id INTEGER NOT NULL REFERENCES order_performance(id) ON DELETE CASCADE,
    snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Snapshot values
    price FLOAT NOT NULL,
    value FLOAT NOT NULL,
    unrealized_pnl FLOAT NOT NULL,
    unrealized_pnl_pct FLOAT NOT NULL,

    -- Metrics
    days_since_entry INTEGER,
    price_change_from_entry_pct FLOAT,
    distance_to_target_pct FLOAT,
    distance_to_stoploss_pct FLOAT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Order Performance Snapshots Indexes
CREATE INDEX IF NOT EXISTS idx_order_snapshots_performance ON order_performance_snapshots(order_performance_id);
CREATE INDEX IF NOT EXISTS idx_order_snapshots_date ON order_performance_snapshots(snapshot_date);

-- Trigger function for updating updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for auto_trading_settings
DROP TRIGGER IF EXISTS update_auto_trading_settings_updated_at ON auto_trading_settings;
CREATE TRIGGER update_auto_trading_settings_updated_at
    BEFORE UPDATE ON auto_trading_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for order_performance
DROP TRIGGER IF EXISTS update_order_performance_updated_at ON order_performance;
CREATE TRIGGER update_order_performance_updated_at
    BEFORE UPDATE ON order_performance
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions for auto-trading tables
GRANT ALL PRIVILEGES ON TABLE auto_trading_settings TO trader;
GRANT ALL PRIVILEGES ON TABLE auto_trading_executions TO trader;
GRANT ALL PRIVILEGES ON TABLE order_performance TO trader;
GRANT ALL PRIVILEGES ON TABLE order_performance_snapshots TO trader;

GRANT USAGE, SELECT ON SEQUENCE auto_trading_settings_id_seq TO trader;
GRANT USAGE, SELECT ON SEQUENCE auto_trading_executions_id_seq TO trader;
GRANT USAGE, SELECT ON SEQUENCE order_performance_id_seq TO trader;
GRANT USAGE, SELECT ON SEQUENCE order_performance_snapshots_id_seq TO trader;

-- Insert default auto-trading settings for existing users
INSERT INTO auto_trading_settings (user_id, is_enabled, preferred_strategies)
SELECT
    id,
    FALSE,
    '["unified"]'
FROM users
ON CONFLICT (user_id) DO NOTHING;

-- ============================================================================
-- DAILY SUGGESTED STOCKS TABLE
-- Stores daily stock picks emitted by the EMA 200/400 1H crossover strategy.
-- ============================================================================

CREATE TABLE IF NOT EXISTS daily_suggested_stocks (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    strategy VARCHAR(50) NOT NULL DEFAULT 'ema_200_400',
    model_type VARCHAR(20) NOT NULL DEFAULT 'crossover',
    stock_name VARCHAR(200),
    current_price DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,

    -- Ranking
    selection_score DOUBLE PRECISION,
    rank INTEGER,

    -- ML/AI Fields (optional, for future use)
    ml_prediction_score DOUBLE PRECISION,
    ml_price_target DOUBLE PRECISION,
    ml_confidence DOUBLE PRECISION,
    ml_risk_score DOUBLE PRECISION,

    -- Technical indicators
    rsi_14 DOUBLE PRECISION,
    macd DOUBLE PRECISION,
    sma_50 DOUBLE PRECISION,
    sma_200 DOUBLE PRECISION,

    -- Fundamental ratios
    pe_ratio DOUBLE PRECISION,
    pb_ratio DOUBLE PRECISION,
    roe DOUBLE PRECISION,
    eps DOUBLE PRECISION,
    beta DOUBLE PRECISION,

    -- Growth metrics
    revenue_growth DOUBLE PRECISION,
    earnings_growth DOUBLE PRECISION,
    operating_margin DOUBLE PRECISION,

    -- Trading signals
    target_price DOUBLE PRECISION,
    stop_loss DOUBLE PRECISION,
    recommendation VARCHAR(20),
    reason TEXT,

    -- Additional metadata
    sector VARCHAR(100),
    market_cap_category VARCHAR(20),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: one record per symbol per date per strategy per model_type
    UNIQUE (date, symbol, strategy, model_type)
);

-- Daily Suggested Stocks Indexes
CREATE INDEX IF NOT EXISTS idx_daily_suggested_date ON daily_suggested_stocks(date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_suggested_symbol ON daily_suggested_stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_suggested_date_strategy ON daily_suggested_stocks(date, strategy);
CREATE INDEX IF NOT EXISTS idx_daily_suggested_ml_score ON daily_suggested_stocks(ml_prediction_score DESC);

COMMENT ON TABLE daily_suggested_stocks IS 'Daily stock picks emitted by the EMA 200/400 1H crossover strategy.';
COMMENT ON COLUMN daily_suggested_stocks.strategy IS 'Strategy name: ema_200_400 for 1H timeframe crossover swing trading strategy.';
COMMENT ON COLUMN daily_suggested_stocks.model_type IS 'Model type: crossover.';

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE daily_suggested_stocks TO trader;
GRANT USAGE, SELECT ON SEQUENCE daily_suggested_stocks_id_seq TO trader;
