# Search for a 100% CAGR (5–10yr backtested) model — running log

Goal: a model holding ≥100% CAGR over a full 5–10yr window (incl. bear markets).
Honest framing: the mapped US frontier tops ~53–55% CAGR over 10yr (unleveraged
momentum) and ~130% only in 3yr bull bursts. Each iteration tries a new lever.

## Iteration 1 (2026-06-05)
- **N40 large-cap, concentration sweep (10yr):** top1 52.7%/77.8%DD, top2 53.9%/60.5%, top3 53.0%/46.8%. Concentration adds DD, not CAGR. Ceiling ~53%.
- **Leveraged 3x-ETF momentum rotation** (`tools/models/leveraged_rotation_3x/`, universe TQQQ/SOXL/TECL/FAS/UPRO/UDOW/TNA/CURE/RETL/DRN/LABU/FNGU, QQQ 200d gate): 10yr BEST = top2 ret63 weekly **28.1% CAGR / 69% DD**. Leverage rotation BACKFIRES over full cycles — vol decay + 2018/2020/2022 crashes + whipsaw. Worse than plain momentum.
- **Verdict so far:** no model ≥100% CAGR over 10yr. Leverage does not rescue it over full cycles; bears destroy 3x. 3yr bull-only configs (N40 132%, lev3x bull) exceed 100% but collapse over 10yr.

## Next levers to try
- Leveraged-MOMENTUM multiplier (1.5–2x applied to the top-3 blend signal, only in risk-on regime) — leverage the ALPHA, not a 3x ETF.
- TQQQ buy-hold regime exact 10yr; single-3x (TQQQ-only) tight regime.
- Shorter window honesty: report the best 5yr (2021-2026) separately from 10yr.

## Iteration 2 (2026-06-05) — leverage the ALPHA (margin on the momentum signal)
Added `lev` + `margin_apr` (6% borrow) to the engine; applied to N40 top-3 blend regime
(`--lev` flag on n40_largecap_weekly). Leverage the proven signal, not a 3x ETF.

| Config | 10yr CAGR | 10yr DD | 5yr CAGR | 5yr DD |
|---|---:|---:|---:|---:|
| lev 1.5× | 73.1% | 64.7% | 71.3% | 62.7% |
| lev 2.0× | 87.5% | 78.5% | 81.7% | 74.5% |
| lev 2.5× | **93.8%** | 87.8% | 82.0% | 83.1% |
| lev 2.5× + trail15 | **96.0%** | 83.1% | — | — |

Trailing stop barely helps (leveraged 2020/2022 gap-downs blow through the regime gate).

### DEFINITIVE VERDICT
**A survivable 100% CAGR over a full 5–10yr cycle does NOT exist for US large-cap systematic.**
- 100% CAGR/10yr is reachable only at **~2.7–3× leverage**, which carries **80–90% MaxDD** — i.e.
  a real margin account is **liquidated/margin-called** long before realizing it (the backtest
  ignores forced liquidation, so even 94% is optimistic).
- Survivable frontier: **~53% CAGR / 47% DD** (unleveraged N40) · **~73% / 65%** (1.5×, aggressive).
- DD floor is structural to momentum (~38–47% unleveraged); leverage multiplies it past survivability.
- Confirms the mapped frontier ([[project-three-model-blend]] search log): US high-CAGR comes only
  from concentrated large-cap momentum; bears + leverage cap the realistic ceiling well under 100%/10yr.
- 100% is achievable only over **3yr bull bursts** (N40 132%), not full cycles.

## Iteration 5 (2026-06-05) — leverage the DIVERSIFIED BOOK (the answer)
Added `--lev` to `tools/analysis/blend_models.py` (margin on the combined blend + 6% borrow).
The v2 book (MOM/TQQQ/BRK 45/15/40) has lower base DD (38%) than any single sleeve, so
leverage on the BOOK gives a better CAGR/DD frontier than leveraging one model.

| Lev | 10yr CAGR | 10yr DD | Calmar | 3yr CAGR | 3yr DD |
|---|---:|---:|---:|---:|---:|
| 1.0× | 53.4% | 37.7% | 1.42 | 108.7% | 24.9% |
| 1.5× | 77.8% | 55.9% | 1.39 | — | — |
| **2.0×** | **101.1%** | 69.8% | 1.45 | 266.7% | 45.1% |
| 2.5× | 121.9% | 80.0% | 1.52 | — | — |

### THE 100%-CAGR ANSWER (with the honest caveat)
**2× leveraged v2 book = 101% CAGR / 70% DD over a full 10yr** — reproduce with:
`python tools/analysis/blend_models.py MOM=… TQQQ=… BRK=… --weights 0.45,0.15,0.40 --lev 2.0`

This is the BEST 100%-CAGR-10yr config found (beats leveraged single-N40 87%/78%) because
the diversified book's 38% base DD leaves more room before leverage. **BUT 70% MaxDD on a 2×
margin account is margin-call / liquidation territory** (maintenance margin is breached well
before a 70% equity drop), and the backtest ignores forced liquidation + carries
survivorship/daily-rebalance optimism. So it clears 100% CAGR on paper but is NOT a safely
tradeable strategy. The honest survivable book stays the unleveraged 45/15/40 (53%/38%).

**Bottom line:** 100% CAGR over 5–10yr exists only WITH ~2× leverage at ~70% DD. Without
leverage the robust ceiling is ~53% (10yr) / ~109% (3yr bull). Search complete.
