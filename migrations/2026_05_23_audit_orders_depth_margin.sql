-- 2026-05-23  Add depth-snapshot + margin columns to audit_orders.
--
-- Rationale:
--   Live FinNifty IC w150 basket on 2026-05-23 surfaced a real-world
--   liquidity risk: short CE leg (26350) printed a +47% candle on
--   "No volume" on 2026-05-04. Depth-gate (tools/live/option_depth_check)
--   validates per-leg liquidity before placing, but never persists the
--   numbers — we cannot backtrack a bad fill to ask "was the threshold
--   too lax that day?" Now persisted with every audit_orders row.
--
--   Margin column captures Fyers funds-utilized delta around the basket
--   so we can audit margin headroom vs configured capital, instead of
--   only reporting ROI on a hypothetical ₹2L from backtest.
--
-- Columns:
--   bid_at_entry / ask_at_entry     — L1 bid+ask just before placeorder
--   spread_pct_at_entry             — (ask-bid)/mid * 100, percent
--   volume_at_entry                 — day-volume on that contract at signal
--   oi_at_entry                     — open interest on that contract
--   margin_blocked_inr              — Fyers utilized-funds delta for basket
--                                     (denormalized: same value on every leg
--                                      of the same basket; query MAX per
--                                      placed_at-bucket to dedup)

BEGIN;

ALTER TABLE audit_orders
    ADD COLUMN IF NOT EXISTS bid_at_entry NUMERIC(14, 4),
    ADD COLUMN IF NOT EXISTS ask_at_entry NUMERIC(14, 4),
    ADD COLUMN IF NOT EXISTS spread_pct_at_entry NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS volume_at_entry INTEGER,
    ADD COLUMN IF NOT EXISTS oi_at_entry INTEGER,
    ADD COLUMN IF NOT EXISTS margin_blocked_inr NUMERIC(14, 4);

COMMENT ON COLUMN audit_orders.bid_at_entry IS
    'L1 bid price at depth-gate snapshot, just before placeorder.';
COMMENT ON COLUMN audit_orders.ask_at_entry IS
    'L1 ask price at depth-gate snapshot.';
COMMENT ON COLUMN audit_orders.spread_pct_at_entry IS
    '(ask-bid)/mid in percent. Wide spread = thin / illiquid leg.';
COMMENT ON COLUMN audit_orders.volume_at_entry IS
    'Day volume on contract at signal time. Sanity-check vs depth-gate min.';
COMMENT ON COLUMN audit_orders.oi_at_entry IS
    'Open interest at signal time.';
COMMENT ON COLUMN audit_orders.margin_blocked_inr IS
    'Fyers utilized-funds delta around the basket. Same value stamped on '
    'every leg of the basket — use MAX in aggregates to avoid double-count.';

COMMIT;
