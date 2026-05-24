# LOCKED — 3-Model Momentum Book (US Nasdaq)

Final book after an exhaustive search of ~12 US strategy archetypes (momentum,
breakout, VCP/Minervini, leveraged-trend, mean-reversion, factor rotation, sector &
cross-asset rotation, overnight/intraday, seasonality, gold, crypto — see
`US_3MODEL_RESULTS.md`). Conclusion: **systematic US large-cap CAGR comes only from
concentrated momentum/trend.** These three are the keepers. All cash-only, buyable at
IBKR (no margin). True daily mark-to-market drawdown. Costs: $0 commission (IBKR Lite)
+ 8 bps slippage.

## The three models

| Sleeve | File | Live config | Mechanism |
|--------|------|-------------|-----------|
| **MOM** | `tools/models/momentum_n100_regime_top3/backtest.py` | `--top 3 --regime` | rank Nasdaq-100 by 30d return, hold top-3, monthly; cash when QQQ < 200d SMA |
| **TQQQ** | `tools/models/leveraged_regime_tqqq/backtest.py` | `--sma 200` | hold TQQQ (3× Nasdaq) when QQQ > 200d SMA, else cash |
| **BRK** | `tools/models/breakout_n100/backtest.py` | `--donchian 50 --trail 20 --maxn 5` | buy 50-day high in uptrend, ride with 20% trailing stop, top-5 |

## Per-model results (true daily DD)

| Model | 3yr CAGR | 3yr DD | 3yr Calmar | 4yr CAGR | 4yr DD | 4yr Calmar | Cycle test |
|-------|---------:|-------:|-----------:|---------:|-------:|-----------:|-----------|
| MOM | 115.12% | 29.61% | 3.89 | 86.82% | 29.61% | 2.93 | 4yr only |
| TQQQ | 67.94% | 37.37% | 1.82 | 56.19% | 37.37% | 1.50 | 16yr → 33.55% / 54.92% / 0.61 |
| BRK | 56.55% | 25.04% | 2.26 | 33.68% | 23.26% | 1.45 | 4yr only |

## Blended book — 50 / 25 / 25 (MOM / TQQQ / BRK)

| Window | CAGR | MaxDD | Calmar |
|--------|-----:|------:|-------:|
| 3yr (2023-2026) | **90.44%** | 25.97% | **3.48** |
| 4yr (2022-2026, incl. bear) | 68.29% | 25.73% | 2.65 |

Daily-return correlations (3yr): MOM-TQQQ 0.51, MOM-BRK 0.61, TQQQ-BRK 0.52 — all long
US tech beta, so the blend smooths return paths but does not deeply cut drawdown (only a
non-equity sleeve would; intentionally excluded here).

## Caveats (carry forward to live)
1. **Survivorship.** MOM/BRK sit on the *current* Nasdaq-100 → upward bias. The
   point-in-time check (`pseudo_n100_regime_top3`) shows the same momentum logic makes
   only ~34-56% on a bias-free universe. **Honest forward ≈ 45-60% CAGR for the book.**
2. **Window.** 2023-2025 was an AI mega-bull; 3yr is flattering, 4yr fairer. DDs are
   identical 3yr↔4yr → the worst drawdown is post-2022, not the 2022 bear.
3. **Bear stress.** Stock sleeves have only 4yr history; only TQQQ has a 16yr record
   (and it's sobering — 33.6% CAGR / 54.9% DD over the cycle).
4. **Concentration / single-name.** MOM top-3 is carried by a few mega-caps.
5. Live DD will likely run 30-40% in a real bear despite the regime gates.

## Artifacts on disk (`exports/backtests/us/`)
- `momentum_n100_regime_top3/{3yr,4yr}/` — summary.json + equity_curve.csv
- `leveraged_regime_tqqq/{3yr,4yr,15yr}/` — summary.json + equity_curve.csv
- `breakout_n100/{3yr,4yr}/` — summary.json + equity_curve.csv
- `<model>/sweep.json` — all parameter configs
- `reports/{1_MOM,2_TQQQ,3_BRK}_*.md` — per-model fact sheets
- `US_3MODEL_RESULTS.md` — full results + rejected models + the diversifier research

## Reproduce
```bash
docker compose up -d database
export DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system"
F=2023-05-24; T=2026-05-24; U=exports/backtests/us
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --from $F --to $T --out $U/momentum_n100_regime_top3/3yr
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py     --sma 200            --from $F --to $T --out $U/leveraged_regime_tqqq/3yr
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --from $F --to $T --out $U/breakout_n100/3yr
PYTHONPATH=. python3 tools/analysis/blend_models.py \
  MOM=$U/momentum_n100_regime_top3/3yr/equity_curve.csv \
  TQQQ=$U/leveraged_regime_tqqq/3yr/equity_curve.csv \
  BRK=$U/breakout_n100/3yr/equity_curve.csv --weights 0.5,0.25,0.25
```
