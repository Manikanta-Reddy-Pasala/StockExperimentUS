# StockExperimentUS — 4-Model Backtest (Nasdaq, yfinance, 2022-05-24 → 2026-05-24)

Data: yfinance daily OHLCV (split/div via Adj Close pulled, raw close used by models).
Universe: top-500 Nasdaq-listed by market cap (`nasdaq500.csv`) + real Nasdaq-100
(`nasdaq100.csv`). 500 symbols, 461,731 rows, span 2022-05-24 → 2026-05-22.
Capital: $1,000,000 nominal. 4.00-year window.

## Results

| Model | Universe | Rebalance | CAGR | MaxDD | Trades | WinRate | Calmar |
|-------|----------|-----------|-----:|------:|-------:|--------:|-------:|
| momentum_n100_top5_max1 | Nasdaq-100 | monthly + day-15 | **+94.65%** | 44.90% | 57 | 54.4% | 2.11 |
| midcap_narrow_60d_breakout | top-100 ADV ex-N100 | event (breakout) | **+51.58%** | 18.82% | 8 | 75.0% | 2.74 |
| momentum_pseudo_n100_adv | top-100 ADV (yearly-PIT) | monthly | **+36.84%** | 48.42% | 32 | 50.0% | 0.76 |
| n20_daily_large_only | top-20 ADV ∩ N100 | daily | **+28.82%** | 71.68% | 159 | 52.2% | 0.40 |

$1M → momentum_n100 $14.36M · midcap $5.28M · pseudo $3.51M · n20 $2.75M.

## India vs US (same models)

| Model | India CAGR (3yr) | India DD | US CAGR (4yr) | US DD |
|-------|-----------------:|---------:|--------------:|------:|
| momentum_n100_top5_max1 | +65.1% | 37.3% | +94.65% | 44.9% |
| momentum_pseudo_n100_adv | +149.15% | 16.17% | +36.84% | 48.42% |
| n20_daily_large_only | +139.55% | 25.66% | +28.82% | 71.68% |
| midcap_narrow_60d_breakout | +86.63% | 15.15% | +51.58% | 18.82% |

US figures materially lower (except momentum_n100) and higher-DD because the
US window **includes the 2022 bear** (India window was 2023-26 bull-only) and
US large-cap momentum is more crowded/correlated than India mid-cap rotation.

## Caveats (read before trusting these numbers)

1. **Survivorship bias.** nasdaq500/nasdaq100 are *current* constituents. Names
   that delisted/dropped out over 2022-26 are absent → upward bias. Same
   limitation as the India pseudo-N100.
2. **midcap lookahead.** The breakout model picks its mid-cap pool from an
   **end-of-data ADV snapshot** (inherited from India). Its top names (NBIS,
   CRWV, RKLB, IREN, COIN, HOOD, ASTS) are 2024-25 high-fliers / recent IPOs —
   the +51% is optimistic. n20 and pseudo use per-period PIT universes (safe);
   momentum_n100 uses the static real index (safe).
3. **Costs are India assumptions.** Slippage 10bps kept; brokerage $20/order
   flat + 0.10% "STT" on sells are India values. US has ~$0 brokerage and no
   STT → these slightly *understate* US net returns, but the effect is tiny at
   $1M cap.
4. **MAX_PRICE filter disabled** for pseudo_n100 (was a ₹3k share-count floor
   for ₹30k live capital — irrelevant at $1M backtest).
5. **Small-cap-250 exclusion disabled** (no US equivalent list built).
6. **Single-position concentration.** All four hold max 1 name → high variance.
   momentum_n100's +94% is largely NVDA/SMCI-era single-name compounding; the
   44.9% DD is the 2022 drawdown.

## Reproduce

```bash
docker compose up -d database
PYTHONPATH=. DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system" \
  python3 tools/pull_yfinance_history.py --universe src/data/symbols/nasdaq500.csv --start 2022-05-24 --end 2026-05-24
for m in momentum_n100_top5_max1 momentum_pseudo_n100_adv n20_daily_large_only midcap_narrow_60d_breakout; do
  PYTHONPATH=. DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system" \
    python3 tools/models/$m/backtest.py
done
```
