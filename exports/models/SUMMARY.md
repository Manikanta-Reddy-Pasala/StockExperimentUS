# Model Exports — 5-Year Backtest ($5,000 per model)

Generated 2026-06-25. Fresh re-run on **NUC** (`stockexp_nuc_app` → `stockexp_nuc_db`). Window **2021-06-24 -> 2026-06-24 (5.00y)** — true last-5-years.

Shared engine `tools/models/n40_largecap_weekly/backtest.py`: weekly top-K, blend signal `avg(21/63/126d ret)`, QQQ 200d regime gate, next-open T+1 fills, $0 commission + 8bps slippage + $1/txn. Data: eToro `yfinance` ≥2022-05-18 ratio-spliced to `yfinance_real` backfill (join 2022-05-18, `--extended`). Backtest capital $1,000,000; **$5k** column scales the realized multiple to a $5,000 stake.

- **momentum_sp100** = engine `--top 1` (single-stock)
- **n40_largecap_weekly** = engine `--top 3`

## Results — $5,000 invested per model

| Model | CAGR | MaxDD | Calmar | Trades | WR | Multiple | **$5k →** |
|-------|-----:|------:|-------:|-------:|----:|---------:|----------:|
| momentum_sp100 | 93.53% | 56.70% | 1.65 | 53 | 58.5% | 27.14× | **$135,678** |
| n40_largecap_weekly | 78.46% | 47.40% | 1.66 | 148 | 59.5% | 18.09× | **$90,466** |
| **TOTAL ($10k, both)** | | | | | | | **$226,144** |

## Read

- **momentum_sp100 (top-1)**: highest CAGR (93.5%), $5k → **$135,678** — rides a 57% drawdown (single-stock concentration).
- **n40_largecap_weekly (top-3)**: lower CAGR (78.5%), $5k → **$90,466**, tamer 47% drawdown — the investable choice.
- **$10k split evenly** ($5k each) → **$226,144** over 5 years.

## Caveats

- Gross backtest: no taxes; 8bps + $1/txn slippage. Multiples on a $1M book — a real $5k account fills differently.
- High CAGR leans on a few monster trades — see each `TRADE_LEDGER.md` top-winners.
- 50%+ drawdowns are structural for concentrated momentum; size accordingly.

## Per-model detail

Each folder: `SUMMARY.md`, `TRADE_LEDGER.md`, `trade_ledger.csv`, `transactions.csv`, `equity_curve.csv`, `model_info.json`.
- [`momentum_sp100/SUMMARY.md`](momentum_sp100/SUMMARY.md) · [`TRADE_LEDGER.md`](momentum_sp100/TRADE_LEDGER.md)
- [`n40_largecap_weekly/SUMMARY.md`](n40_largecap_weekly/SUMMARY.md) · [`TRADE_LEDGER.md`](n40_largecap_weekly/TRADE_LEDGER.md)
