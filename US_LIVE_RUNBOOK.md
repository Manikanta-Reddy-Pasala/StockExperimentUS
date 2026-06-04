# US live runbook — IBKR (India-parity stack)

End-to-end flow for the US book on Interactive Brokers, mirroring the India
StockExperiment live loop (data → backtest → signal → execute), but on IBKR + yfinance.

## 0. Prereqs
- Postgres up: `docker compose -f docker-compose.dev.yml up -d database`
- `DATABASE_URL=postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system`
- `pip install ib_async` (requirements.txt is gitignored — install manually)
- For live trading: IB TWS or Gateway running, API enabled. Paper = port 7497, live = 7496.
  Env: `IBKR_HOST` (127.0.0.1), `IBKR_PORT` (7497), `IBKR_CLIENT_ID` (11).

## 1. Pull data (IBKR primary, yfinance fallback — shared core)
```bash
PYTHONPATH=. python tools/pull_yfinance_history.py \
  --universe src/data/symbols/nasdaq100.csv --start 2016-05-24 --end $(date +%F) --source ibkr
PYTHONPATH=. python tools/pull_yfinance_history.py \
  --universe src/data/symbols/leveraged_etfs.csv --start 2016-05-24 --end $(date +%F) --source ibkr
```
Rows tagged `data_source='yfinance'` (what the backtests + executor read).

## 2. Backtest the book (verify CAGR/DD)
```bash
# v2 book sleeves
python tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --mom-mode blend --from 2016-05-24 --to $(date +%F) --out exports/.../mom
python tools/models/leveraged_regime_tqqq/backtest.py --sma 200 --from 2016-05-24 --to $(date +%F) --out exports/.../tqqq
python tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --regime --from 2016-05-24 --to $(date +%F) --out exports/.../brk
# blend (add --lev 2.0 to see the 100%-CAGR leveraged variant)
python tools/analysis/blend_models.py MOM=…/mom/equity_curve.csv TQQQ=…/tqqq/equity_curve.csv BRK=…/brk/equity_curve.csv --weights 0.45,0.15,0.40
```
Unleveraged book: ~53% CAGR / 38% DD (10yr). `--lev 2.0` → ~101% CAGR / 70% DD (margin-call-risky — see HIGH_CAGR_SEARCH.md).

## 3. Generate today's signal + (optionally) execute on IBKR
```bash
# dry-run the whole book (MOM 45% / TQQQ 15% / BRK 40%) — prints the order plan
PYTHONPATH=. python tools/live/us_executor.py --model book --capital 5000

# single sleeve: --model n40|mom|tqqq|brk
# LIVE (places market orders on IBKR; defaults to paper 7497):
PYTHONPATH=. python tools/live/us_executor.py --model book --live
```
Executor reads current IBKR positions + NetLiquidation, diffs vs target, places only the deltas.
Prices fall back to yfinance when TWS is down (dry-run still works offline).

## 4. Schedule (cron)
`data_scheduler.py` runs `generate_us_book_signal` daily 13:45 (DRY-RUN, logs only).
**Live placement is intentionally manual** — flip to `--live` in that job only when you want
auto-trading. Run the scheduler: `python data_scheduler.py`.

## Components (all IBKR; no Fyers)
| Piece | File |
|---|---|
| Shared history core (IBKR→yfinance) | `src/services/data/price_history_provider.py` |
| Market data service | `src/services/data/market_data_service.py` |
| IBKR broker (orders/positions/funds/history) | `src/services/brokers/ibkr/ibkr_service.py` |
| Live executor | `tools/live/us_executor.py` |
| Book doc / results | `exports/backtests/us/3MODEL_BOOK.md`, `HIGH_CAGR_SEARCH.md`, `INDIA_PORTS_IMPROVED.md` |

## Honest notes
- 100% CAGR (5–10yr) exists only WITH ~2× leverage at ~70% DD = liquidation-risk. Survivable book = unleveraged 45/15/40 (~53%/38%).
- BRK live target is a daily Donchian-high approximation (event-driven sleeve can't be snapshotted exactly).
- Backtests carry survivorship (current Nasdaq-100 list) + same-bar-execution optimism; forward returns lower.
