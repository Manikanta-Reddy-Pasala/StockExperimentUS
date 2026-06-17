# Blends — pushing the 60–100% band to lower DD (4yr eToro)

Iteration 2 of the search: blend in-band standalone models to keep 60–100% CAGR
while cutting drawdown. Engine = `n40_largecap_weekly` (95.5%/37.6%); DD-reducer =
`diversifier_sleeve` (managed-futures/commodity ETF sleeve, 6%/13.8%, low correlation);
optional 2nd momentum leg = `momentum_n100_regime_top3` (74.1%/37.7%).

Window 2022-06-21 → 2026-06-17 (3.99y). Equity-curve blend (daily rebalanced weights).

## Un-leveraged blends

| Blend | Weights | CAGR | MaxDD | Calmar |
|---|---|---|---|---|
| n40 + div | 85 / 15 | **82.5%** | 32.5% | 2.54 |
| n40 + mom + div | 60 / 20 / 20 | 75.5% | 29.8% | 2.54 |
| n40 + mom + div | 50 / 30 / 20 | 74.2% | 29.5% | 2.51 |
| n40 + div | 75 / 25 | 72.7% | 29.7% | 2.44 |
| n40 + div | 65 / 35 | 63.0% | 26.9% | 2.34 |

→ `n40+div 85/15` = best return-in-band (82.5%) at 5pp lower DD than standalone, same Calmar 2.54.

## Vol-targeted blends (apply leverage to hit a vol target — MARGIN RISK)

| Blend | Weights | vol-target | max-lev | CAGR | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| n40 + div | 85 / 15 | 0.30 | 2.0 | **64.8%** | **18.4%** | **3.52** |
| n40 + div | 85 / 15 | 0.25 | 1.5 | 53.2% | 15.5% | 3.43 |

→ **Best risk-adjusted of the whole search:** vol-targeted n40+div = 64.8% CAGR at 18.4% DD,
Calmar 3.52 — in-band return, ~half the DD of any standalone. Uses up to 2× leverage
(margin-call risk; borrow cost not fully modeled).

## Verdict
- Want max return in band → standalone `n40_largecap_weekly` (95.5%).
- Want band return + low DD, no leverage → `n40+div 85/15` (82.5% / 32.5%).
- Want best Calmar, accept leverage → vol-targeted `n40+div` (64.8% / 18.4% / 3.52).

## Reproduce
```
export PYTHONPATH=.
B=exports/backtests/us/models_60_100_cagr_4yr
python3 tools/analysis/blend_models.py \
  n40=$B/n40_largecap_weekly/equity_curve.csv \
  div=$B/diversifier_sleeve/equity_curve.csv \
  --weights 0.85,0.15                         # un-leveraged
python3 tools/analysis/blend_models.py \
  n40=$B/n40_largecap_weekly/equity_curve.csv \
  div=$B/diversifier_sleeve/equity_curve.csv \
  --weights 0.85,0.15 --vol-target 0.30 --max-lev 2.0   # vol-targeted
```
Caveat (inherits standalone runs): eToro ~975-bar (~4yr) cap, no lookback buffer →
regime SMA cash-heavy until ~Apr 2023, understating CAGR.
