# N40 — large-cap weekly momentum (top-3, blend, regime)

Improved US port of the India `n40` archetype. Faithful single-name weekly rotation
bled to 62–80% DD on US; this LOCKED config fixes it by **diversifying to top-3** and
ranking on the **blend** momentum signal (the same alpha as the v2 MOM sleeve), gated
by QQQ's 200d SMA.

## Locked config
| Item | Value |
|---|---|
| Universe | top-40 by 20d ADV ∩ Nasdaq-100 (liquid large caps) |
| Signal | `blend` = avg(21 / 63 / 126-day return) |
| Hold | top-3 equal-weight |
| Rebalance | **weekly** (first trading day of each ISO week) |
| Regime | 100% cash when QQQ < 200d SMA |
| Costs | $0 commission (IBKR Lite) + 8 bps slippage; true daily-MTM DD |

## Results (Nasdaq-100, locked config)
| Window | CAGR | MaxDD | Calmar | Trades | WR |
|---|---:|---:|---:|---:|---:|
| 3yr (2023→2026) | **132.5%** | 38.6% | 3.44 | 285 | 80% |
| 5yr (2021→2026) | 53.1% | 46.8% | 1.13 | 422 | 75% |
| 10yr (2016→2026) | 53.0% | 46.8% | 1.13 | 888 | 77% |

## Run
```bash
PYTHONPATH=. python tools/models/n40_largecap_weekly/backtest.py \
    --from 2023-05-24 --to 2026-05-24 --out exports/backtests/us/n40_largecap_weekly/3yr
```
Emits `equity_curve.csv`, `summary.json`, `trade_ledger.csv`, `transactions.csv`.
Knobs (locked by default): `--top 3 --topadv 40 --signal blend` + regime ON; `--no-regime`,
`--trail %`, `--universe-csv`, `--regime-sym` for research.

## Book role — READ THIS
N40 is a **higher-turnover twin of the v2 MOM sleeve** (both = Nasdaq large-cap blend
momentum). Expect HIGH correlation to MOM, so it lifts CAGR/turnover but does **not**
diversify the 3-model book, and its DD (~47% over 10yr) is *higher* than the book's 38%.
Use it as a MOM alternative (more names, weekly cadence), not as a low-correlation sleeve.
Engine shared with `tools/models/india_ports_us/backtest.py`.
