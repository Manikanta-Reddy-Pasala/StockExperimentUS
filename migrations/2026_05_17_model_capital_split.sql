-- 2026-05-17  Per-model capital split.
--
-- Splits the single `allocated_capital` column into two semantic fields:
--   invested_amount  — cumulative principal in (deposits − withdrawals)
--   current_amount   — latest NAV cache (cash + open MTM)
--
-- Rationale:
--   Today `allocated_capital` is overloaded — used both as cost basis for
--   return % calc AND mutated by deposit/withdraw. After this split:
--     - deposit/withdraw move `invested_amount`
--     - BUY/SELL/MTM update `current_amount`
--     - Return %  = (current_amount - invested_amount) / invested_amount
--
-- Backfill: existing rows had `allocated_capital` only — initialize
-- `current_amount` from invested_amount (effective zero PnL at migration time).

BEGIN;

ALTER TABLE model_settings
    RENAME COLUMN allocated_capital TO invested_amount;

ALTER TABLE model_settings
    ADD COLUMN IF NOT EXISTS current_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;

-- Backfill: any row with current_amount = 0 gets seeded from invested_amount.
-- (Treats migration moment as "fresh deposit, no MTM yet".)
UPDATE model_settings
   SET current_amount = invested_amount
 WHERE current_amount = 0;

COMMENT ON COLUMN model_settings.invested_amount IS
    'Cumulative principal in: increases on deposit, decreases on withdraw. '
    'Used as denominator in return-% calculations. Never moves on buy/sell.';

COMMENT ON COLUMN model_settings.current_amount IS
    'Latest NAV snapshot: cash + open MTM. Maintained by record_buy/sell '
    'and periodic MTM refresh. Used as numerator for return-% calc.';

COMMIT;
