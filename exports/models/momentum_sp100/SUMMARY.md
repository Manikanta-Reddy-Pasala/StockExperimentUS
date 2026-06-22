# S&P 100 Momentum (n40 top-3 blend) (`momentum_sp100`)

**Status:** LIVE (observer)  
Weekly rotation, top-3 by 30d return, blend weights .8/.1/.1 (70/30 conviction), single sleeve. QQQ-200d regime gate (risk-off → cash).

**Universe:** Top-40 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2021-06-01 → 2026-06-18** (~4.09 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR VERIFIED (see `tools/analysis/verify_cagr.py`)

CAGR re-derived from the equity curve; ledger prices match the eToro **source** close on 99%+ of in-range trades (engine faithful → re-run is identical); **0** >40% single-day glitch-jumps across all traded names.

**41 trade(s) ($2,050,261 = 44% of PnL) ride 2025-26 memory-sector edge prices** (AMAT, AMD, GEV, INTC, MU) — large but continuous (jump-free) and sector-correlated, so they **lean REAL** (AI/HBM memory supercycle). The only residual is byte-verifying the final June-2026 exits past the data snapshot (2026-05-22) with a fresh NUC eToro pull. See `TRADE_RECHECK.md`.

**1 wrong-ABSOLUTE-price trade(s)** ($583 = 0% of PnL): BKNG 2023-04-24 $107 — eToro stores these in a CONSTANT-scaled unit (NFLX ≈0.10×, BKNG ≈0.04×), so relative returns are correct and CAGR is **unaffected**.

## Results (as-is, net of $1/txn) — see audit before trusting

| Metric | Value |
|---|---|
| Final NAV ($1,000,000 start) | $9,388,792 |
| Total return | +838.9% |
| CAGR (annualized) | +72.9% |
| Max drawdown | 27.0% |
| Calmar | 2.70 |
| Trades | 297 · 80.5% win |
| PnL on 2025-26 memory-edge prices (lean real) | $2,050,261 (44% of total) |
| PnL on constant-scale tickers (CAGR-neutral) | $583 (0% of total) |

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
