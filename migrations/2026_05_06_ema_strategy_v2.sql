-- EMA 200/400 Strategy v2: BTC trade rules update
--   - 30% target / 15% partial + trail SL to entry
--   - 3 re-entry cap at retest1 and retest2
--   - EMA400 touch invalidates retest1 path (jump to retest2 watch)
--   - Per-position SL/target tracked in positions_json
--   - 2nd-entry SL = retest2_low (BUY) / retest2_high (SELL)
--
-- Idempotent: ALTER TABLE ... ADD COLUMN IF NOT EXISTS

ALTER TABLE ema_crossover_state
    ADD COLUMN IF NOT EXISTS retest1_attempts         INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retest2_attempts         INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retest1_invalidated      BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS positions_json           JSONB   NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS retest1_pending_cross_ts BIGINT,
    ADD COLUMN IF NOT EXISTS retest2_pending_cross_ts BIGINT;

-- Reset existing in-flight states so old single-entry/single-SL data does not
-- leak into the new per-position model. Crossover detection re-runs on next
-- evaluation pass and re-arms cleanly.
UPDATE ema_crossover_state
   SET trend = 'NONE',
       stage = 0,
       crossover_ts = NULL, crossover_high = NULL, crossover_low = NULL,
       retest1_ts = NULL, retest1_high = NULL, retest1_low = NULL,
       retest2_ts = NULL, retest2_high = NULL, retest2_low = NULL,
       entries_count = 0,
       entry1_price = NULL, entry1_time = NULL,
       entry2_price = NULL, entry2_time = NULL,
       stop_loss = NULL, target_price = NULL,
       position_active = FALSE,
       last_evaluated_ts = NULL,
       retest1_attempts = 0, retest2_attempts = 0,
       retest1_invalidated = FALSE,
       positions_json = '[]'::jsonb,
       retest1_pending_cross_ts = NULL,
       retest2_pending_cross_ts = NULL
 WHERE trend <> 'NONE' OR position_active = TRUE;

-- Wipe v1 audit signals so backtest/UI counts reflect v2 rules only.
TRUNCATE TABLE ema_crossover_signals;

-- Wipe v1 picks so daily_suggested_stocks reflects v2 target/SL rules.
DELETE FROM daily_suggested_stocks WHERE strategy = 'ema_200_400';
