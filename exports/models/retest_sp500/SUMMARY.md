# S&P 500 Retest Momentum (top-2 blend) (`retest_sp500`)

**Status:** LIVE (observer)  
Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 55 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $18,376,752 |
| Total return | +1737.7% |
| **CAGR (annualized)** | **+104.5%** |
| **Max drawdown** | **31.4%** |
| Calmar | 3.33 |
| Trades | 55 · 74.5% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +44.4% | 17.5% |
| 2024 | +71.5% | 30.2% |
| 2025 | +93.4% | 31.4% |
| 2026 | +284.0% | 23.4% |

## Cap mix

mega=27, large=28

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
