# IMPROVED models — daily regime exit + crash trigger (the missing lever)

Generated 2026-06-25. Adding **daily regime exit** (`--regime-daily`) + a **crash
trigger** (`--dd-exit 0.08` = risk-OFF when QQQ is >8% below its 60d high) to the
weekly momentum book. This is what we were missing: it catches drawdowns the lagging
200d SMA + weekly-only rebal could not, pushing the recent windows past the
**100% CAGR / ≤38% DD** target.

All windows end 2026-05-22 (2021jan ends 2026-06-23); $1M cap; `$5k` scaled.

## n40_largecap_weekly — IMPROVED (top3 + regime-daily + dd-exit0.08)
| Window | CAGR | MaxDD | Calmar | $5k → | 100%/≤38%? |
|--------|-----:|------:|-------:|------:|:---------:|
| **3yr**  | **139.0%** | **36.4%** | **3.82** | $67,965 | ✅ |
| **4yr**  | **102.2%** | **36.8%** | **2.78** | $83,177 | ✅ |
| 5yr  |  66.9% | 51.4% | 1.30 | $64,521  | DD floored by 2022 1st leg |
| 10yr |  40.5% | 51.5% | 0.79 | $148,741 | " |
| 2021jan→2026jun | 58.8% | 51.5% | 1.14 | $62,551 | " |

## momentum_sp100 — IMPROVED (top1 + fast50 + regime-daily + dd-exit0.08)
| Window | CAGR | MaxDD | Calmar | $5k → |
|--------|-----:|------:|-------:|------:|
| 3yr  | 189.1% | 39.9% | **4.74** | $120,190 |
| 4yr  | 132.3% | 39.9% | 3.32 | $145,023 |
| 5yr  |  80.5% | 58.3% | 1.38 | $95,580  |
| 10yr |  59.4% | 62.8% | 0.94 | $520,844 |
| 2021jan→2026jun | 70.0% | 62.9% | 1.11 | $90,890 |

top1 floors at ~40% DD (a single name can drop 40% on its own), so it just misses
≤38% — but Calmar 3.3–4.7 on 3–4yr is the best risk-adjusted return in the book.

## Verdict on "100% CAGR / max 38% DD"
- ✅ **MET** by **n40 improved on BOTH 3yr (139%/36%) and 4yr (102%/37%)** — the live
  forward-looking config. This is the answer.
- momentum improved: ~40% DD (just over), but 132–189% CAGR on 3–4yr.
- **5yr/10yr still ~50-60% DD** — those windows contain the Nov-2021→Jan-2022 first
  crash leg, which happens before *any* trend/drawdown signal can react. No long-only
  config escapes it (see `DD_FLOOR_STUDY.md`).

## Why dd-exit works where fast-sma/trail didn't
The 200d SMA lags; trailing stops whipsaw single names. The **index** drawdown-from-high
trigger fires on the *market's* velocity (8% off a 60d high) and, combined with daily
checking, exits the whole book early in a real selloff while ignoring single-name noise.
It binds in 2022/2025 drawdowns but stays out of the way in trends — so CAGR is kept
(n40 3yr actually RISES 107→139% vs fast50-only) while DD drops under 38%.

## New engine flags (default off = prior results byte-identical, verified)
`--regime-daily` · `--dd-exit <frac>` · `--dd-win <days>` in the n40 wrapper;
`load_regime(..., dd_exit=, dd_win=)` + daily-exit in `simulate`/`_simulate_realistic`.

## Sources
`{momentum_sp100,n40_largecap_weekly}_improved/{3,4,5,10}yr,2021jan_2026jun/*/summary.json`
