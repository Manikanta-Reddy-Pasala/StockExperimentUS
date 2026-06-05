# Drawdown reduction — the diversifier sleeve

Goal: cut the book's ~38% MaxDD. The regime gate + vol-targeting only move along the
frontier (less DD = less CAGR, ~flat Calmar). The one STRUCTURAL DD lever is a sleeve
with near-zero correlation to Nasdaq momentum.

## DIV sleeve (`tools/models/diversifier_sleeve/`)
All-weather basket: managed futures (DBMF/KMLM/CTA) + commodities (DBC/PDBC) + dollar
(UUP) + gold (GLD) + bonds (TLT). Hold top-4 by blend(63/126d) momentum, monthly, NO
regime gate. Standalone: ~9.8% CAGR / 24% DD (2020-2026) — modest by design.
**Correlation to the book: MOM 0.09 · TQQQ 0.10 · BRK 0.13** (near-zero).

## Result — book + DIV beats the 3-model book on BOTH CAGR and DD
Window 2020-06 → 2026-05 (DBMF/KMLM only exist from 2019-2020), true daily DD:

| Book | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|
| 3-model 45/15/40 (MOM/TQQQ/BRK) | 58.9% | 36.3% | 1.62 |
| **MOM 0.60 / TQQQ 0.05 / DIV 0.35** (max Calmar) | **61.0%** | **28.2%** | **2.17** |
| MOM 0.65 / TQQQ 0.05 / DIV 0.30 (max CAGR, DD<30) | 65.3% | 30.3% | 2.16 |
| MOM 0.15 / BRK 0.15 / DIV 0.70 (min DD) | 23.5% | 14.8% | 1.59 |

The optimizer drops BRK entirely (corr 0.62 to MOM = redundant) and cuts TQQQ to 5%,
putting 35% in DIV. Net: **DD 36→28% AND CAGR 59→61% — Calmar 1.62→2.17.** A real free
lunch from diversification, not a risk-dial trade.

## Recommended DD-reduced book (v3 candidate)
**MOM 0.60 / TQQQ 0.05 / DIV 0.35** — 61% CAGR / 28% DD / Calmar 2.17.
Reproduce:
```
python tools/models/diversifier_sleeve/backtest.py --from 2020-06-01 --to 2026-05-24 --out .../div
python tools/analysis/blend_optimize.py MOM=… TQQQ=… BRK=… DIV=…/equity_curve.csv --objective calmar
```

## Caveats
- **Short history:** DBMF (2019)/KMLM (2020)/CTA (2022) — only a ~6yr window, NO 2008/2018
  long-cycle test. The low correlation is structural (different asset classes) so it should
  hold, but the managed-futures CAGR contribution is unproven across a full bond/commodity cycle.
- Lower DD layers (vol-target, smaller weights) available if 28% is still too high; min-DD
  config gets to ~15% DD at 24% CAGR.
