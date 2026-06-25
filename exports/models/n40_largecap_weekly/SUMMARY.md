# n40_largecap_weekly (top-3 blend) — 5-year summary

**Window** 2021-06-24 -> 2026-06-24 (5.00y)  ·  engine `tools/models/n40_largecap_weekly/backtest.py` (`n40_top3_blend_reg`)  ·  ran on NUC (`stockexp_nuc_app` → `stockexp_nuc_db`).

Backtest capital $1,000,000. Next-open T+1 fills, $0 commission + 8bps slippage + $1/txn, QQQ 200d regime gate (100% cash when QQQ < 200d SMA). Data: eToro `yfinance` ≥2022-05-18 ratio-spliced to `yfinance_real` backfill (join 2022-05-18, `--extended`).

| Metric | Value |
|--------|------:|
| CAGR | **78.46%** |
| Max drawdown (true daily) | 47.40% |
| Calmar | 1.66 |
| Trades | 148 |
| Win rate | 59.5% |
| Avg win | +17.47% |
| Avg loss | -5.87% |
| Avg hold (bars) | 17.4 |
| Final equity ($1M start) | $18,093,165 |
| Multiple | 18.09× |
| **$5,000 stake →** | **$90,466** |

### $5,000 outcome
$5,000 → **$90,466** over 5.00 years (18.09× / 78.46% CAGR), riding a 47.4% max drawdown.

Full ledger: [`TRADE_LEDGER.md`](TRADE_LEDGER.md) · raw: `trade_ledger.csv`, `transactions.csv`, `equity_curve.csv`, `model_info.json`.
