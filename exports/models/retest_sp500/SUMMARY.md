# S&P 500 Retest Momentum (top-2 blend) (`retest_sp500`)

**Status:** LIVE (observer)  
Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.

**Universe:** S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate

Backtest window: **2021-06-01 → 2026-06-18** (~5.05 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ⚠️ DATA-INTEGRITY NOTE — verify before trusting headline

**9 trade(s) ($18,497,534 = 85% of PnL) sit on UNVERIFIABLE 2025-26 edge prices** (SNDK, WDC) — out-of-band vs pre-2026 norms, on dates past the Jan-2026 knowledge cutoff. Could be real 2025-26 AI/memory mania OR corrupted eToro candles; the price paths are smooth & self-consistent (lean real) but magnitudes are extreme. **Re-pull the raw eToro daily series for these names on the NUC to confirm.** Until then treat CAGR / Final NAV as UNVERIFIED. See `DATA_AUDIT.md` / `TRADE_RECHECK.md`.

**1 CONFIRMED data error(s)** ($-34,874 = -0% of PnL): NFLX 2023-01-03 $29 — price impossible on a date inside the verifiable window.

## Results (as-is, net of $1/txn) — see audit before trusting

| Metric | Value |
|---|---|
| Final NAV ($1,000,000 start) | $44,776,308 |
| Total return | +4377.6% |
| CAGR (annualized) | +112.4% |
| Max drawdown | 34.1% |
| Calmar | 3.30 |
| Trades | 66 · 75.8% win |
| PnL on UNVERIFIABLE edge prices | $18,497,534 (85% of total) |
| PnL on CONFIRMED data errors | $-34,874 (-0% of total) |

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
