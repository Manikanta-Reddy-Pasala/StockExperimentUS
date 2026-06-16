# LOCKED — 3-Model Momentum Book v2 (US Nasdaq)

Final book after an exhaustive archetype search (see `US_3MODEL_RESULTS.md`) **plus a
model-based optimization pass**. Two changes lifted CAGR *and* cut drawdown vs the v1
book: MOM now ranks on **multi-timeframe ("blend") momentum**, and BRK runs its
**regime gate ON**. All cash-only, buyable at IBKR (no margin). True daily MTM
drawdown. Costs: $0 commission (IBKR Lite) + 8 bps slippage.

## Universe support (same models, both markets)

The 3 models are universe-agnostic via `--universe-csv` + `--regime-sym`. Run
**per-universe** (do NOT merge — a combined pool makes top-3 momentum pick extreme
high-beta names and blows out DD). Nasdaq is the best book; S&P is fully supported.

| Universe | flags | 3yr CAGR/DD/Calmar | 10yr CAGR/DD/Calmar |
|----------|-------|--------------------|---------------------|
| **Nasdaq-100** (default, best) | `--universe-csv src/data/symbols/nasdaq100.csv --regime-sym QQQ` | 108.7 / 24.9 / 4.36 | 55.2 / 37.7 / 1.46 |
| S&P 500 | `--universe-csv src/data/symbols/sp500.csv --regime-sym SPY` | 87.7 / 30.1 / 2.91 | 37.7 / 38.9 / 0.97 |
| Combined (516) | `--universe-csv src/data/symbols/combined_us.csv --regime-sym SPY` | 79.0 / 30.7 / 2.57 | 35.3 / 45.9 / 0.77 |

Leveraged sleeve: TQQQ (`--lev TQQQ --index QQQ`) for Nasdaq; UPRO (`--lev UPRO
--index SPY`) for S&P. Numbers above use TQQQ. Momentum/trend is strongest on Nasdaq
(tech concentration + dispersion); broadening to S&P or the union dilutes it.

## The three models (locked configs)

| Sleeve | File | Live config | Mechanism |
|--------|------|-------------|-----------|
| **MOM** | `tools/models/momentum_n100_regime_top3/backtest.py` | `--top 3 --regime --mom-mode blend` | Nasdaq-100, rank by avg of 21/63/126-day returns, top-3, monthly; cash when QQQ < 200d SMA |
| **TQQQ** | `tools/models/leveraged_regime_tqqq/backtest.py` | `--sma 200` | hold TQQQ (3× Nasdaq) when QQQ > 200d SMA, else cash |
| **BRK** | `tools/models/breakout_n100/backtest.py` | `--donchian 50 --trail 20 --maxn 5 --regime` | buy 50-day high in uptrend (QQQ>200d), 20% trailing stop, top-5 |

## Additional model — N40 (large-cap weekly momentum)

`tools/models/n40_largecap_weekly/backtest.py` — improved US port of the India `n40`
archetype (top-3 + blend signal + QQQ regime). Standalone sleeve, not in the 45/15/40
blend by default.

| Sleeve | File | Locked config | Mechanism |
|--------|------|---------------|-----------|
| **N40** | `tools/models/n40_largecap_weekly/backtest.py` | `--top 3 --topadv 40 --signal blend` + regime ON | top-40 ADV ∩ Nasdaq-100, rank by avg(21/63/126d) returns, top-3 equal-wt, **weekly**; cash when QQQ<200d |

| Window | CAGR | MaxDD | Calmar | WR |
|--------|-----:|------:|-------:|---:|
| 3yr (2023-2026) | **132.5%** | 38.6% | 3.44 | 80% |
| 5yr (2021-2026) | 53.1% | 46.8% | 1.13 | 75% |
| 10yr (2016-2026) | 53.0% | 46.8% | 1.13 | 77% |

⚠️ **Book role:** N40 is a higher-turnover twin of MOM (both = Nasdaq large-cap blend
momentum) → HIGH correlation to MOM and *higher* DD (~47% vs the book's 38%). Use it as a
MOM alternative (more names, weekly cadence), not as a diversifying sleeve. Exhaustive
port comparison + why emerging/retest don't translate: `INDIA_PORTS_{RESULTS,IMPROVED}.md`.

## Blended book — 45 / 15 / 40 (MOM / TQQQ / BRK)

| Window | CAGR | MaxDD | Calmar |
|--------|-----:|------:|-------:|
| 3yr (2023-2026) | **108.69%** | 24.90% | **4.36** |
| 4yr (2022-2026, incl. bear) | 74.75% | 26.17% | 2.86 |
| 10yr (2016-2026, incl. 2018/2020/2022) | 55.19% | 37.69% | 1.46 |

### v2 (upgraded) vs v1 (original) — better on every metric, both windows
| Book | 3yr CAGR / DD / Calmar | 10yr CAGR / DD / Calmar |
|------|------------------------|-------------------------|
| v1 (raw 30d MOM, BRK no-regime, 50/25/25) | 90.4% / 26.0% / 3.48 | 45.7% / 39.0% / 1.17 |
| **v2 (blend MOM, BRK regime, 45/15/40)** | **108.7% / 24.9% / 4.36** | **55.2% / 37.7% / 1.46** |

### Leveraged variants (the 100%-CAGR question — NOT the default book)
The unleveraged book is the survivable default. For higher CAGR, `blend_models.py` supports
margin (`--lev`) and vol-targeting (`--vol-target`). Full analysis: `HIGH_CAGR_SEARCH.md`.

| Variant | 10yr CAGR / DD / Calmar | reproduce |
|---|---|---|
| **flat 2× book** (max CAGR) | **101.1% / 69.8% / 1.45** | `blend_models.py … --weights 0.45,0.15,0.40 --lev 2.0` |
| vol-targeted 50%/max3 (best Calmar) | 85.4% / 58.2% / 1.47 | `… --vol-target 0.50 --max-lev 3` |
| unleveraged (survivable, default) | 53.4% / 37.7% / 1.42 | `… --weights 0.45,0.15,0.40` |

⚠️ 100% CAGR/10yr needs ~2× leverage at ~70% DD = **margin-call/liquidation territory** (the
backtest ignores forced liquidation + survivorship). A *survivable* 100%/full-cycle does not
exist for US large-cap; 100% only happens in 3yr bull bursts. Leverage at your own risk.

### DD-reduced book — add the diversifier sleeve (lower DD AND higher CAGR)
The regime gate + vol-target only move along the frontier. The structural DD lever is a
near-zero-correlation sleeve: `tools/models/diversifier_sleeve/` (managed futures DBMF/KMLM/CTA
+ commodities + dollar + gold + bonds, top-4 momentum, no regime). Corr to book = 0.09/0.10/0.13.

| Book (2020-2026) | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|
| 3-model 45/15/40 | 58.9% | 36.3% | 1.62 |
| **MOM 0.60 / TQQQ 0.05 / DIV 0.35** | **61.0%** | **28.2%** | **2.17** |
| min-DD MOM 0.15 / BRK 0.15 / DIV 0.70 | 23.5% | 14.8% | 1.59 |

Dropping the MOM-correlated BRK for the uncorrelated DIV cuts DD 36→28% while CAGR rises
59→61% — a real free lunch. Caveat: DBMF/KMLM/CTA exist only from 2020 (~6yr window, no
2008/2018 test). Full analysis: `DD_REDUCTION.md`.

## Per-model results (locked configs, true daily DD)

| Model | 3yr CAGR/DD/Calmar | 4yr CAGR/DD/Calmar | 10yr CAGR/DD/Calmar |
|-------|--------------------|--------------------|---------------------|
| MOM (blend) | 162.9% / 39.2% / 4.16 | 117.7% / 39.2% / 3.00 | 80.9% / 47.0% / 1.72 |
| TQQQ | 67.9% / 37.4% / 1.82 | 56.2% / 37.4% / 1.50 | 44.8% / 54.9% / 0.81 |
| BRK (regime) | 66.3% / 25.5% / 2.60 | 34.1% / 21.2% / 1.61 | 26.9% / 36.7% / 0.73 |

## What the optimization pass found (model-based, not curve-fit)
1. **MOM blend momentum** (avg of 21/63/126-day returns vs raw 30d) — 10yr CAGR 50→81%,
   Calmar 1.08→1.72. Multi-timeframe ranking favors durable trends over volatile pumps.
   The real alpha upgrade.
2. **BRK regime gate ON** — CAGR 56→66% (3yr) *and* DD 48→37% (10yr). Near-free win.
3. **Reweight to 45/15/40** (less TQQQ — it's the highest-DD sleeve at 55%) lowers book DD.
4. **Rejected:** trailing stop + fast (50d) gate on the blend signal *raised* 10yr DD
   (whipsaw); Sharpe-momentum cut DD but killed CAGR. Blend-clean is best.

## Caveats (carry to live)
1. **Survivorship.** MOM/BRK on the *current* Nasdaq-100 → upward bias (~2.5× per the
   point-in-time `pseudo_n100_regime_top3` check). Honest forward ≈ 40-60% CAGR.
2. **Window / bull tilt.** 3yr 109% rides the AI mega-bull; 10yr (real bears) is the
   fair read: ~55% CAGR / ~38% DD.
3. **DD floor.** Concentrated momentum draws down ~38-47% in real bears even with the
   regime gate (2020 COVID gapped through the 200d). The blend upgrade raised
   CAGR/Calmar; it did NOT lower the DD floor.
4. Stock sleeves have 10yr history; only TQQQ has 16yr (33.6% CAGR / 54.9% DD over cycle).

## Artifacts (`exports/backtests/us/`)
- `book_v2/{3yr,4yr,10yr}/{mom,tqqq,brk}/` — summary.json + equity_curve.csv (locked configs)
- `<model>/sweep.json` — parameter sweeps
- `reports/{1_MOM,2_TQQQ,3_BRK}_*.md` — per-model fact sheets
- `US_3MODEL_RESULTS.md` — full archetype search + rejected models + diversifier research

## Reproduce
```bash
docker compose up -d database
export DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system"
# 10yr needs Nasdaq-100 history back to ~2014:
PYTHONPATH=. python3 tools/pull_etoro_history.py --universe src/data/symbols/nasdaq100.csv --start 2014-01-01 --end 2026-05-24
F=2016-05-24; T=2026-05-24; D=exports/backtests/us/book_v2/10yr
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --mom-mode blend --from $F --to $T --out $D/mom
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py --sma 200 --from $F --to $T --out $D/tqqq
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --regime --from $F --to $T --out $D/brk
PYTHONPATH=. python3 tools/analysis/blend_models.py MOM=$D/mom/equity_curve.csv TQQQ=$D/tqqq/equity_curve.csv BRK=$D/brk/equity_curve.csv --weights 0.45,0.15,0.40
```
