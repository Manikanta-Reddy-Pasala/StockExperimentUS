# n20_daily_large_only

**Daily-rebalance momentum rotation on NSE Nifty 100 large-caps.** Replaces archived `n20_daily_30d_mc1_uptrend` (50% DD version).

## Stock pick logic (plain English)

1. **Universe build (per day)**: top-20 N500 stocks by 20-day ADV
2. **Uptrend filter**: keep only stocks where close > 200-day SMA
3. **Large-cap filter**: keep only stocks in NSE Nifty 100 (`src/data/symbols/nifty100.csv`)
4. **Rank by 30-day return** (highest first)
5. **Pick top-1** from filtered set; if empty, hold cash
6. **Rebalance daily** (re-rank + rotate)

No price filter — honest unfiltered baseline.

## Key knobs

| Knob | Value |
|---|---|
| Universe pool | Top-20 by 20-day ADV from N500 |
| Uptrend filter | close > 200d SMA |
| NSE Nifty 100 filter | Stock must be in NSE Nifty 100 list |
| Lookback | 30 days |
| Position | top-1, max_concurrent=1 |
| Rebalance | Daily |
| Cash policy | Sit in cash if no candidate matches |

## Backtest result (₹10L, 2023-05-15 → 2026-05-12)

| Metric | Value |
|---|---:|
| Final NAV (cap + open MTM) | **₹1,36,55,640** |
| Total return | **+1265.56%** |
| 3-yr CAGR | **+139.55%** |
| Max DD (NAV MTM) | **25.66%** |
| Max DD (rebal cap_after) | 24.74% |
| Calmar (CAGR/NAV-DD) | **5.44** |
| Trades | 138 |
| WR | 44.1% (60W / 76L) |

## Yearly money flow

| Year | Open | Close (cap_after) | ROI |
|---|---:|---:|---:|
| 2023-24 | ₹10,00,000 | ₹49,54,282 | **+395.43%** |
| 2024-25 | ₹49,54,282 | ₹1,03,11,211 | **+108.13%** |
| 2025-26 | ₹1,03,11,211 | ₹1,18,13,452 | **+14.57%** (+ open MTM →₹1.37 Cr) |

## Top 5 winners

| Symbol | Entry → Exit | Entry ₹ | Ret | PnL |
|---|---|---:|---:|---:|
| MAZDOCK | 2024-05-29 → 2024-08-02 | 1,678.68 | +51.77% | +₹33.45L |
| ETERNAL | 2025-07-21 → 2025-08-26 | 271.70 | +17.00% | +₹16.65L |
| HAL | 2024-05-10 → 2024-05-29 | 3,872.90 | +30.44% | +₹15.08L |
| BEL | 2025-05-30 → 2025-07-02 | 384.60 | +11.01% | +₹12.86L |
| BAJFINANCE | 2025-01-28 → 2025-03-19 | 760.66 | +14.79% | +₹12.60L |

## Top 5 losses

| Symbol | Entry → Exit | Entry ₹ | Ret | PnL |
|---|---|---:|---:|---:|
| ADANIPOWER | 2025-09-22 → 2025-09-24 | 170.25 | -15.12% | -₹19.02L |
| TRENT | 2025-07-02 → 2025-07-04 | 6,222.50 | -12.32% | -₹15.97L |
| ETERNAL | 2024-10-17 → 2024-10-18 | 270.55 | -4.84% | -₹4.80L |
| MAZDOCK | 2025-05-05 → 2025-05-06 | 3,099.50 | -4.09% | -₹4.39L |
| BEL | 2026-01-30 → 2026-02-05 | 449.00 | -3.59% | -₹4.36L |

Note: biggest loss (ADANIPOWER) was ₹170 stock, not a high-px name. Removing the curve-fit MAX_PRICE filter restores honest result.

## Files

| File | Purpose |
|---|---|
| `backtest.py` | Standalone reproducer (no price filter) |
| `trade_ledger.json` | 138 trades raw |
| `summary.json` | Authoritative metrics output |

`exports/models/n20_daily_large_only/{SUMMARY.md, TRADE_LEDGER.md}` for full per-trade table with NSE cap + invested ₹.

## Reproduce

```bash
docker exec trading_system_app python tools/models/n20_daily_large_only/backtest.py
```

## Caveats

- 25% MTM DD substantial for single-stock daily rotation.
- 138 trades / 3yr ≈ 46/yr round-trip → 3-5%/yr cost drag. Post-cost CAGR ≈ +134%.
- NSE Nifty 100 list refreshes quarterly (Mar/Sep). Run `tools/refresh_nifty100.py`.
- Slippage not modeled. Real ~10-30 bps drag per round-trip.

## History

- **2026-05-17 (eve)**: Removed curve-fit MAX_PRICE=₹2,500 filter. CAGR 165.97% → 139.55% (honest baseline, no in-sample bias). NAV-DD 24.57% → 25.66%.
- **2026-05-17 (pm)**: Briefly tested MAX_PRICE filter — gave higher CAGR but threshold tuned on backtest losers (TRENT ₹6,222 etc.). Rejected as not formula-defensible.
- Earlier variant `n20_daily_30d_mc1_uptrend` (no Large-cap filter) hit +157% CAGR but 50% Max DD. Tested 15+ pure-number DD-reduction filters — all hurt CAGR more than they helped. Only NSE Nifty 100 categorical filter halved DD with acceptable CAGR cost. Original archived at `tools/models/_archived_models/n20_daily_30d_mc1_uptrend/README.md`.
