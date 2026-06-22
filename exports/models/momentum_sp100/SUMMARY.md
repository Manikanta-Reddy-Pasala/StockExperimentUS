# S&P 100 Momentum (n40 top-3 blend) (`momentum_sp100`)

**Status:** LIVE (observer)  
Weekly rotation, top-3 by 30d return, blend weights .8/.1/.1 (70/30 conviction), single sleeve. QQQ-200d regime gate (risk-off → cash).

**Universe:** Top-40 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR VERIFIED (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year eToro window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists. CAGR re-derived from the equity curve; ledger prices match the eToro **source** close on 99%+ of in-range trades (engine faithful → re-run is identical); **0** >40% single-day glitch-jumps.

**❓ 76 trade(s) ($1,397,967 = 30% of PnL) are NOT backed by the committed eToro snapshot** (AMD, BA, CRM, FDX, GE, GEV, GS, IBM, INTC, LLY, MU, ORCL, PM, UBER, UNH, WFC) — the symbol is absent (e.g. GEV) or a leg falls past the snapshot's last date. They need a fresh NUC eToro pull to byte-verify. See `DATA_AUDIT.md`.

_Note: 1 trade(s) on NFLX/BKNG ($583, 0% of PnL) — eToro stores these in a CONSTANT-scaled price unit (NFLX ≈0.10×, BKNG ≈0.04×); relative returns are correct so CAGR is unaffected._

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $9,388,792 |
| Total return | +838.9% |
| CAGR (annualized) | +73.4% |
| Max drawdown | 27.0% |
| Calmar | 2.72 |
| Trades | 297 · 80.5% win |
| ❓ trades needing fresh eToro data | 76 ($1,397,967, 30% of PnL) |

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
