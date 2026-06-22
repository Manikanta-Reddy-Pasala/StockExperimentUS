# Model Exports — US Observer System (2 models)

Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.
Window 2021-06-01 → 2026-06-18 (~5yr). QQQ 200d SMA regime gate. Net of $1/txn.

> ⚠️ **DATA-INTEGRITY NOTE:** a large share of PnL rides on 2025-26 price moves that are UNVERIFIABLE past the Jan-2026 knowledge cutoff (out-of-band vs pre-2026 norms). They may be real AI/memory-mania moves or corrupted eToro candles — the paths are smooth & self-consistent but the magnitudes are extreme. Per-model `TRADE_RECHECK.md` has every trade's verdict; resolve the ❓ names by re-pulling raw eToro candles on the NUC. `retest_sp500` is **85% UNVERIFIABLE** (WDC + SNDK), so its +112% CAGR is unconfirmed. Only 2 CONFIRMED data errors exist (NFLX 2022, BKNG 2023) and neither inflates returns.

| Model | CAGR | MaxDD | Calmar | Final NAV | Trades | WR | ❓ unverif. PnL | 🛑 confirmed-err PnL |
|-------|------|-------|--------|-----------|--------|----|----|----|
| momentum_sp100 | +72.9% | 27.0% | 2.70 | $9,388,792 | 297 | 80.5% | 44% | 0% |
| retest_sp500 | +112.4% | 34.1% | 3.30 | $44,776,308 | 66 | 75.8% | 85% | -0% |

Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, `TRADE_RECHECK.md`, `trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.

