# momentum_sp100 (top-1 single-stock) — 5-year summary

**Window** 2021-06-24 -> 2026-06-24 (5.00y)  ·  engine `tools/models/n40_largecap_weekly/backtest.py` (`n40_top1_blend_reg`)  ·  ran on NUC (`stockexp_nuc_app` → `stockexp_nuc_db`).

Backtest capital $1,000,000. Next-open T+1 fills, $0 commission + 8bps slippage + $1/txn, QQQ 200d regime gate (100% cash when QQQ < 200d SMA). Data: eToro `yfinance` ≥2022-05-18 ratio-spliced to `yfinance_real` backfill (join 2022-05-18, `--extended`).

| Metric | Value |
|--------|------:|
| CAGR | **93.53%** |
| Max drawdown (true daily) | 56.70% |
| Calmar | 1.65 |
| Trades | 53 |
| Win rate | 58.5% |
| Avg win | +30.26% |
| Avg loss | -10.13% |
| Avg hold (bars) | 15.5 |
| Final equity ($1M start) | $27,135,605 |
| Multiple | 27.14× |
| **$5,000 stake →** | **$135,678** |

### $5,000 outcome
$5,000 → **$135,678** over 5.00 years (27.14× / 93.53% CAGR), riding a 56.7% max drawdown.

Full ledger: [`TRADE_LEDGER.md`](TRADE_LEDGER.md) · raw: `trade_ledger.csv`, `transactions.csv`, `equity_curve.csv`, `model_info.json`.
