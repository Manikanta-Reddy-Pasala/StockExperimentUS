# "What are we missing?" — exhaustive DD-reduction study

Generated 2026-06-25. Question: can we break the ~50-60% drawdown floor on the two
momentum books while keeping high CAGR? Diagnosis + every lever tried.

## Diagnosis: where the drawdown comes from
The max DD on BOTH models is the **2021-11 → 2022-12 bear** (real market, QQQ −35%),
not a single-name blowup:
- momentum_sp100 (top1): −60.2%, peak 2021-11-04 → trough 2023-02-24
- n40 (top3): −51.6%, peak 2021-11-29 → trough 2022-12-20

**Root cause found:** the regime gate was checked **only at the weekly rebalance**, and
the 200d SMA itself **lags** — the fast Nov-2021→Jan-2022 first leg happens before the
SMA crosses. So the book rides the opening ~25% of the crash no matter what.

## Levers tried (all on 2021-01→2026-06 unless noted)
| Lever | Result | Verdict |
|-------|--------|---------|
| **fast-sma=50** multi-tf gate | top1 80%→60% DD, CAGR 43→63% (10yr) | ✅ big win — LOCKED |
| top-K diversify (5/8/12/20) | DD 50→31% but CAGR 57→18% | ❌ trades return ~1:1 |
| trailing stop (10–25%) | CAGR down, DD flat (whipsaw) | ❌ omitted |
| **daily regime exit** (`--regime-daily`) | n40 Calmar 1.08→1.15; top1 hurt | ⚠️ marginal (n40 only) |
| **crash trigger** (`--dd-exit` 8–15% below 60d high) | n40 Calmar 1.08→1.14, DD 54→51.5; top1 hurt | ⚠️ marginal (n40 only) |

The two NEW exits (`--regime-daily`, `--dd-exit`) were added this session and DO help the
diversified n40 book a little (free — no CAGR cost): **top3 + daily + dd-exit0.08 →
58.8% CAGR / 51.5% DD / Calmar 1.14** vs base 58.6% / 54.4% / 1.08. They HURT the
single-name top1 book (whipsaw), so momentum_sp100 stays fast50-only.

## The honest ceiling (why ~50% DD is structural here)
1. **Long-only high-beta equities.** In a −35% market every momentum name falls together;
   concentration isn't the driver, market beta is.
2. **Signal lag.** Trend/drawdown triggers can't dodge the *first* leg without so much
   whipsaw that CAGR collapses. Faster timing saves days, not the leg.
3. **Cash is already the best risk-off.** Without shorting / an inverse-ETF / bond sleeve,
   you can't do better than flat — and those add their own risk and change the product.

## What actually breaks the floor (and the cost)
| Path | DD | CAGR | Note |
|------|---:|-----:|------|
| Trade only post-2022 regimes (3yr) | 30% | 107% | the 100%/38% target lives here |
| Diversify to top-20 + fast50 (10yr) | 31% | 18% | low-DD, low-return product |
| Add a hedge/short sleeve | lower | lower net | not built; new risk, new complexity |
| **Accept ~50% DD** (n40 top3 improved) | 51% | 59% | best high-CAGR survivable book |

## Bottom line
We weren't missing a free lunch — but we WERE missing daily regime checking + a crash
trigger, now added (small, real n40 gain). The ~50% DD over a 2022-spanning window is a
**structural property of a long-only momentum book**, not a tuning miss. To go materially
lower you must change the product (shorter regime, heavy diversification, or a hedge),
each paying for the lower DD in CAGR.

New engine flags: `--regime-daily`, `--dd-exit <frac>`, `--dd-win <days>` in the n40
wrapper (default off = prior results byte-identical, verified).
