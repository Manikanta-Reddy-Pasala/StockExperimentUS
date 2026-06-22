# Model Exports — US Observer System (2 models)

Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.
Window 2021-06-01 → 2026-06-18 (~5yr). QQQ 200d SMA regime gate. Net of $1/txn.

> ✅ **CAGR VERIFIED** (`tools/analysis/verify_cagr.py`): both CAGRs re-derived from the equity curve, and the ledger price matches the eToro **source** close on **99%+** of in-range trades — the engine adds no error, so a re-run yields identical numbers. Glitch-jump scan = **0** >40% single-day moves across all 54 traded names (no split-adjust corruption). The two wrong-ABSOLUTE tickers (NFLX ≈0.10×, BKNG ≈0.04×) are **constant-scale** errors → relative returns unchanged → **zero CAGR impact**. The big 2025-26 memory run (WDC/SNDK/MU) is continuous + sector-correlated → leans REAL. Residual: the last ~3 weeks of June-2026 exits sit past this data snapshot (2026-05-22) — byte-verify with a fresh NUC eToro pull. Per-trade detail in `TRADE_RECHECK.md`.

| Model | CAGR | MaxDD | Calmar | Final NAV | Trades | WR | ❓ memory-edge PnL (lean real) | 🛑 scale-only PnL (CAGR-neutral) |
|-------|------|-------|--------|-----------|--------|----|----|----|
| momentum_sp100 | +72.9% | 27.0% | 2.70 | $9,388,792 | 297 | 80.5% | 44% | 0% |
| retest_sp500 | +112.4% | 34.1% | 3.30 | $44,776,308 | 66 | 75.8% | 85% | -0% |

Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, `TRADE_RECHECK.md`, `trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.

