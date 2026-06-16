# StockExperimentUS

US (Nasdaq) fork of StockExperiment. Same 4 live momentum models, but data comes
from **yfinance** (no Fyers — that's India-only) and the universe is US Nasdaq.

## What's here

| Piece | Path |
|---|---|
| Universe builders | `tools/refresh_nasdaq100.py`, `tools/refresh_nasdaq500.py` |
| Universe lists | `src/data/symbols/nasdaq100.csv` (101), `nasdaq500.csv` (500 by mkt cap) |
| Data loader (yfinance → Postgres) | `tools/pull_etoro_history.py` |
| Backtested OHLCV data | `data/historical_etoro_ohlcv.csv.gz` (500 syms, 461,731 rows, 2022-05-24→2026-05-22) |
| 4 ported models | `tools/models/{momentum_n100_top5_max1,momentum_pseudo_n100_adv,n20_daily_large_only,midcap_narrow_60d_breakout}/backtest.py` |
| **3-model diversified book** | `tools/models/{momentum_n100_regime_top3,leveraged_regime_tqqq,breakout_n100}/backtest.py` |
| Blend tool | `tools/analysis/blend_models.py` |
| ETF data (QQQ/TQQQ/SOXL/BIL/SPY) | `src/data/symbols/leveraged_etfs.csv` |
| **Ported-model CAGR + caveats** | `exports/backtests/US_RESULTS.md` |
| **3-model book results + all data** | `exports/backtests/US_3MODEL_RESULTS.md` |
| Per-model summaries | `exports/backtests/us/<model>/summary.json` |
| Plan | `docs/plans/2026-05-24-us-port.md` |

## LOCKED — 3-Model Momentum Book (recommended)

Final book after scanning ~12 US strategy archetypes (momentum, breakout,
VCP/Minervini, leveraged-trend, mean-reversion, factor/sector/cross-asset rotation,
overnight/intraday, seasonality, gold, crypto). Conclusion: **systematic US large-cap
CAGR comes only from concentrated momentum/trend** — these three are the keepers.
Cash-only, true daily-MTM drawdown.

Optimization pass (model-based) upgraded it: MOM now ranks on multi-timeframe **blend**
momentum, BRK runs its **regime gate ON** — higher CAGR *and* lower DD than v1.

| Sleeve | Live config | 3yr CAGR/DD/Calmar | 10yr CAGR/DD/Calmar |
|---|---|---|---|
| MOM `momentum_n100_regime_top3` | `--top 3 --regime --mom-mode blend` | 162.9% / 39.2% / 4.16 | 80.9% / 47.0% / 1.72 |
| TQQQ `leveraged_regime_tqqq` | `--sma 200` | 67.9% / 37.4% / 1.82 | 44.8% / 54.9% / 0.81 |
| BRK `breakout_n100` | `--donchian 50 --trail 20 --maxn 5 --regime` | 66.3% / 25.5% / 2.60 | 26.9% / 36.7% / 0.73 |
| **Blend 45/15/40** | — | **108.7% / 24.9% / 4.36** | **55.2% / 37.7% / 1.46** |

v2 beats v1 (90.4%/26.0%/3.48 · 45.7%/39.0%/1.17) on every metric, both windows.
**Numbers are survivorship- and bull-window-inflated** — honest forward ≈ 40-60% CAGR,
DD ~38% in a real bear (the DD floor; momentum's nature). Locked-book summary + exports:
`exports/backtests/us/3MODEL_BOOK.md` and `exports/backtests/us/<model>/{3yr,4yr}/`.
Per-model fact sheets in `exports/backtests/us/reports/`. Full search incl. rejected
models (VCP, mean-reversion, SOXL, factor rotation), the point-in-time reality check,
the 16-year TQQQ cycle test, and the diversifier research are in
`exports/backtests/US_3MODEL_RESULTS.md`.

## DD-reduced book (diversifier sleeve) — lower DD AND higher CAGR

The regime gate + vol-targeting only move along the frontier (less DD = less CAGR). The
one STRUCTURAL drawdown lever is a near-zero-correlation sleeve: `tools/models/diversifier_sleeve/`
(managed futures DBMF/KMLM/CTA + commodities + dollar + gold + bonds, top-4 momentum, no
regime). Correlation to the book = **0.09 / 0.10 / 0.13**.

| Book (2020-2026) | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|
| 3-model 45/15/40 (MOM/TQQQ/BRK) | 58.9% | 36.3% | 1.62 |
| **MOM 0.60 / TQQQ 0.05 / DIV 0.35** (DD-reduced) | **61.0%** | **28.2%** | **2.17** |
| min-DD (MOM 0.15 / BRK 0.15 / DIV 0.70) | 23.5% | 14.8% | 1.59 |

Adding DIV (and dropping the MOM-correlated BRK) cuts DD **36 → 28%** while CAGR *rises*
59 → 61% — a real free lunch, not a risk-dial trade. Caveat: DBMF/KMLM/CTA only exist from
2020, so this is a ~6yr window (no 2008/2018 long-cycle test). Full analysis:
`exports/backtests/us/DD_REDUCTION.md`. Leverage variants (100%-CAGR question):
`exports/backtests/us/HIGH_CAGR_SEARCH.md`.

## Live trading (IBKR)

Broker = Interactive Brokers (no Fyers — that's India). `tools/live/us_executor.py --model book`
computes today's target → diffs vs IBKR positions → places orders (`--live`, paper 7497;
dry-run default). End-to-end stack + commands: `US_LIVE_RUNBOOK.md`.

## Results (4yr, $1M, 2022-05-24 → 2026-05-24)

| Model | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|
| momentum_n100_top5_max1 | +94.65% | 44.90% | 2.11 |
| midcap_narrow_60d_breakout | +51.58% | 18.82% | 2.74 |
| momentum_pseudo_n100_adv | +36.84% | 48.42% | 0.76 |
| n20_daily_large_only | +28.82% | 71.68% | 0.40 |

See `exports/backtests/US_RESULTS.md` for full caveats (survivorship bias,
midcap lookahead, India-vs-US comparison).

## Reproduce

```bash
docker compose up -d database
# option A: reload the committed data
gzcat data/historical_etoro_ohlcv.csv.gz | docker compose exec -T database \
  psql -U trader -d trading_system -c "\copy historical_data(symbol,date,open,high,low,close,volume,adj_close) FROM STDIN WITH CSV HEADER"
# (then UPDATE historical_data SET data_source='yfinance', timestamp=extract(epoch from date)::bigint, api_resolution='1D';)
# option B: re-pull fresh
PYTHONPATH=. DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system" \
  python3 tools/pull_etoro_history.py --universe src/data/symbols/nasdaq500.csv --start 2022-05-24 --end 2026-05-24

for m in momentum_n100_top5_max1 momentum_pseudo_n100_adv n20_daily_large_only midcap_narrow_60d_breakout; do
  PYTHONPATH=. DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system" \
    python3 tools/models/$m/backtest.py --out exports/backtests/us/$m
done
```
