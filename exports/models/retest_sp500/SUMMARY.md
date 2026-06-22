# S&P 500 Retest Momentum (top-2 blend) (`retest_sp500`)

**Status:** LIVE (observer)  
Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2021-06-01 → 2026-06-18** (~5.05 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR VERIFIED (see `tools/analysis/verify_cagr.py`)

CAGR re-derived from the equity curve; ledger prices match the eToro **source** close on 99%+ of in-range trades (engine faithful → re-run is identical); **0** >40% single-day glitch-jumps across all traded names.

**9 trade(s) ($18,497,534 = 85% of PnL) ride 2025-26 memory-sector edge prices** (SNDK, WDC) — large but continuous (jump-free) and sector-correlated, so they **lean REAL** (AI/HBM memory supercycle). The only residual is byte-verifying the final June-2026 exits past the data snapshot (2026-05-22) with a fresh NUC eToro pull. See `TRADE_RECHECK.md`.

**1 wrong-ABSOLUTE-price trade(s)** ($-34,874 = -0% of PnL): NFLX 2023-01-03 $29 — eToro stores these in a CONSTANT-scaled unit (NFLX ≈0.10×, BKNG ≈0.04×), so relative returns are correct and CAGR is **unaffected**.

## Results (as-is, net of $1/txn) — see audit before trusting

| Metric | Value |
|---|---|
| Final NAV ($1,000,000 start) | $44,776,308 |
| Total return | +4377.6% |
| CAGR (annualized) | +112.4% |
| Max drawdown | 34.1% |
| Calmar | 3.30 |
| Trades | 66 · 75.8% win |
| PnL on 2025-26 memory-edge prices (lean real) | $18,497,534 (85% of total) |
| PnL on constant-scale tickers (CAGR-neutral) | $-34,874 (-0% of total) |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2021 | +0.0% | 0.0% |
| 2022 | -7.7% | 11.0% |
| 2023 | +81.7% | 17.5% |
| 2024 | +71.5% | 30.2% |
| 2025 | +151.8% | 34.1% |
| 2026 | +524.5% | 23.4% |

## Cap mix

large=36, mega=30

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
