# DD reduction + multi-timeframe regime + $5k returns — fast-sma=50 lock

Generated 2026-06-25. Goal stated: **~100% CAGR, max drawdown ≤ 38%.**

## What changed (engine)
- **Multi-timeframe regime confirm** added (`--fast-sma`): go 100% cash unless QQQ
  is above BOTH its 200d AND its 50d SMA. Exits to cash earlier than the 200d gate
  alone. Code: `load_regime(..., fast_sma=50)` in `india_ports_us/backtest.py`,
  wired via `--fast-sma` in the n40 wrapper.
- **Stop loss**: the multi-tf regime gate IS the systematic portfolio stop. Per-name
  trailing stops (`--trail` 10–25%) were swept and **consistently hurt** — whipsaw
  cut CAGR without lowering portfolio DD (DD is market-beta driven, not single-name).
  So trail is left off; the regime gate does the de-risking.

`fast-sma=50` is a robust win in every window — e.g. momentum 10yr Calmar 0.54→1.05,
CAGR 43%→63%, DD 80%→60%.

## Locked configs (both = same engine, weekly, blend signal, QQQ 200d+50d gate)
- **momentum_sp100** = `--top 1 --fast-sma 50` → `n40_top1_blend_reg`
- **n40_largecap_weekly** = `--top 3 --fast-sma 50` → `n40_top3_blend_reg`

All windows end 2026-05-22; backtest cap $1M; `$5k` scales the realized multiple.

## momentum_sp100 (top-1 + fast50)
| Window | CAGR | MaxDD | Calmar | Trades | $5k → |
|--------|-----:|------:|-------:|-------:|------:|
| 3yr  | 193.6% | 41.6% | 4.65 | 34  | $125,896 |
| 4yr  | 136.3% | 41.6% | 3.28 | 38  | $155,279 |
| 5yr  |  79.9% | 60.2% | 1.33 | 76  | $93,761  |
| 10yr |  63.5% | 60.2% | 1.05 | 138 | $671,795 |

## n40_largecap_weekly (top-3 + fast50)
| Window | CAGR | MaxDD | Calmar | Trades | $5k → |
|--------|-----:|------:|-------:|-------:|------:|
| 3yr  | 107.5% | 30.1% | 3.57 | 93  | $44,508  |
| 4yr  |  82.3% | 31.2% | 2.64 | 111 | $55,064  |
| 5yr  |  50.2% | 51.6% | 0.97 | 195 | $38,166  |
| 10yr |  42.2% | 51.6% | 0.82 | 360 | $166,809 |

## Does it hit 100% CAGR / ≤38% DD?
| Window | 100% CAGR + ≤38% DD? | Best available |
|--------|----------------------|----------------|
| **3yr**  | ✅ **YES** | n40 top3+fast50 = **107.5% / 30.1%** (Calmar 3.57). momentum 193.6% / 41.6%. |
| 4yr  | ⚠️ partial | top3+fast50 82% / 31% (DD met, CAGR short) **or** top1+fast50 136% / 41.6% (CAGR met, DD over). Can't get both. |
| 5yr  | ❌ no | ceiling ~80% CAGR @ 60% DD |
| 10yr | ❌ no | ceiling ~63% CAGR @ 60% DD |

**Reality:** 100% CAGR with ≤38% DD is met only on the **3yr** window (n40 top3+fast50
= 107.5%/30.1%). Over 5yr/10yr it's not reachable long-only — those windows contain
the 2022 bear (QQQ −35%); a fully-invested high-beta momentum book draws down with
the market and 100% CAGR sustained for 10yr would be 1,000×. The 3yr/4yr figures are
the live-forward expectation in a favorable regime; the 5/10yr figures are the
through-cycle truth.

To force ≤38% DD on the long windows you must diversify to ~top-20 (DD 31% @ 10yr)
but CAGR collapses to ~18% — a different, low-return product. Not locked.

## Frontier evidence (10yr, swept)
top1 fast0 → 43%/80% · top1 **fast50 → 63%/60%** · top3 fast0 → 45%/54% ·
top5 fast50 → 36%/48% · top12 fast50 → 21%/38% · top20 fast50 → 18%/31%.
Diversification lowers DD but trades CAGR ~1:1 (Calmar flat ~0.6–1.0).

## Sources
`{momentum_sp100,n40_largecap_weekly}_fast50/{3,4,5,10}yr/*/summary.json`.
Baseline (fast=0) retained in `5K_RETURN_SUMMARY.md` + the non-`_fast50` dirs.
