# S&P 500 Retest Momentum (top-2, realistic fills) (`retest_sp500`)

**Status:** LIVE (observer)  
WEEKLY retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate. Shared `pick_retest_holdings` — live==backtest. REALISTIC US execution: next-open fills + T+1 settlement. **+82.6% CAGR / 40.5% DD** (corrected after removing phantom eToro weekend candle rows that had booked trades on non-trading days incl. a Sunday; was 110.2% pre-fix). Concentrated on a few big movers by design (WDC-driven).

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn + 8bps slippage, **next-open fills + T+1 settlement** (realistic US execution), PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists, so both models start the same day. Data = the full-universe eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All 19 trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. **No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $11,589,817 |
| Total return | +1059.0% |
| **CAGR (annualized)** | **+82.6%** |
| **Max drawdown** | **40.5%** |
| Calmar | 2.04 |
| Trades | 19 · 68.4% win |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | +0.0% | 0.0% |
| 2023 | +74.3% | 12.8% |
| 2024 | +107.5% | 28.6% |
| 2025 | +57.4% | 40.5% |
| 2026 | +93.8% | 26.3% |

## Cap mix

mega=9, large=10

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
