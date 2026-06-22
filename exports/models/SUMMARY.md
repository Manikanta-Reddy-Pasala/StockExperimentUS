# Model Exports — US Observer System (2 models)

Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.
**Common window 2022-05-24 → 2026-06-18 (~4yr)** — the span where eToro daily data exists; both models start the SAME day (neither trades before it). QQQ 200d SMA regime gate. Net of $1/txn.

> ✅ **CAGR VERIFIED** (`tools/analysis/verify_cagr.py`): CAGRs re-derived from the equity curve; **100% of in-range trades explained, ZERO anomalies** (price-faithful, return-faithful, or documented blend re-weight); engine adds no error. 0 split-adjust jumps. The ❓ flag marks ONLY trades not backed by the committed eToro snapshot (symbol absent, e.g. GEV, or a leg past 2026-05-22) — these need a fresh NUC eToro pull to byte-verify. NFLX/BKNG store a constant-scaled price unit (return-neutral, zero CAGR impact). Detail: `CAGR_VERIFICATION.txt`.

| Model | CAGR | MaxDD | Calmar | Final NAV | Years | Trades | WR | ❓ needs-data |
|-------|------|-------|--------|-----------|-------|--------|----|----|
| momentum_sp100 | +73.4% | 27.0% | 2.72 | $9,388,792 | 4.07 | 297 | 80.5% | 76 |
| retest_sp500 | +154.6% | 34.1% | 4.54 | $44,776,308 | 4.07 | 66 | 75.8% | 2 |

Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, `TRADE_RECHECK.md`, `trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.

