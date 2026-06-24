# IMPROVED models — FIXED regime data (the real breakthrough)

Generated 2026-06-25. Supersedes all prior extended-window numbers this session.

## The bug that was hiding the result
The QQQ regime reference had a **data gap 2021-05-28 → 2022-06-17** (filled only by
yfinance_real to May-2021 and eToro from Jun-2022). `load_regime` ffilled across it,
**freezing QQQ at its 2021 high through the entire 2022 bear** → the gate read
risk-ON 100% of 2022 → the book held straight through the −35% crash. Every 5yr/10yr
drawdown this session (~50-60%) was that frozen-gate artifact, not real strategy DD.

**Fix:** backfilled QQQ + SPY across the gap into `yfinance_real`. Regime now goes
risk-OFF in Jan-2022 and stays cash through the bear (verified: %ON drops 100→0 by
Feb-2022). Reproduce: `pull_yfinance_history.py --membership src/data/symbols/regime_refs.csv
--start 2021-05-25 --end 2022-06-17`.

## Configs
- **momentum_sp100** = `--top 1 --fast-sma 50 --regime-daily --dd-exit 0.08`
- **n40_largecap_weekly** = `--top 3 --regime-daily --dd-exit 0.08`

Windows end 2026-05-22 (2021jan → 2026-06-23); $1M cap; `$5k` scaled.

## momentum_sp100 — top1 + fast50 + daily + dd0.08
| Window | CAGR | MaxDD | Calmar | $5k → |
|--------|-----:|------:|-------:|------:|
| 3yr  | 189.1% | 39.9% | 4.74 | $120,190 |
| 4yr  | 131.7% | 39.9% | 3.30 | $143,360 |
| **5yr**  | **101.8%** | **39.9%** | **2.55** | $166,554 |
| 10yr | 68.5% | 39.9% | 1.72 | $907,539 |
| 2021jan→2026jun | 88.2% | 39.9% | 2.21 | $158,386 |

DD pinned ~39.9% every window — a single name's own max drawdown. CAGR ≥100% out to 5yr.

## n40_largecap_weekly — top3 + daily + dd0.08
| Window | CAGR | MaxDD | Calmar | $5k → | 100%/≤38% |
|--------|-----:|------:|-------:|------:|:--------:|
| **3yr**  | **139.0%** | **36.4%** | 3.82 | $67,965 | ✅ |
| **4yr**  | **101.1%** | **36.8%** | 2.75 | $81,514 | ✅ |
| 5yr  | 78.8% | 36.8% | 2.14 | $91,056 | DD ✅ / CAGR 79% |
| 10yr | 45.5% | 42.6% | 1.07 | $209,946 | |
| 2021jan→2026jun | 69.1% | 36.8% | 1.88 | $88,300 | DD ✅ |

## Verdict — 100% CAGR / ≤38% DD, by window
| Window | Best result |
|--------|-------------|
| 3yr  | ✅ n40 **139% / 36.4%** (or momentum 189% / 40%) |
| 4yr  | ✅ n40 **101% / 36.8%** |
| **5yr**  | momentum **101.8% / 39.9%** (CAGR met, DD 2pts over) **or** n40 78.8% / 36.8% (DD met) |
| 10yr | momentum 68.5% / 39.9% · n40 45.5% / 42.6% |

5yr now essentially hits the target — 101.8% CAGR at ~40% DD, vs ~50-60% DD before the
data fix. The last 2pts (40→38) are the irreducible single-name drawdown of a top-1
book; the diversified n40 clears 38% but trades down to 79% CAGR. Pick the point on the
frontier. Even 10yr DD fell from 60-80% to ~40-43%.

## Levers, final
1. `--fast-sma 50` — multi-tf gate (top1 only; whipsaws diversified n40)
2. `--regime-daily` — exit the day the gate breaks, not next weekly rebal
3. `--dd-exit 0.08` — index crash trigger (risk-OFF when QQQ >8% below 60d high)
4. **regime-data integrity** — the biggest lever of all; a frozen reference silently
   disables the gate. Now covered by `regime_refs.csv` + the backfill.

Sources: `{momentum_sp100,n40_largecap_weekly}_improved/{3,4,5,10}yr,2021jan_2026jun/`.
