-- 15-minute OHLCV table for the EMA 200/400 sustain check.
-- Trend detection (EMA200/400, crossover, retests) still runs on 1H candles.
-- Only the post-cross sustain confirmation uses 15m bars so ENTRY fires
-- ~15m after a level break instead of waiting for the next 1H close (60m).

CREATE TABLE IF NOT EXISTS historical_data_15m (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(50) NOT NULL,
    timestamp    BIGINT      NOT NULL,
    candle_time  TIMESTAMP   NOT NULL,
    open         DOUBLE PRECISION NOT NULL,
    high         DOUBLE PRECISION NOT NULL,
    low          DOUBLE PRECISION NOT NULL,
    close        DOUBLE PRECISION NOT NULL,
    volume       BIGINT      NOT NULL DEFAULT 0,
    data_source  VARCHAR(20) DEFAULT 'fyers',
    created_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_hist15m_symbol_ts UNIQUE (symbol, timestamp)
);

CREATE INDEX IF NOT EXISTS ix_hist15m_symbol      ON historical_data_15m (symbol);
CREATE INDEX IF NOT EXISTS ix_hist15m_time        ON historical_data_15m (candle_time);
CREATE INDEX IF NOT EXISTS ix_hist15m_symbol_time ON historical_data_15m (symbol, candle_time);
