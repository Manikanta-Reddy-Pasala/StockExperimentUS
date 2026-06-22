# S&P 100 Momentum (n40 top-1) (`momentum_sp100`)

**Status:** LIVE (observer)  
WEEKLY rotation, **top-1 single-stock** by BLEND multi-timeframe momentum (21/63/126d) from the top-50-ADV S&P100 pool, QQQ-200d regime gate (risk-off → cash). Shared `pick_n40_holdings` — **live signal byte-identical to this backtest**. top-1 chosen for max CAGR (+121.4% / 39.0% DD / Calmar 3.11; vs top-2 102%/28%/3.65). Single-stock = whole book on one name → higher DD, but rotates (83.8% WR, not one-name-dependent).

**Universe:** Top-50 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 154 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $25,362,069 |
| Total return | +2436.2% |
| **CAGR (annualized)** | **+121.4%** |
| **Max drawdown** | **39.0%** |
| Calmar | 3.11 |
| Trades | 154 · 83.8% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +17.5% | 38.6% |
| 2024 | +279.4% | 27.0% |
| 2025 | +134.3% | 39.0% |
| 2026 | +132.6% | 29.3% |

## Cap mix

mega=154

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
