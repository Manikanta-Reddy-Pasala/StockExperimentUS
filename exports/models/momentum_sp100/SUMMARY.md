# S&P 100 Momentum (top-2 blend) (`momentum_sp100`)

**Status:** LIVE (observer)  
Monthly + mid-month rotation, **top-2** equal-weight by BLEND multi-timeframe momentum (21/63/126d), QQQ-200d regime gate (risk-off → cash). Tuned 2026-06: top-3→top-2 concentration + blend signal lifted CAGR 73→118% and cut trades 297→94 (DD flat ~27%); robust pre-mania (92% CAGR / 19% DD on 2022-24).

**Universe:** S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 94 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $24,020,701 |
| Total return | +2302.1% |
| **CAGR (annualized)** | **+118.4%** |
| **Max drawdown** | **27.2%** |
| Calmar | 4.36 |
| Trades | 94 · 83.0% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +78.0% | 19.0% |
| 2024 | +220.5% | 18.0% |
| 2025 | +54.9% | 27.2% |
| 2026 | +169.9% | 21.9% |

## Cap mix

mega=94

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
