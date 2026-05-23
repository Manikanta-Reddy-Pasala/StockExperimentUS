-- EMA 200/400 v2 — opt-in tuning params bookkeeping.
-- Adds alert3_locks_count to track number of retest2 candle locks per cycle
-- (used by max_alert3_locks_per_cycle config cap, default 0 = unlimited).

ALTER TABLE ema_crossover_state
    ADD COLUMN IF NOT EXISTS alert3_locks_count INTEGER NOT NULL DEFAULT 0;
