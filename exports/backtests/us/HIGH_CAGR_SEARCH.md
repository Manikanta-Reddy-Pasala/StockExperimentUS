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
