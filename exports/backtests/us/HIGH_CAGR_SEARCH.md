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
