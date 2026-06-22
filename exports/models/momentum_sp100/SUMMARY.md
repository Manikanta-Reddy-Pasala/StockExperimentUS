# S&P 100 Momentum (n40 top-1, realistic fills) (`momentum_sp100`)

**Status:** LIVE (observer)  
WEEKLY rotation, **top-1 single-stock** by BLEND multi-timeframe momentum (21/63/126d), QQQ-200d regime gate. Shared `pick_n40_holdings` — **live signal byte-identical to backtest**. REALISTIC US execution: decide on close, fill at NEXT OPEN, **T+1 settlement** (buy waits one bar after sell — no instant same-day rotation). On realistic fills: **+118.8% CAGR / 43.7% DD** (legacy same-close was 121%/39%). Single-stock = whole book on one name → high DD.

**Universe:** Top-50 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn + 8bps slippage, **next-open fills + T+1 settlement** (realistic US execution), PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 28 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $24,197,428 |
| Total return | +2319.7% |
| **CAGR (annualized)** | **+118.8%** |
| **Max drawdown** | **43.7%** |
| Calmar | 2.72 |
| Trades | 28 · 67.9% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +27.8% | 35.6% |
| 2024 | +231.3% | 28.6% |
| 2025 | +135.0% | 43.7% |
| 2026 | +133.0% | 31.2% |

## Cap mix

mega=28

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
