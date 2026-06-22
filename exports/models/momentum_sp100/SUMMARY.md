# S&P 100 Momentum (n40 top-3 blend) (`momentum_sp100`)

**Status:** LIVE (observer)  
Weekly rotation, top-3 by 30d return, blend weights .8/.1/.1 (70/30 conviction), single sleeve. QQQ-200d regime gate (risk-off → cash).

**Universe:** Top-40 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2021-06-01 → 2026-06-18** (~4.09 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ⚠️ DATA-INTEGRITY NOTE — verify before trusting headline

**41 trade(s) ($2,050,261 = 44% of PnL) sit on UNVERIFIABLE 2025-26 edge prices** (AMAT, AMD, GEV, INTC, MU) — out-of-band vs pre-2026 norms, on dates past the Jan-2026 knowledge cutoff. Could be real 2025-26 AI/memory mania OR corrupted eToro candles; the price paths are smooth & self-consistent (lean real) but magnitudes are extreme. **Re-pull the raw eToro daily series for these names on the NUC to confirm.** Until then treat CAGR / Final NAV as UNVERIFIED. See `DATA_AUDIT.md` / `TRADE_RECHECK.md`.

**1 CONFIRMED data error(s)** ($583 = 0% of PnL): BKNG 2023-04-24 $107 — price impossible on a date inside the verifiable window.

## Results (as-is, net of $1/txn) — see audit before trusting

| Metric | Value |
|---|---|
| Final NAV ($1,000,000 start) | $9,388,792 |
| Total return | +838.9% |
| CAGR (annualized) | +72.9% |
| Max drawdown | 27.0% |
| Calmar | 2.70 |
| Trades | 297 · 80.5% win |
| PnL on UNVERIFIABLE edge prices | $2,050,261 (44% of total) |
| PnL on CONFIRMED data errors | $583 (0% of total) |

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
