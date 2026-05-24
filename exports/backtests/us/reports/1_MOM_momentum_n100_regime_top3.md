# Model 1 — MOM · momentum_n100_regime_top3

**Mechanism:** cross-sectional momentum rotation (buy the strongest names).
**File:** `tools/models/momentum_n100_regime_top3/backtest.py`
**Live config (LOCKED v2):** `--top 3 --regime --mom-mode blend`

> v2 upgrade: rank by **blend** momentum = mean of 21/63/126-day returns (vs raw 30d).
> Multi-timeframe favors durable trends → 10yr CAGR 50%→81%, Calmar 1.08→1.72 (DD ~flat).
> Other flags available: `--trail` (per-position stop), `--fast-sma` (faster gate),
> `--mom-mode sharpe` (vol-adjusted, lower DD/lower CAGR). Trailing/fast-gate hurt the
> blend signal over 10yr (whipsaw) — left off in the locked config.

## Rules
- **Universe:** real Nasdaq-100 (`src/data/symbols/nasdaq100.csv`, 101 names).
- **Signal:** rank by 30-day return, monthly (first trading day).
- **Hold:** top-3 equal-weight.
- **Regime gate:** if QQQ closes below its 200-day SMA on a rebalance day → 100% cash.
- **Costs:** $0 commission (IBKR Lite) + 8 bps slippage. Daily mark-to-market DD.

## Results (true daily DD)

| Window | Config | CAGR | MaxDD | Calmar | Trades | WR |
|--------|--------|-----:|------:|-------:|-------:|---:|
| 3yr (2023-2026) | **top3 regime** | **115.12%** | 29.61% | 3.89 | 93 | 65.6% |
| 3yr | top3 no-regime | 140.03% | 32.36% | 4.33 | 101 | 66.3% |
| 3yr | top1 no-regime +mid (≈parent) | 185.60% | 57.25% | 3.24 | 72 | 73.6% |
| 3yr | top5 regime | 72.50% | 22.85% | 3.17 | 158 | 62.0% |
| 4yr (2022-2026) | top3 regime | 86.82% | 29.61% | 2.93 | — | — |
| 4yr | top1 no-regime +mid | 98.25% | 57.25% | 1.72 | — | — |

## Notes
- The two levers (top-3 instead of top-1; QQQ regime gate) cut MaxDD from 57% to
  29.6% while CAGR only fell ~98→87% (4yr). MaxDD is identical 3yr vs 4yr → the worst
  drawdown is post-2022, not the 2022 bear.
- ⚠ **Survivorship-inflated.** Current Nasdaq-100 + NVDA-class single names. The same
  strategy on the point-in-time `pseudo_n100_regime_top3` universe makes only ~34-56%.
  Honest forward ≈ 40-60% CAGR.
- Highest single-model Calmar in the book; the core return engine.
