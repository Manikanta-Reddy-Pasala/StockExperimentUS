-- 2026-05-09  Strategy v1.4 state fields.
-- Adds:
--   retest1_last_close / retest2_last_close — track prev bar close per retest
--     for v1.4 single-bar-edge-cross sustain (replaces PENDING wait timer).
--   retest1_bars_since_lock / retest2_bars_since_lock — count bars since
--     retest candle locked for v1.4 sideways check (4-candle window).

ALTER TABLE ema_crossover_state
    ADD COLUMN IF NOT EXISTS retest1_last_close DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS retest2_last_close DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS retest1_bars_since_lock INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retest2_bars_since_lock INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN ema_crossover_state.retest1_last_close IS
    'Strategy v1.4: prev bar close in Stage 3 (BUY/SELL retest1 watch). Used '
    'to detect single-bar edge-cross-and-close sustain triggers.';
COMMENT ON COLUMN ema_crossover_state.retest1_bars_since_lock IS
    'Strategy v1.4: bars elapsed since retest1 locked. Used by sideways check '
    '(if price breaks retest1.low before retest1.high within N bars).';
