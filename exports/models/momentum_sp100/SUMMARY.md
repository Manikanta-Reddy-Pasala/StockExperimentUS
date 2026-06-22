# S&P 100 Momentum (n40 top-3 blend) (`momentum_sp100`)

**Status:** LIVE (observer)  
Weekly rotation, top-3 by 30d return, blend weights .8/.1/.1 (70/30 conviction), single sleeve. QQQ-200d regime gate (risk-off → cash).

**Universe:** Top-40 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 297 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $9,388,792 |
| Total return | +838.9% |
| **CAGR (annualized)** | **+73.4%** |
| **Max drawdown** | **27.0%** |
| Calmar | 2.72 |
| Trades | 297 · 80.5% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +46.9% | 13.5% |
| 2024 | +92.3% | 27.0% |
| 2025 | +40.1% | 24.8% |
| 2026 | +141.5% | 17.6% |

## Cap mix

mega=297

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
