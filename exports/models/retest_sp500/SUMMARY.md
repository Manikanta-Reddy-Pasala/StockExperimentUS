# S&P 500 Retest Momentum (top-2 blend) (`retest_sp500`)

**Status:** LIVE (observer)  
Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2022-05-24 → 2026-06-18** (~4.07 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ✅ CAGR VERIFIED (see `tools/analysis/verify_cagr.py`)

Evaluated on the common 4-year eToro window (**2022-05-24 → 2026-06-18**) — the model has no trade before eToro data exists. CAGR re-derived from the equity curve; ledger prices match the eToro **source** close on 99%+ of in-range trades (engine faithful → re-run is identical); **0** >40% single-day glitch-jumps.

**❓ 2 trade(s) ($16,002,059 = 73% of PnL) are NOT backed by the committed eToro snapshot** (SNDK, WDC) — the symbol is absent (e.g. GEV) or a leg falls past the snapshot's last date. They need a fresh NUC eToro pull to byte-verify. See `DATA_AUDIT.md`.

_Note: 1 trade(s) on NFLX/BKNG ($-34,874, -0% of PnL) — eToro stores these in a CONSTANT-scaled price unit (NFLX ≈0.10×, BKNG ≈0.04×); relative returns are correct so CAGR is unaffected._

## Results (net of $1/txn, common 4yr eToro window)

| Metric | Value |
|---|---|
| Window | 2022-05-24 → 2026-06-18 (4.07y) |
| Final NAV ($1,000,000 start) | $44,776,308 |
| Total return | +4377.6% |
| CAGR (annualized) | +154.6% |
| Max drawdown | 34.1% |
| Calmar | 4.54 |
| Trades | 66 · 75.8% win |
| ❓ trades needing fresh eToro data | 2 ($16,002,059, 73% of PnL) |

## Year-by-year breakdown

| Year | Return % | Intra-yr DD % |
|---|---:|---:|
| 2022 | -7.7% | 11.0% |
| 2023 | +81.7% | 17.5% |
| 2024 | +71.5% | 30.2% |
| 2025 | +151.8% | 34.1% |
| 2026 | +524.5% | 23.4% |

## Cap mix

large=36, mega=30

---
*Auto-generated from model_info.json + trade_ledger.csv by tools/analysis/refresh_export_docs.py — do not hand-edit.*
