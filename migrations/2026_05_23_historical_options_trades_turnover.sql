-- 2026-05-23  Add num_trades + turnover_lakh to historical_options.
--
-- Why:
--   `volume` (TtlTradgVol = contracts traded) is a single number — a fat
--   day can be 1 huge trade or 100 small ones. Real fillability and
--   realistic-return calculation needs:
--     num_trades     — how many distinct orders matched today
--                      (NSE UDiFF: TtlNbOfTxsExctd; pre-Jul-2024 old
--                      bhavcopy: not provided — left NULL)
--     turnover_lakh  — total ₹ traded today on this contract in lakhs
--                      (NSE OLD bhavcopy r[11] VAL_INLAKH;
--                       NSE UDiFF: TtlTrnvrInRsrL)
--
-- Lets caller estimate "what share of the day's actual trade would my
-- order have been" → realistic slippage.

BEGIN;

ALTER TABLE historical_options
    ADD COLUMN IF NOT EXISTS num_trades INTEGER,
    ADD COLUMN IF NOT EXISTS turnover_lakh NUMERIC(14, 2);

COMMENT ON COLUMN historical_options.num_trades IS
    'NSE UDiFF TtlNbOfTxsExctd — distinct trades matched that day. '
    'NULL for pre-2024-07-07 old bhavcopy format (field not provided).';
COMMENT ON COLUMN historical_options.turnover_lakh IS
    'Total rupees traded that day, in lakhs (1 lakh = 100,000). '
    'Multiply by 100,000 for INR. NULL until re-ingest completes.';

COMMIT;
