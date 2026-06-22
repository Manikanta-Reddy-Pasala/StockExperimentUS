# Model Exports — US Observer System (2 models)

Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.
**Common window 2022-05-24 → 2026-06-18 (~4yr)** — the span where eToro daily data exists; both models start the SAME day (neither trades before it). QQQ 200d SMA regime gate. Net of $1/txn.

> ✅ **CLEAN — NO FLAGS** (`tools/analysis/verify_cagr.py`): data is the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **Every trade (297 + 66) is price-faithful to the eToro source** — 100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps. CAGR re-derived from the equity curve; DD is daily peak-to-trough. NFLX/BKNG are quoted in a constant-scaled unit (return-neutral). Detail: `CAGR_VERIFICATION.txt`.

| Model | CAGR | MaxDD | Calmar | Final NAV | Years | Trades | WR |
|-------|------|-------|--------|-----------|-------|--------|----|
| momentum_sp100 | +118.4% | 27.2% | 4.36 | $24,020,701 | 4.07 | 94 | 83.0% |
| retest_sp500 | +154.6% | 34.1% | 4.54 | $44,776,308 | 4.07 | 66 | 75.8% |

Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, `TRADE_RECHECK.md`, `trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.

