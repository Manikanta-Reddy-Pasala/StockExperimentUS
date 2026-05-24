# momentum_n100_regime_top3 (MOM)

**Mechanism:** trend / relative strength. Rank the real Nasdaq-100 by 30-day return,
hold the top-K equal-weight, rebalance monthly. Adds two drawdown levers over the
parent `momentum_n100_top5_max1`:

- `--top K` — hold top-K (default 3) instead of top-1 → cuts single-name variance.
- `--regime` — go 100% cash on a rebalance day when QQQ closes below its 200-day SMA.

Equity is rebuilt as a **daily mark-to-market curve**, so MaxDD is the true
peak-to-trough (the parent model reported a trade-snapshot DD that understated it).

Costs: $0 commission (IBKR Lite), 8 bps slippage on traded notional (delta shares).
Data: `data_source='yfinance'`, real Nasdaq-100 (`src/data/symbols/nasdaq100.csv`).

## Canonical config

```
--top 3 --regime          # (mid-month check OFF — it adds churn and raises DD)
```

## Results (true daily DD)

| Window | Config | CAGR | MaxDD | Calmar |
|--------|--------|-----:|------:|-------:|
| 3yr (2023-2026) | top3 regime | 114.77% | 29.61% | 3.88 |
| 3yr | top1 no-regime +mid (≈orig) | 185.60% | 57.25% | 3.24 |
| 3yr | top5 regime | 72.50% | 22.85% | 3.17 |
| 4yr (2022-2026) | top3 regime | 86.90% | 29.61% | 2.94 |
| 4yr | top1 no-regime +mid (≈orig) | 98.25% | 57.25% | 1.72 |

The two levers cut DD from 57% (top-1, no gate) to 29.6% (top-3 + regime) while CAGR
only fell ~98% → 87% (4yr). MaxDD is identical across windows → the worst drawdown is
post-2022, not the 2022 bear.

## ⚠ Bias warning

This sits on the **current** Nasdaq-100 (survivorship) and is carried by NVDA-class
single names. The same strategy on the less-biased point-in-time universe
(`pseudo_n100_regime_top3`) makes only ~34-56% CAGR. Treat the 87-115% as an
upper bound; honest forward ≈ 40-60%.

## Run

```bash
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --sweep --from 2023-05-24 --to 2026-05-24
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --out exports/backtests/us/momentum_n100_regime_top3
```
