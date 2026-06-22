# S&P 500 Retest Momentum (top-2 blend) (`retest_sp500`)

**Status:** LIVE (observer)  
Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2021-06-01 → 2026-06-18** (~5.05 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ⚠️ DATA-INTEGRITY WARNING — headline metrics are NOT trustworthy

**7 trade(s) use corrupted eToro price levels** (impossible exit prices, e.g. SNDK $1,188, SNDK $1,761, SNDK $237, SNDK $573, SNDK $692, WDC $280, WDC $547). They contribute **$18,131,482 = 83% of all PnL**. Until the underlying eToro candles are re-pulled and validated on the NUC, treat CAGR / Final NAV below as an UPPER bound, not a real result. See `DATA_AUDIT.md`.

## Results (as-is, net of $1/txn) — see audit before trusting

| Metric | Value |
|---|---|
| Final NAV ($1,000,000 start) | $44,776,308 |
| Total return | +4377.6% |
| CAGR (annualized) | +112.4% |
| Max drawdown | 34.1% |
| Calmar | 3.30 |
| Trades | 66 · 75.8% win |
| **PnL from corrupted trades** | **$18,131,482 (83% of total)** |

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
