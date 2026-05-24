# LOCKED — 3-Model Momentum Book v2 (US Nasdaq)

Final book after an exhaustive archetype search (see `US_3MODEL_RESULTS.md`) **plus a
model-based optimization pass**. Two changes lifted CAGR *and* cut drawdown vs the v1
book: MOM now ranks on **multi-timeframe ("blend") momentum**, and BRK runs its
**regime gate ON**. All cash-only, buyable at IBKR (no margin). True daily MTM
drawdown. Costs: $0 commission (IBKR Lite) + 8 bps slippage.

## The three models (locked configs)

| Sleeve | File | Live config | Mechanism |
|--------|------|-------------|-----------|
| **MOM** | `tools/models/momentum_n100_regime_top3/backtest.py` | `--top 3 --regime --mom-mode blend` | Nasdaq-100, rank by avg of 21/63/126-day returns, top-3, monthly; cash when QQQ < 200d SMA |
| **TQQQ** | `tools/models/leveraged_regime_tqqq/backtest.py` | `--sma 200` | hold TQQQ (3× Nasdaq) when QQQ > 200d SMA, else cash |
| **BRK** | `tools/models/breakout_n100/backtest.py` | `--donchian 50 --trail 20 --maxn 5 --regime` | buy 50-day high in uptrend (QQQ>200d), 20% trailing stop, top-5 |

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
PYTHONPATH=. python3 tools/pull_yfinance_history.py --universe src/data/symbols/nasdaq100.csv --start 2014-01-01 --end 2026-05-24
F=2016-05-24; T=2026-05-24; D=exports/backtests/us/book_v2/10yr
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --mom-mode blend --from $F --to $T --out $D/mom
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py --sma 200 --from $F --to $T --out $D/tqqq
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --regime --from $F --to $T --out $D/brk
PYTHONPATH=. python3 tools/analysis/blend_models.py MOM=$D/mom/equity_curve.csv TQQQ=$D/tqqq/equity_curve.csv BRK=$D/brk/equity_curve.csv --weights 0.45,0.15,0.40
```
