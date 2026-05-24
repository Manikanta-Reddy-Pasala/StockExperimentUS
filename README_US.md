# StockExperimentUS

US (Nasdaq) fork of StockExperiment. Same 4 live momentum models, but data comes
from **yfinance** (no Fyers — that's India-only) and the universe is US Nasdaq.

## What's here

| Piece | Path |
|---|---|
| Universe builders | `tools/refresh_nasdaq100.py`, `tools/refresh_nasdaq500.py` |
| Universe lists | `src/data/symbols/nasdaq100.csv` (101), `nasdaq500.csv` (500 by mkt cap) |
| Data loader (yfinance → Postgres) | `tools/pull_yfinance_history.py` |
| Backtested OHLCV data | `data/historical_yfinance_ohlcv.csv.gz` (500 syms, 461,731 rows, 2022-05-24→2026-05-22) |
| 4 ported models | `tools/models/{momentum_n100_top5_max1,momentum_pseudo_n100_adv,n20_daily_large_only,midcap_narrow_60d_breakout}/backtest.py` |
| **3-model diversified book** | `tools/models/{momentum_n100_regime_top3,leveraged_regime_tqqq,breakout_n100}/backtest.py` |
| Blend tool | `tools/analysis/blend_models.py` |
| ETF data (QQQ/TQQQ/SOXL/BIL/SPY) | `src/data/symbols/leveraged_etfs.csv` |
| **Ported-model CAGR + caveats** | `exports/backtests/US_RESULTS.md` |
| **3-model book results + all data** | `exports/backtests/US_3MODEL_RESULTS.md` |
| Per-model summaries | `exports/backtests/us/<model>/summary.json` |
| Plan | `docs/plans/2026-05-24-us-port.md` |

## 3-Model Diversified Book (recommended)

Three **distinct mechanisms** (cash-only, true daily-MTM drawdown), blended:

| Sleeve | Mechanism | 3yr CAGR | 3yr MaxDD | Calmar |
|---|---|---:|---:|---:|
| MOM `momentum_n100_regime_top3` | momentum rotation + QQQ>200d gate, top-3 | 114.8% | 29.6% | 3.88 |
| TQQQ `leveraged_regime_tqqq` | 3× Nasdaq ETF timed by QQQ 200d SMA | 64.2% | 37.4% | 1.72 |
| BRK `breakout_n100` | 50d-high breakout + 20% trailing stop | 55.3% | 25.0% | 2.21 |
| **Blend 45/30/25** | daily-rebalanced | **88.2%** | **25.9%** | **3.40** |

4yr (incl. 2022 bear): blend 45/30/25 = **66.96% / 25.68% DD / 2.61 Calmar**.
Blending drops drawdown below every single sleeve. **Numbers are survivorship- and
bull-window-inflated** — honest forward ≈ 50-65% CAGR, DD 30-40% in a real bear. Full
data, rejected models (mean-reversion, SOXL), the point-in-time reality check, the
16-year TQQQ cycle test, correlations, caveats, and reproduce commands are in
`exports/backtests/US_3MODEL_RESULTS.md`.

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
gzcat data/historical_yfinance_ohlcv.csv.gz | docker compose exec -T database \
  psql -U trader -d trading_system -c "\copy historical_data(symbol,date,open,high,low,close,volume,adj_close) FROM STDIN WITH CSV HEADER"
# (then UPDATE historical_data SET data_source='yfinance', timestamp=extract(epoch from date)::bigint, api_resolution='1D';)
# option B: re-pull fresh
PYTHONPATH=. DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system" \
  python3 tools/pull_yfinance_history.py --universe src/data/symbols/nasdaq500.csv --start 2022-05-24 --end 2026-05-24

for m in momentum_n100_top5_max1 momentum_pseudo_n100_adv n20_daily_large_only midcap_narrow_60d_breakout; do
  PYTHONPATH=. DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system" \
    python3 tools/models/$m/backtest.py --out exports/backtests/us/$m
done
```
