-- =====================================================================
-- EMA 200/400 Crossover Strategy migration
-- Date: 2026-04-30
--
-- Replaces the legacy 8-21 EMA + DeMarker + Fibonacci strategy with the
-- EMA 200/400 crossover strategy on a 1H timeframe.
--
-- Steps:
--   1. Create new tables: historical_data_1h, ema_crossover_state,
--      ema_crossover_signals
--   2. Drop unused 8-21 EMA columns from `stocks` and `technical_indicators`
--   3. Purge legacy `daily_suggested_stocks` rows tagged with the old
--      strategy/model_type and reset the strategy default to ema_200_400
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. New tables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historical_data_1h (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(50) NOT NULL,
    timestamp       BIGINT      NOT NULL,
    candle_time     TIMESTAMP   NOT NULL,
    open            DOUBLE PRECISION NOT NULL,
    high            DOUBLE PRECISION NOT NULL,
    low             DOUBLE PRECISION NOT NULL,
    close           DOUBLE PRECISION NOT NULL,
    volume          BIGINT      NOT NULL DEFAULT 0,
    ema_200         DOUBLE PRECISION,
    ema_400         DOUBLE PRECISION,
    data_source     VARCHAR(20) DEFAULT 'fyers',
    created_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_hist1h_symbol_ts UNIQUE (symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS ix_hist1h_symbol_time
    ON historical_data_1h (symbol, candle_time);

CREATE TABLE IF NOT EXISTS ema_crossover_state (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    symbol          VARCHAR(50) NOT NULL,
    trend           VARCHAR(8)  NOT NULL DEFAULT 'NONE',
    stage           INTEGER     NOT NULL DEFAULT 0,

    crossover_ts    BIGINT,
    crossover_high  DOUBLE PRECISION,
    crossover_low   DOUBLE PRECISION,

    retest1_ts      BIGINT,
    retest1_high    DOUBLE PRECISION,
    retest1_low     DOUBLE PRECISION,

    retest2_ts      BIGINT,
    retest2_high    DOUBLE PRECISION,
    retest2_low     DOUBLE PRECISION,

    entries_count   INTEGER DEFAULT 0,
    entry1_price    DOUBLE PRECISION,
    entry1_time     TIMESTAMP,
    entry2_price    DOUBLE PRECISION,
    entry2_time     TIMESTAMP,

    stop_loss       DOUBLE PRECISION,
    target_price    DOUBLE PRECISION,
    position_active BOOLEAN DEFAULT FALSE,

    last_evaluated_ts BIGINT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_ema_state_user_symbol UNIQUE (user_id, symbol)
);
CREATE INDEX IF NOT EXISTS ix_ema_state_symbol_trend
    ON ema_crossover_state (symbol, trend);
CREATE INDEX IF NOT EXISTS ix_ema_state_user
    ON ema_crossover_state (user_id);

CREATE TABLE IF NOT EXISTS ema_crossover_signals (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    symbol          VARCHAR(50) NOT NULL,
    signal_type     VARCHAR(32) NOT NULL,
    trend           VARCHAR(8)  NOT NULL,
    candle_ts       BIGINT      NOT NULL,
    candle_time     TIMESTAMP   NOT NULL,
    price           DOUBLE PRECISION,
    ema_200         DOUBLE PRECISION,
    ema_400         DOUBLE PRECISION,
    note            VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ema_sig_symbol_time
    ON ema_crossover_signals (symbol, candle_time);
CREATE INDEX IF NOT EXISTS ix_ema_sig_user
    ON ema_crossover_signals (user_id);

-- ---------------------------------------------------------------------
-- 2. Drop legacy 8-21 EMA columns
-- ---------------------------------------------------------------------
ALTER TABLE stocks
    DROP COLUMN IF EXISTS ema_8,
    DROP COLUMN IF EXISTS ema_21,
    DROP COLUMN IF EXISTS demarker,
    DROP COLUMN IF EXISTS buy_signal,
    DROP COLUMN IF EXISTS sell_signal,
    DROP COLUMN IF EXISTS indicators_last_updated;

-- (technical_indicators legacy columns are intentionally retained as a
-- backwards-compatible cache; new strategy does not populate them.)

-- ---------------------------------------------------------------------
-- 3. Reset suggested-stocks rows belonging to the old strategy
-- ---------------------------------------------------------------------
DELETE FROM daily_suggested_stocks
 WHERE strategy IN ('ema_8_21', 'ema_8_21_demarker', 'd_momentum')
    OR model_type IN ('traditional', 'd_momentum');

ALTER TABLE daily_suggested_stocks
    ALTER COLUMN strategy SET DEFAULT 'ema_200_400';

COMMIT;
