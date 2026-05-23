# momentum_n100_top5_max1 — SUMMARY

**Real NSE Nifty 100 monthly momentum rotation (top-1 by 30d ret). No price filter — honest baseline.**

## Backtest window & trade frequency

| Metric | Value |
|---|---|
| Backtest window | **2023-05-15 → 2026-05-12** (~3.00 years) |
| First entry | 2023-05-15 |
| Last exit | 2026-05-04 |
| Total trades | 31 |
| Trades per year | ~10.3 |
| Rebalance | Monthly (1st trading day) |
| Data source | **Fyers (split-adjusted cont_flag=1)** |

## Stock pick logic

1. Universe: src/data/symbols/nifty100.csv (104 NSE Nifty 100 stocks)
2. Rank by 30-day return, pick top-1
3. Rebalance: 1st trading day of month
4. Exit: rotation only — sell when not rank-1

## Headline result

| Metric | Value |
|---|---:|
| Final NAV (cap + open MTM) | **Rs.4,483,692** |
| Total return | **+348.37%** |
| 2.99-yr CAGR | **+65.10%** |
| Max DD | **37.30%** |
| Calmar (CAGR / Max DD) | **1.75** |
| Trades closed | 31 |
| Wins / Losses | 22 / 9 |
| Win rate | 71.0% |
| Live deployment | YES |
| Open position | **ADANIGREEN** qty 3,427 entry Rs.1,290.70 (2026-05-04) last Rs.1,308.00 unrealized +59,287 |

## NSE cap segment breakdown

| Cap | Trades | Wins | Losses | WR | Total PnL Rs. |
|---|---:|---:|---:|---:|---:|
| **Large** | 31 | 22 | 9 | 71% | +3,424,405 |

## Top 5 winners

| Symbol | Entry → Exit | Entry ₹ | Ret % | PnL ₹ |
|---|---|---:|---:|---:|
| ADANIPOWER   | 2026-04-01 → 2026-05-04 | 157.11 | +44.68% | +1,366,248 |
| SHRIRAMFIN   | 2025-11-03 → 2026-01-01 | 796.45 | +28.03% | +699,442 |
| MAZDOCK      | 2023-07-03 → 2023-09-01 | 644.55 | +46.39% | +471,491 |
| IRFC         | 2023-09-01 → 2023-11-01 | 55.75 | +30.85% | +459,188 |
| SOLARINDS    | 2025-04-01 → 2025-05-02 | 11,131.60 | +17.22% | +297,197 |

## Top 5 losses

| Symbol | Entry → Exit | Entry ₹ | Ret % | PnL ₹ |
|---|---|---:|---:|---:|
| BAJAJ-AUTO   | 2024-10-01 → 2024-11-01 | 12,157.45 | -18.77% | -483,678 |
| ENRIN        | 2026-03-02 → 2026-04-01 | 2,972.70 | -12.07% | -419,437 |
| IRFC         | 2024-02-01 → 2024-03-01 | 169.90 | -13.24% | -325,890 |
| HINDZINC     | 2024-11-01 → 2024-12-02 | 558.25 | -9.92% | -208,526 |
| TATACONSUM   | 2025-02-01 → 2025-03-03 | 1,069.85 | -10.84% | -205,231 |

Full trade-by-trade ledger: see [TRADE_LEDGER.md](TRADE_LEDGER.md).
