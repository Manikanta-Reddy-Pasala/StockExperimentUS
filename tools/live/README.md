# Live Execution Infrastructure

Generic broker + execution scripts. Always-live Fyers order placement.
**No paper trading. No env-gated kill switch.**

## Files

| File | Purpose |
|---|---|
| `fyers_executor.py` | Real Fyers equity order placement (BUY/SELL with limit-walk fallback) |
| `fyers_executor_options.py` | Multi-leg options executor (Iron Condor etc.) |
| `risk_manager.py` | Pre-trade risk check (capital lock, kill-switch) |
| `daily_summary.py` | Read live ledger from DB, emit NAV/P&L |
| `telegram_notify.py` | Optional Telegram notifications for signals/fills |
| `position_reconciler.py` | Match Fyers positions vs ledger every 5 min, auto-mirror drift |
| `broker_charges.py` | SEBI-rate charge computation (brokerage + STT + GST + stamp) |

## Daily flow

All scheduling lives in `scheduler.py` (runs inside `technical_scheduler`
container, APScheduler-backed). Each model registers its own jobs via
`tools/models/<model>/cron.py`. There is no host-side cron wrapper any more.

## Live trading safety

- Every signal that lands during market hours places real Fyers orders.
- `USER_ID` env selects which Fyers session (broker_configurations row).
- Per-trade ₹30k cap + daily-loss kill enforced by `risk_manager.py`.
- Data-quality gate (`data_quality_gate.json`) blocks entries if coverage low.
- `--dry-run` CLI flag still available on executors for manual paper runs.

## Bootstrap (one-time)

1. Build the N100 universe snapshot:
   ```bash
   python tools/models/momentum_n100_top5_max1/build_universe.py \
       --top 100 --out /app/logs/momrot/universes/n100_current.json
   ```
2. Ensure Fyers token is fresh (`tools/refresh_fyers_token.py`).
3. Confirm `model_settings.enabled=true` + `invested_amount` funded.

## Refresh universe

Self-heals every Saturday 06:00 IST via `data_scheduler` (refresh_universe_csvs).
Manual override:
```bash
python tools/models/momentum_n100_top5_max1/build_universe.py \
    --top 100 --out /app/logs/momrot/universes/n100_current.json
```
