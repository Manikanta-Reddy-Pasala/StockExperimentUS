# US Models — 60–100% CAGR Search (4yr, eToro data)

**Window:** 2022-06-17 → 2026-06-17 (4.00y)
**Data source:** eToro public market-data API (sole source; yfinance/IBKR-data removed). DB pulled fresh: 454 equity symbols + QQQ + TQQQ + 7 diversifier ETFs. `data_source='yfinance'` bucket (legacy storage label, eToro-sourced).
**Costs:** 8 bps slippage on traded notional, $0 commission (IBKR-Lite-style).
**Capital:** $1,000,000 start.

## Goal
Find models landing in the **60–100% CAGR** band, referencing existing US models + India-market-derived ports.

## Results (ranked by CAGR)

| Model | Config | CAGR | TrueDailyDD | Calmar | WR | Trades | Band |
|---|---|---|---|---|---|---|---|
| india_retest_faithful | k2 / ret (India spec) | 117.0% | 44.5% | 2.63 | 67.7% | 65 | >100 |
| india_n40_faithful | top1 / ret (India spec) | 105.1% | 57.8% | 1.82 | 69.0% | 171 | >100 |
| **n40_largecap_weekly** | top3 / blend / QQQ-reg | **95.5%** | 37.6% | **2.54** | 77.0% | 318 | ✅ 60–100 |
| **india_n40_improved** | top3 / blend / QQQ-reg | **94.1%** | 37.6% | 2.51 | 76.3% | 317 | ✅ 60–100 |
| **momentum_n100_regime_top3** | top3 / regime | **74.1%** | 37.7% | 1.97 | — | 100 | ✅ 60–100 |
| **n20_daily_large_only** | v2 large-only | **73.0%** | 61.8% | 1.18 | — | 221 | ✅ 60–100 |
| **momentum_n100_top5_max1** | top5 / max1-per-name | **69.1%** | 34.6% | 2.00 | — | 41 | ✅ 60–100 |
| **india_retest_improved** | k3 / blend / QQQ-reg | **68.7%** | 52.3% | 1.31 | 64.5% | 93 | ✅ 60–100 |
| leveraged_regime_tqqq | TQQQ gate200 | 43.8% | 41.3% | 1.06 | — | 5 | below |
| breakout_n100 | D100 / trail20 / N5 | 35.7% | 30.3% | 1.18 | — | 62 | below |
| diversifier_sleeve | top4 ETF sleeve | 6.0% | 13.8% | 0.44 | 64.3% | 70 | below |

**Reference (not run as standalone models):** buy-hold TQQQ 63.0%/58.5% DD; buy-hold QQQ 27.7%/22.9% DD.

**Broken / N-A on this data:** momentum_pseudo_n100_adv −5% (needs pseudo-ADV input); leveraged_rotation_3x 0% (no/broken data); midcap_narrow_60d_breakout uses nifty_midcap150 (India universe) — not applicable to US.

## Best picks
- **Return:** `n40_largecap_weekly` — 95.5% CAGR, 37.6% DD, Calmar 2.54, WR 77%.
- **Lowest DD in band:** `momentum_n100_top5_max1` — 69.1% CAGR, 34.6% DD, Calmar 2.00.
- **India port:** `india_n40_improved` mirrors n40_largecap (94.1%/37.6%) — same large-cap weekly momentum archetype.

## Caveats
- eToro caps ~975 daily candles (~4yr) with **no pre-window lookback buffer**, so the 200-day regime SMA is invalid until ~Apr 2023 → regime/improved runs sit cash-heavy early, **understating** their CAGR.
- 47/501 universe symbols failed eToro pull (mostly preferred shares/ADRs: AGNCN, FITBM, JD…); all liquid momentum names present.
- Survivorship: static CSV universes (no point-in-time Nasdaq membership for US).

## Artifacts per model
Each subdir holds `summary.json` + a trade ledger (`trade_ledger.csv` or `.json`). Most also have `equity_curve.csv` + `transactions.csv` (full buy/sell tape). `momentum_n100_top5_max1` and `n20_daily_large_only` emit JSON ledgers only (their native format).

Reproduce:
```
export DATABASE_URL='postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system'
PYTHONPATH=. python3 tools/models/<dir>/backtest.py --from 2022-06-17 --to 2026-06-17 --out <outdir>
# India ports:
PYTHONPATH=. python3 tools/models/india_ports_us/backtest.py --model all --top 1 --signal ret   # faithful
PYTHONPATH=. python3 tools/models/india_ports_us/backtest.py --model all --top 3 --signal blend --regime  # improved
```
