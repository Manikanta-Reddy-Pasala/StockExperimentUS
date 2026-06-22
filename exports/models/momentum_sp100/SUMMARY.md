# S&P 100 Momentum (n40 top-2) (`momentum_sp100`)

**Status:** LIVE (observer)  
WEEKLY rotation, **top-2 equal-weight** by BLEND multi-timeframe momentum (21/63/126d) from the top-50-ADV S&P100 pool, QQQ-200d regime gate (risk-off → cash). Shared `pick_n40_holdings` — **live signal byte-identical to this backtest**. Tuned 2026-06: top-3 .8/.1/.1 → top-2 equal-weight lifted CAGR 81→102% and cut trades 300→196 (DD flat ~28%).

**Universe:** Top-50 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 196 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $17,464,129 |
| Total return | +1646.4% |
| **CAGR (annualized)** | **+102.0%** |
| **Max drawdown** | **27.9%** |
| Calmar | 3.65 |
| Trades | 196 · 84.2% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +60.9% | 21.3% |
| 2024 | +174.4% | 27.9% |
| 2025 | +43.6% | 22.9% |
| 2026 | +172.0% | 21.3% |

## Cap mix

mega=196

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
