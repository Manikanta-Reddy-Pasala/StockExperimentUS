# momentum_pseudo_n100_adv — SUMMARY

**Pseudo-N100 (top-100 ADV from N500 − Smallcap) + uptrend + MAX_PRICE≤₹3,000. Monthly rotation top-1 by 30d ret.**

## Backtest window & trade frequency

| Metric | Value |
|---|---|
| Backtest window | **2023-05-15 → 2026-05-12** (~3.00 years) |
| First entry | 2023-05-15 |
| Last exit | 2026-05-04 |
| Total trades | 27 |
| Trades per year | ~9.0 |
| Rebalance | Monthly (1st trading day) |
| Data source | **Fyers (split-adjusted cont_flag=1)** |

## Stock pick logic

1. Universe: top-100 by 20-day ADV from N500 (yearly-PIT, rebuilt at year start)
2. Drop NSE Smallcap 250 members
3. Uptrend filter: close > 200-day SMA
4. Max-price filter: close ≤ ₹3,000 at entry
5. Rank by 30-day return, pick top-1
6. Rebalance: 1st trading day of month

## Headline result

| Metric | Value |
|---|---:|
| Final NAV (cap + open MTM) | **Rs.15,361,000** |
| Total return | **+1436.10%** |
| 2.99-yr CAGR | **+149.15%** |
| Max DD | **16.17%** |
| Calmar (CAGR / Max DD) | **9.22** |
| Trades closed | 27 |
| Wins / Losses | 24 / 3 |
| Win rate | 88.9% |
| Live deployment | NO |
| Open position | **ADANIGREEN** qty 11,743 entry Rs.1,290.70 (2026-05-04) last Rs.1,308.00 unrealized +203,154 |

## NSE cap segment breakdown

| Cap | Trades | Wins | Losses | WR | Total PnL Rs. |
|---|---:|---:|---:|---:|---:|
| **Large** | 14 | 13 | 1 | 93% | +9,982,487 |
| **Mid** | 13 | 11 | 2 | 85% | +4,175,358 |

## Top 5 winners

| Symbol | Entry → Exit | Entry ₹ | Ret % | PnL ₹ |
|---|---|---:|---:|---:|
| ADANIPOWER   | 2026-04-01 → 2026-05-04 | 157.11 | +44.68% | +4,680,690 |
| SHRIRAMFIN   | 2025-11-03 → 2026-03-02 | 796.45 | +32.15% | +2,497,000 |
| BSE          | 2025-05-02 → 2025-06-02 | 2,102.17 | +28.12% | +1,539,303 |
| PAYTM        | 2025-08-01 → 2025-09-01 | 1,076.40 | +14.81% | +873,193 |
| IDEA         | 2025-10-01 → 2025-11-03 | 8.52 | +11.97% | +830,474 |

## Top 5 losses

| Symbol | Entry → Exit | Entry ₹ | Ret % | PnL ₹ |
|---|---|---:|---:|---:|
| MCX          | 2025-07-01 → 2025-08-01 | 1,812.10 | -16.17% | -1,137,426 |
| COFORGE      | 2024-12-02 → 2025-02-01 | 1,742.14 | -7.28% | -334,302 |
| IRFC         | 2024-02-01 → 2024-03-01 | 169.90 | -13.24% | -305,483 |

Full trade-by-trade ledger: see [TRADE_LEDGER.md](TRADE_LEDGER.md).
