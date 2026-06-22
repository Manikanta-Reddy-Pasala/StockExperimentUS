# S&P 500 Retest Momentum (top-2, realistic fills) (`retest_sp500`)

**Status:** LIVE (observer)  
WEEKLY retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate. Shared `pick_retest_holdings` — live==backtest. REALISTIC US execution: next-open fills + T+1 settlement. **+110.2% CAGR / 34.5% DD** (legacy same-close 104.5%/31.4%). Concentrated on a few big movers by design (WDC-driven).

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn + 8bps slippage, **next-open fills + T+1 settlement** (realistic US execution), PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 31 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $20,546,085 |
| Total return | +1954.6% |
| **CAGR (annualized)** | **+110.2%** |
| **Max drawdown** | **34.5%** |
| Calmar | 3.19 |
| Trades | 31 · 58.1% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +52.7% | 16.9% |
| 2024 | +80.7% | 30.0% |
| 2025 | +107.0% | 34.5% |
| 2026 | +259.7% | 23.3% |

## Cap mix

mega=12, large=19

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
