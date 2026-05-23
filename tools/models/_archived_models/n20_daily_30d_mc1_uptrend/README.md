# n20_daily_30d_mc1_uptrend (ARCHIVED)

**Status: ARCHIVED 2026-05-17.** Superseded by `tools/models/n20_daily_v2_large_only/` which adds NSE Nifty 100 filter to halve Max DD.

## Original strategy (kept for historical reference)

| Knob | Value |
|---|---|
| Universe pool | Top-20 by 20-day ADV from Nifty 500 |
| Uptrend filter | close > 200-day SMA |
| Cap filter | None (all caps eligible: Large + Mid + Small) |
| Lookback | 30 days |
| Position | top-1 (max_concurrent=1) |
| Rebalance | Daily |
| Exit | Rotation only (sell when not rank-1) |

## Pick logic

1. Build universe (per day): top-20 N500 stocks by 20-day ADV
2. Apply uptrend filter: keep stocks where close > 200d SMA
3. Rank remaining by 30-day return
4. Pick top-1 for next trading day
5. Rebalance daily — re-rank + rotate if new top-1

## Backtest result (₹10L, 2023-05-15 → 2026-05-12)

| Metric | Value |
|---|---:|
| Final NAV | ~₹1.70 Cr |
| Total return | +1599.57% |
| 3-yr CAGR | +157.27% |
| Max DD (cash NAV) | **50.61%** |
| Calmar | 3.10 |
| Trades | 134 |
| WR | 47.8% |

## Why archived

50% Max DD too high for production. Pure-number filter sweep (15+ variants: hard SL, trail SL, mc>1, vol caps, port-DD halt) all harmed CAGR more than they cut DD. Only NSE Nifty 100 membership filter (categorical) halved DD with acceptable CAGR cost.

**Successor**: `n20_daily_v2_large_only` (+140.78% CAGR / 26.92% DD / Calmar 5.23).

## Files

Original code preserved in git history. To restore:

```bash
git log --all --oneline -- tools/models/n20_daily_30d_mc1_uptrend/
git checkout <commit-hash> -- tools/models/n20_daily_30d_mc1_uptrend/
```

Last live version: commit `e67f0e15` (just before archival).
