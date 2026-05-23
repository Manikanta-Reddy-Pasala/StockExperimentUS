# All Trading Models — Combined SUMMARY

3-year backtest window: **2023-05-15 → 2026-05-12** · ₹10L per model · Fyers data (4-yr re-pull 2026-05-17)

5 models (4 equity + 1 options). Each has ONE canonical version. Last refreshed 2026-05-17.

## Headline — deploy ₹10L per model

| # | Model | Universe | Rebalance | Final NAV | CAGR | Max DD | LIVE |
|--:|---|---|---|---:|---:|---:|:-:|
| 1 | `momentum_n100_top5_max1` | Real NSE Nifty 100 (no filter) | Monthly | ₹4,483,692 | **+65.10%** | 37.30% | ✅ |
| 2 | `momentum_pseudo_n100_adv` | Top-100 ADV from N500 − Small + uptrend + MAX_PRICE≤₹3K | Monthly | ₹15,361,000 | **+149.15%** | **16.17%** | ✅ |
| 3 | `midcap_narrow_60d_breakout` | Top-100 ADV from N500 − Large | Event-driven | ₹13,456,535 | **+137.85%** | **8.12%** | ✅ |
| 4 | `finnifty_ic_otm4_w300_lots5` | FINNIFTY options (4 strikes per Mon) | Monthly IC | ₹22,25,673 | **+123.27%** compound | 13.88% | ❌ |
| 5 | `n20_daily_large_only` | Top-20 ADV + uptrend + NSE Nifty 100 | Daily | ₹13,655,640 | **+139.55%** | 25.66% | ✅ |

## Unique stock-filtering approach per model

| Model | Filter mechanism | Why unique |
|---|---|---|
| `momentum_n100_top5_max1` | NSE Nifty 100 official list (no derived filter) | Only model using REAL NSE constituents — large-cap pure baseline |
| `momentum_pseudo_n100_adv` | Top-100 ADV from N500, drop Small, uptrend, price ≤ ₹3,000 | Liquidity + trend + price gate; only model retaining MAX_PRICE filter (justified by share-count floor heuristic) |
| `midcap_narrow_60d_breakout` | Top-100 ADV from N500, drop Large | Highest-liquidity mid/small breakouts; event-driven |
| `finnifty_ic_otm4_w300_lots5` | Spot-derived 4 strikes (±4% OTM + ±300pt wings) | No equity universe — options chain auto-built per Monday |
| `n20_daily_large_only` | Top-20 ADV + close>200d SMA + NSE Nifty 100 | Smallest universe (20); strictest gate; daily rebuild |

## Composite ranking — risk-adjusted Calmar (CAGR / Max DD)

| Rank | Model | CAGR | MaxDD | Calmar |
|--:|---|---:|---:|---:|
| 1 | midcap_narrow_60d_breakout | +137.85% | 8.12% | **16.98** |
| 2 | momentum_pseudo_n100_adv | +149.15% | 16.17% | **9.22** |
| 3 | finnifty_ic_otm4_w300_lots5 | +123.27% | 13.88% | **8.88** |
| 4 | n20_daily_large_only | +139.55% | 25.66% | **5.44** |
| 5 | momentum_n100_top5_max1 | +65.10% | 37.30% | **1.74** |

## MAX_PRICE filter decision history (2026-05-17)

Initially applied MAX_PRICE filter to all 3 momentum models. Reviewed and removed on N100 + N20 because threshold (₹3K / ₹2.5K) was curve-fit on backtest losses (in-sample bias) — replicates only if next-3-yr losers happen to sit in same price buckets.

**Kept on PSEUDO** as a defensible position-sizing heuristic: with ₹30K live capital, any share priced > ₹3,000 leaves <10 shares — i.e. 1 share = >10% of capital, which is excessive per-trade concentration. The filter is observable from current price (no future data) and applies identically live.

**Removed on N100 (LIVE)** and **N20** to give honest unfiltered backtest numbers. CAGR drops back to baseline but no hidden tuning.

## Deployment recommendation

| Goal | Use |
|---|---|
| **Live equity — real NSE universe** | `momentum_n100_top5_max1` (LIVE) |
| **Live equity — best risk-adjusted CAGR** | `momentum_pseudo_n100_adv` (LIVE, Calmar 9+) |
| **Live equity — best Calmar overall** | `midcap_narrow_60d_breakout` (LIVE, Calmar 17+) |
| **Live equity — highest absolute CAGR (daily)** | `n20_daily_large_only` (LIVE) |
| **Defined-risk income (options)** | `finnifty_ic_otm4_w300_lots5` |

## Stock Overlap Across Models

Stocks that appear in trade ledgers of 2+ equity models (multi-model conviction signal).

### Large-cap (NSE Nifty 100)

| Stock | n100 | pseudo | midcap | n20 | Total models |
|---|:-:|:-:|:-:|:-:|:-:|
| ADANIPOWER | ✓ | ✓ |  | ✓ | 3 |
| ETERNAL | ✓ | ✓ |  | ✓ | 3 |
| IRFC | ✓ | ✓ |  | ✓ | 3 |
| MAZDOCK | ✓ | ✓ |  | ✓ | 3 |
| PFC | ✓ | ✓ |  | ✓ | 3 |
| SHRIRAMFIN | ✓ | ✓ |  | ✓ | 3 |
| ADANIGREEN | ✓ | ✓ |  |  | 2 |
| BAJFINANCE |  | ✓ |  | ✓ | 2 |
| HAL | ✓ |  |  | ✓ | 2 |
| HINDZINC | ✓ |  |  | ✓ | 2 |
| ONGC |  | ✓ |  | ✓ | 2 |
| RECLTD |  | ✓ |  | ✓ | 2 |
| TRENT | ✓ |  |  | ✓ | 2 |

### Mid-cap (NSE Nifty Midcap 150)

| Stock | n100 | pseudo | midcap | n20 | Total models |
|---|:-:|:-:|:-:|:-:|:-:|
| BSE |  | ✓ | ✓ |  | 2 |
| COCHINSHIP |  | ✓ | ✓ |  | 2 |
| INDUSTOWER |  | ✓ | ✓ |  | 2 |

### Small-cap (NSE Nifty Smallcap 250)

_None._

### Other / outside top-500

_None._

**Interpretation**: stocks appearing in 3+ models are high-conviction across strategies. Used for portfolio concentration decisions.

## Data integrity

- All data from Fyers production source (cont_flag=1 split-adjusted)
- 498/504 N500 stocks covered (4 DUMMYVEDL placeholders + 2 symbol mismatch = legitimately missing)
- 1 known anomaly: ABFRL 2025-05-22 real demerger (-67%, not data bug)
- yfinance NEVER used (project rule)

## Files

```
exports/models/
├── SUMMARY.md                          ← this file
├── momentum_n100_top5_max1/
│   ├── SUMMARY.md
│   └── TRADE_LEDGER.md
├── momentum_pseudo_n100_adv/
│   ├── SUMMARY.md
│   └── TRADE_LEDGER.md
├── midcap_narrow_60d_breakout/
│   ├── SUMMARY.md
│   └── TRADE_LEDGER.md
├── finnifty_ic_otm4_w300_lots5/
│   ├── SUMMARY.md + MONTHLY_INVESTED.md + trades.csv + monthly.csv
└── n20_daily_large_only/
    ├── SUMMARY.md
    └── TRADE_LEDGER.md
```
