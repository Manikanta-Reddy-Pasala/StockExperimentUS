# Model Exports — US Observer System (2 models)

Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.
Window 2021-06-01 → 2026-06-18 (~5yr). QQQ 200d SMA regime gate.

| Model | Strategy | CAGR | MaxDD | Calmar | Trades | WR | Avg PnL% |
|-------|----------|------|-------|--------|--------|----|----------|
| momentum_sp100 | n40 S&P100 top-3, blend momentum, weights .8/.1/.1 (70/30) | 112.4% | 34.9% | 3.22 | 297 | — | — |
| retest_sp500 | India retest engine, S&P500 PIT, top-2, blend | 112.4% | 34.1% | 3.30 | 66 | 75.8% | +78.0% |

Each model folder contains:
- `trade_ledger.csv` — per-trade: symbol, entry_date, entry_px, shares, exit_date, exit_px, pnl, ret_pct, bars_held, **cap_tag** (mega=S&P100 / large=S&P500), pnl_pct
- `equity_curve.csv` — daily equity
- `model_info.json` — strategy, performance, metrics, cap-mix, win-rate, mode

NOTE: momentum trade count (297) is high because the blend-weight live model rebalances the
top-3 weekly; many are small re-weights of the same names. retest holds longer (66 trades, 75.8% WR).
