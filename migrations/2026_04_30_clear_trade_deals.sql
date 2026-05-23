-- =====================================================================
-- Clear trade deals migration
-- Date: 2026-04-30
--
-- Wipes every order/trade/position/holding/auto-trading artifact so the
-- new EMA 200/400 strategy starts from a clean slate.
--
-- Safe-by-default: TRUNCATE ... RESTART IDENTITY CASCADE for transactional
-- tables. Auth tables (users, broker_configurations, webauthn_credentials)
-- are intentionally NOT touched.
-- =====================================================================

-- Truncate tables that exist; ignore those that don't.
DO $$
DECLARE
    tbl TEXT;
    targets TEXT[] := ARRAY[
        'trades', 'orders', 'positions', 'holdings',
        'auto_trading_executions',
        'order_performance', 'order_performances',
        'order_performance_snapshots',
        'dry_run_positions', 'dry_run_portfolios',
        'daily_suggested_stocks'
    ];
BEGIN
    FOREACH tbl IN ARRAY targets LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            EXECUTE format('TRUNCATE TABLE %I RESTART IDENTITY CASCADE', tbl);
            RAISE NOTICE 'Truncated %', tbl;
        ELSE
            RAISE NOTICE 'Skipped (missing) %', tbl;
        END IF;
    END LOOP;
END $$;
