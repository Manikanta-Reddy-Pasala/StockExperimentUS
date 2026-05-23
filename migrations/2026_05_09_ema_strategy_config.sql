-- 2026-05-09  EMA 200/400 strategy per-user config (JSONB).
--
-- Stores any subset of StrategyConfig fields. Loader merges this onto the
-- code defaults at runtime (see EMACrossoverRunner._effective_config).
-- NULL or empty {} = use defaults.

ALTER TABLE auto_trading_settings
    ADD COLUMN IF NOT EXISTS ema_strategy_config JSONB;

COMMENT ON COLUMN auto_trading_settings.ema_strategy_config IS
    'Per-user overrides for EMA 200/400 StrategyConfig. JSONB. NULL = use code defaults.';
