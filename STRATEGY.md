# EMA 200 / 400 Crossover Strategy — v2 (BTC trade rules)

Production: `77.42.45.12` · Universe: 504 NSE Nifty 500. Default 1H bars
(timeframe customizable to 30min via `historical_data_*` switch).

Spec source: `BTC Trade Rules_V1.1.pdf`.

---

# A. FUNCTIONAL

## What it does

Trend-following. EMA 200 vs EMA 400 crossover sets direction. Two confirmation
alerts then up to 3 re-entries each at retest1 (EMA 200) and retest2 (EMA 400).
Per-position 30% target, 15% partial-book + trail SL → entry. EMA 400 close-
based exit closes everything.

## Stage chain (BUY; SELL mirror)

| # | Stage | Trigger | Action |
|---|-------|---------|--------|
| 0 | Wait | — | Wait for crossover |
| 1 | Trend ID | EMA 200 crosses above EMA 400 | Lock crossover candle |
| 2 | First Alert | bar close > crossover candle high | Watch for retest |
| 3 | Second Alert | bar close < EMA 200 (retest1) | Lock retest1 candle, attempts=0, invalidated=False |
| 3 | Retest1 invalidate | bar low ≤ EMA 400 AND attempts==0 | Skip ENTRY1, jump to Stage 4 |
| 3 | EMA400 touch post-entry | bar low ≤ EMA 400 AND attempts>0 | Per-position SL hits + advance to Stage 4 (ALERT3 fires same bar) |
| 3 | **Entry 1** (cross + sustain) | edge cross of retest1.high → PENDING; entry fires when (now − pending_ts) ≥ sustain_minutes AND close still > level. PENDING_CANCEL if close drops back below before sustain elapses. | **BUY** ×4 max, SL=current EMA400 (dynamic) |
| 4 | Third Alert | bar low ≤ EMA 400 | Lock retest2 candle, attempts=0 |
| 5 | **Entry 2** (cross + sustain) | edge cross of retest2.high → PENDING; entry after sustain_minutes elapsed | **BUY** ×4 max, SL=retest2.low (static) |
| Per-bar | Per-position management | TP @ entry×1.30, partial @ entry×1.15, SL hit | Emits TARGET_HIT / PARTIAL / STOP_HIT |

"Edge break" = price must dip back below the alert level then re-cross to count
as a new attempt. Stops a single break from consuming all 3 re-entries.

## Risk model (per position)

| Item | Rule |
|------|------|
| Target | entry × (1 + 30%) for BUY, entry × (1 − 30%) for SELL |
| Partial | bar.high ≥ entry × 1.15 (BUY) → book 50% qty, trail SL → entry |
| SL (ENTRY1) | intra-bar low ≤ current EMA 400 (dynamic, per-position) |
| SL (ENTRY2) | retest2.low (BUY) / retest2.high (SELL) — static, per-position |
| SL after partial | sl=entry price (static); trail to breakeven |
| Re-entry cap | 4 attempts at retest1, 4 at retest2 (1 initial + 3 re-entries each) |
| Re-arm retest2 | 4th retest1 attempt OR EMA 400 touch → advance to retest2 |
| Pyramid | Stage 5 → 4 after 4th retest2 attempt; new ALERT3 lock re-arms |
| Trend reset | Opposite crossover ONLY (no EMA 400 close-based reset) |

## Backtest

v1 stats below are stale — superseded by v2 rules. Re-run via
`tools/backtests/run_ema_200_400_backtest.py` to regenerate.

## What user sees in UI

- `/strategies` — strategy description, entry/exit rules, settings
- `/suggested_stocks` — daily picks table (Trend, Stage, Score, Target, EMA 400 Stop)
- Modal — recommendation, selection score, target price, stop loss
- CSV export — same fields

---

# B. TECHNICAL

## Code map

| Layer | File |
|-------|------|
| State machine | `src/services/technical/ema_crossover_strategy.py` |
| Hourly orchestrator | `src/services/technical/ema_crossover_runner.py` |
| 1H Fyers fetcher | `src/services/data/historical_1h_service.py` |
| Universe loader | `src/services/data/nifty500_universe.py` |
| Models | `src/models/historical_models.py` |
| Auto-trade consumer | `src/services/trading/auto_trading_service.py` |
| API route | `src/web/routes/suggested_stocks_routes.py` |
| UI | `src/web/templates/{strategies,suggested_stocks}.html`, `v2/{picks,settings}.html` |
| Backtest harness | `tools/backtests/run_ema_200_400_backtest.py` |
| Migrations | `migrations/2026_04_30_{ema_200_400_strategy,clear_trade_deals}.sql`, `migrations/2026_05_06_ema_strategy_v2.sql` |

## Schema

**New tables**

| Table | Purpose |
|-------|---------|
| `historical_data_1h` | 1H OHLCV per symbol/ts + cached EMA 200/400 |
| `ema_crossover_state` | Per-user/symbol state (stage, retest1/2, entries) |
| `ema_crossover_signals` | Append-only audit: CROSSOVER, ALERT1-3, ENTRY1-2, EXIT |

**Dropped:** `ema_8`, `ema_21`, `demarker`, `buy_signal`, `sell_signal`, `signal_quality`, `fib_target_1/2/3`, `ema_8_21_score`.

**Wiped (clear_trade_deals.sql):** `trades`, `orders`, `positions`, `holdings`, `auto_trading_executions`, `order_performance`, `dry_run_*`, `daily_suggested_stocks`. Auth tables untouched.

## Data flow

```
Fyers API (1h interval, 95d chunks)
    ↓
Historical1HService.backfill_universe(user_id=1, days=120)
    ↓
historical_data_1h (Postgres)
    ↓
EMACrossoverRunner.run_for_user(user_id)  ← hourly during 09:15-15:30 IST
    ↓
EMACrossoverStrategy.evaluate()           ← state machine per symbol
    ↓
ema_crossover_signals (audit) + ema_crossover_state (incremental)
    ↓
_promote_to_daily_picks() — only ENTRY1/ENTRY2 → daily_suggested_stocks
    ↓
auto_trading_service._select_top_strategies() — query ema_200_400 picks
    ↓
Fyers order placement (live or paper)
```

## API contract — `daily_suggested_stocks`

```sql
strategy        = 'ema_200_400'
model_type      = 'crossover'
recommendation  IN ('BUY', 'SELL')
selection_score = 100  -- ENTRY1 (high conviction)
                | 90   -- ENTRY2 (pyramid)
target_price    = entry × (1 ± 0.30)                  -- 30% TP
stop_loss       = ENTRY1 → EMA 400, ENTRY2 → retest2.low/high
```

Upsert key: `(date, symbol, strategy, model_type)` — idempotent re-runs.

## State machine — `EMACrossoverState`

| Field | Notes |
|-------|-------|
| `trend` | NONE / BUY / SELL |
| `stage` | 0–5 |
| `crossover_ts/high/low` | Locked at trend flip |
| `retest1_ts/high/low` | Set at ALERT 2 |
| `retest2_ts/high/low` | Set at ALERT 3 (loops) |
| `entries_count` | Total entries this cycle |
| `entry1_price/time`, `entry2_price/time` | First two entries |
| `stop_loss` | EMA 400 at Entry 1 time |
| `target_price` | RR or 5000 pts |
| `position_active` | True between Entry 1 and EXIT |
| `last_evaluated_ts` | Incremental replay marker |

## Config — `StrategyConfig` (v2)

```python
target_pct        = 0.30     # 30% take-profit
partial_pct       = 0.15     # 15% partial-book trigger
partial_qty_frac  = 0.5      # book 50% at partial
re_entry_cap      = 4        # 1 initial + 3 re-entries per alert
sustain_minutes   = 15       # informational on 1H; effective on <=30m
ema_fast_period   = 200
ema_slow_period   = 400
```

## Signals emitted

`CROSSOVER`, `ALERT1`, `ALERT2`, `ALERT2_SKIP` (EMA400 invalidate),
`ALERT3`, `PENDING` (cross detected, sustain check armed),
`PENDING_CANCEL` (close retraced before sustain),
`ENTRY1`, `ENTRY2`, `PARTIAL`, `TARGET_HIT`, `STOP_HIT`, `EXIT`.

ENTRY signals carry per-position `target` and `sl` fields directly.

## State columns added (v2)

| Column | Type | Meaning |
|--------|------|---------|
| `retest1_attempts` | int | ENTRY1 fires this cycle (cap 3) |
| `retest2_attempts` | int | ENTRY2 fires this cycle (cap 3) |
| `retest1_invalidated` | bool | EMA400 touched before ENTRY1 break |
| `retest1_pending_cross_ts` | bigint | Bar timestamp where retest1 cross detected; entry fires after sustain elapsed |
| `retest2_pending_cross_ts` | bigint | Bar timestamp where retest2 cross detected; entry fires after sustain elapsed |
| `positions_json` | jsonb | List of open positions w/ entry/sl/sl_type/target/qty/partial flag |

## Container layout (production VM)

| Container | Role | New code |
|-----------|------|----------|
| `trading_system_app` | Flask UI + API (`:5001`) | ✓ |
| `trading_system_technical_scheduler` | Hourly strategy run | ✓ |
| `trading_system_data_scheduler` | 1H + daily data pipeline | ✓ |
| `trading_system_db` | Postgres 15 | schema migrated |
| `trading_system_dragonfly` | Cache | unchanged |

Volumes: only `./logs`, `./exports`, `./init-scripts` mounted. Code is **baked
into images** — production code changes require `docker compose build`.

## Ops runbook

```bash
# Apply migrations (v1 + v2)
docker cp migrations/2026_04_30_ema_200_400_strategy.sql trading_system_db:/tmp/
docker cp migrations/2026_05_06_ema_strategy_v2.sql trading_system_db:/tmp/
docker exec trading_system_db psql -U trader -d trading_system \
    -f /tmp/2026_04_30_ema_200_400_strategy.sql
docker exec trading_system_db psql -U trader -d trading_system \
    -f /tmp/2026_05_06_ema_strategy_v2.sql

# First-time backfill (120d × 504 symbols)
docker exec -w /app trading_system_app /usr/local/bin/python -c "
from src.services.technical.ema_crossover_runner import get_ema_crossover_runner
print(get_ema_crossover_runner().backfill_universe(user_id=1, days=120, max_symbols=500))"

# Hourly run (manual trigger)
docker exec -w /app trading_system_app /usr/local/bin/python -c "
from src.services.technical.ema_crossover_runner import get_ema_crossover_runner
print(get_ema_crossover_runner().run_for_user(user_id=1, max_symbols=500))"

# Today's picks
docker exec trading_system_db psql -U trader -d trading_system -c "
SELECT symbol, recommendation, target_price, stop_loss, selection_score
  FROM daily_suggested_stocks
 WHERE strategy='ema_200_400' AND date=CURRENT_DATE
 ORDER BY selection_score DESC LIMIT 20;"

# Signal audit
docker exec trading_system_db psql -U trader -d trading_system -c "
SELECT signal_type, COUNT(*) FROM ema_crossover_signals
 WHERE created_at > NOW() - INTERVAL '1 day'
 GROUP BY signal_type ORDER BY 2 DESC;"
```

## Backtest harness

```bash
# Yahoo (offline, no DB, no token)
venv/bin/python tools/backtests/run_ema_200_400_backtest.py --days 720 --source yahoo
venv/bin/python tools/backtests/run_ema_200_400_backtest.py --days 720 --source yahoo \
    --universe nifty500 --out exports/backtests/nifty500_full

# Fyers (production data; container)
docker exec -w /app trading_system_app /usr/local/bin/python \
    /app/tools/backtests/run_ema_200_400_backtest.py \
    --days 720 --source fyers --user-id 1 \
    --universe nifty500 --out /app/exports/backtests_fyers/nifty500_full
```

Per-stock report contains: signal counts, P&L summary, **Strategy Cycles**
section (per-cycle stage table with time/price/EMA/note), closed trades with
exit reasons (TARGET / EXIT_EMA400).

## Performance numbers (per session)

- Fyers Nifty 500 backfill: ~30-40 min (504 × 8 chunks × 0.3s rate)
- Hourly strategy run: ~2-3 min for 504 symbols
- Backtest (Yahoo, 720d, 504 symbols): ~12-15 min
- Backtest (Fyers, 720d, 504 symbols): ~30-45 min

## Known limitations

1. Indices target 5000 pts unreachable on 1H (NIFTY moves 50-300/session)
2. No HTF filter (daily trend ignored)
3. Pyramid Entry 2 can loop unbounded
4. No volume/ATR confirmation
5. Fyers history capped at ~2 years for 1H (Yahoo gives ~3 years)

## Future improvements

| Tweak | Expected impact |
|-------|-----------------|
| Daily HTF filter | WR 31.6% → ~40-45% |
| Disable Entry 2 | Halve loss count, halve compound exposure |
| ATR stop instead of EMA 400 close | Tighter losses |
| Volume filter on retest break | Drop low-conviction entries |
| Tighter index target (200-500 pts) | Indices become tradeable |

---

# C. RESULT FILES

| File | Content |
|------|---------|
| `STRATEGY.md` | This doc |
| `exports/backtests/NIFTY500_RESULTS.md` | Yahoo Nifty 500 aggregate |
| `exports/backtests/FYERS_NIFTY500_RESULTS.md` | Fyers vs Yahoo compare |
| `exports/backtests/INDICES_RESULTS.md` | NIFTY/BANKNIFTY/sectoral |
| `exports/backtests/STAGE_HIT_COUNTS.md` | Funnel + BUY/SELL split |
| `exports/backtests/LOSS_ANALYSIS.md` | Loss source breakdown |
| `exports/backtests/<dir>/<symbol>.md` | Per-stock cycle reports |
