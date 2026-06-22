# S&P 100 Momentum (n40 top-3 blend) (`momentum_sp100`)

**Status:** LIVE (observer)  
Weekly rotation, top-3 by 30d return, blend weights .8/.1/.1 (70/30 conviction), single sleeve. QQQ-200d regime gate (risk-off → cash).

**Universe:** Top-40 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate

Backtest window: **2021-06-01 → 2026-06-18** (~4.09 years; $1,000,000 start). OBSERVER (cash, no leverage), net of $1/txn, next-close fills, PIT survivorship-corrected, **eToro** daily data. QQQ 200d regime gate.

## ⚠️ DATA-INTEGRITY WARNING — headline metrics are NOT trustworthy

**19 trade(s) use corrupted eToro price levels** (impossible exit prices, e.g. INTC $110, INTC $120, INTC $126, INTC $129, MU $1,038, MU $1,081, MU $345, MU $366, MU $388, MU $389, MU $397, MU $404, MU $411, MU $420, MU $439, MU $445, MU $447, MU $579, MU $793). They contribute **$1,585,696 = 34% of all PnL**. Until the underlying eToro candles are re-pulled and validated on the NUC, treat CAGR / Final NAV below as an UPPER bound, not a real result. See `DATA_AUDIT.md`.

## Results (as-is, net of $1/txn) — see audit before trusting

| Metric | Value |
|---|---|
| Final NAV ($1,000,000 start) | $9,388,792 |
| Total return | +838.9% |
| CAGR (annualized) | +72.9% |
| Max drawdown | 27.0% |
| Calmar | 2.70 |
| Trades | 297 · 80.5% win |
| **PnL from corrupted trades** | **$1,585,696 (34% of total)** |

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
