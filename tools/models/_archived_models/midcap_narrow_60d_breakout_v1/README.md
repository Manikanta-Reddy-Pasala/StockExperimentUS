# midcap_narrow_60d_breakout V1 (ARCHIVED)

**Status: ARCHIVED 2026-05-17.** Superseded by V2 which excludes Large-caps from the pseudo-midcap pool. Same strategy machinery, better cap filter.

## Original V1 strategy (kept for historical reference)

| Knob | Value |
|---|---|
| Universe pool | Pseudo-midcap (N500 skip-30 ADV, take next 100) |
| Cap filter | None (all caps in pseudo-midcap allowed) |
| Excluded stocks | ANGELONE (corp-action data anomaly) |
| Breakout | 40-day high |
| Volume confirm | ≥ 2× 20-day avg |
| Long-term filter | close > 200-day SMA |
| Position | max_concurrent=1 |
| Exits | TARGET +100% / TRAIL -20% (after +10%) / MAX_HOLD 90d |
| SMA20 exit | DISABLED |
| Costs | 10 bps slippage + ₹20 brokerage + 0.10% STT |

## V1 result (ex-ANGELONE, ₹10L start, 2023-05-15 → 2026-05-15)

| Metric | Value |
|---|---:|
| Final NAV | ₹47.92 L |
| Total return | +379.25% |
| 3-yr CAGR | **+68.60%** |
| Max DD | 17.83% |
| Trades | 12 |
| WR | 75% |
| Calmar | 3.85 |

## Why archived — V2 wins on all metrics

V2 (Exclude Large from pseudo-midcap pool, keep Mid + Small only):
- CAGR: **+86.63%** (+18pp vs V1)
- Max DD: **15.15%** (-2.7pp better)
- Calmar: **5.72** (+1.87 better)
- Same 12 trades

Pseudo-midcap pool accidentally caught Large-caps (JIOFIN, ADANIPORTS, SHRIRAMFIN, ITC at end-2026 ranks 31-130 ADV). Those competed with cleaner mid/small breakouts for capital. V2 drops them.

## Cap-filter sweep (6 variants)

| Variant | CAGR | DD | Calmar |
|---|---:|---:|---:|
| **V2 Exclude Large (Mid+Small) — NEW DEFAULT** | **+86.63%** | **15.15%** | **5.72** |
| V1 Exclude Small (Large+Mid) | +78.26% | 15.49% | 5.05 |
| V0 Baseline ARCHIVED (all caps) | +68.60% | 17.83% | 3.85 |
| V4 Large only | +59.26% | 28.67% | 2.07 |
| V3 Mid only | +38.71% | 20.01% | 1.93 |
| V5 Small only | +9.99% | 48.08% | 0.21 |

## Files

V1 code preserved in git history. To restore:

```bash
git log --all --oneline -- tools/models/midcap_narrow_60d_breakout/backtest.py
git checkout <commit-hash> -- tools/models/midcap_narrow_60d_breakout/
```

Last V1-baseline commit: `0894a941` (before V2 migration).
