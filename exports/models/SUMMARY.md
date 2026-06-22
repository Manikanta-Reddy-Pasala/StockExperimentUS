# Model Exports — US Observer System (2 models)

Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.
Window 2021-06-01 → 2026-06-18 (~5yr). QQQ 200d SMA regime gate. Net of $1/txn.

> ⚠️ **DATA-INTEGRITY WARNING:** the eToro candle feed has corrupted price levels at the 2025-2026 edge that inflate headline CAGR/NAV. Per-model `DATA_AUDIT.md` lists the flagged trades. Headline numbers below are an UPPER bound until the eToro candles are re-pulled and validated on the NUC. Especially `retest_sp500`, where one corrupted WDC trade alone is ~67% of PnL.

| Model | CAGR | MaxDD | Calmar | Final NAV | Trades | WR | 🛑 corrupt PnL share |
|-------|------|-------|--------|-----------|--------|----|----|
| momentum_sp100 | +72.9% | 27.0% | 2.70 | $9,388,792 | 297 | 80.5% | 34% |
| retest_sp500 | +112.4% | 34.1% | 3.30 | $44,776,308 | 66 | 75.8% | 83% |

Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, `trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.

