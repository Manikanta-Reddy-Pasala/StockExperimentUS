# S&P 500 Retest Momentum (top-2 blend) (`retest_sp500`)

**Status:** LIVE (observer)  
Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 66 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $44,776,308 |
| Total return | +4377.6% |
| **CAGR (annualized)** | **+154.6%** |
| **Max drawdown** | **34.1%** |
| Calmar | 4.54 |
| Trades | 66 · 75.8% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | -7.7% | 11.0% |
| 2023 | +81.7% | 17.5% |
| 2024 | +71.5% | 30.2% |
| 2025 | +151.8% | 34.1% |
| 2026 | +524.5% | 23.4% |

## Cap mix

large=36, mega=30

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
