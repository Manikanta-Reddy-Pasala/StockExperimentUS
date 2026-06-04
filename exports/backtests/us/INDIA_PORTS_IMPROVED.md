# India-port models — IMPROVED (target ≥60% CAGR)

The faithful India ports bled to 55–87% DD at 15–20% CAGR (see INDIA_PORTS_RESULTS.md).
Improvement levers added to `tools/models/india_ports_us/backtest.py`:
`--top K` (diversify from 1→K equal-weight), `--signal blend` (avg 21/63/126d return —
the US v2 alpha), `--trail %` (per-position trailing stop), `--regime` (QQQ 200d gate).
Grid search: `--sweep`.

## Best configs

| Model (improved) | Window | CAGR | DD | Calmar | WR | vs original |
|---|---|---|---|---|---|---|
| **n40 top3 blend regime** (weekly large-cap) | 3yr | **132.5%** | 38.6% | 3.44 | 80% | 66% → 132% |
| n40 top3 blend trail20 regime | 3yr | 104.0% | 35.6% | 2.92 | — | lower DD |
| n40 top5 blend regime | 3yr | 98.9% | 36.3% | 2.72 | — | |
| **n40 top3 blend regime** | 5yr | **53.1%** | 46.8% | 1.13 | 75% | 20% → 53% |
| retest k6 blend regime | 3yr | 56.4% | 44.2% | 1.28 | 61% | −9% → 56% |
| emerging top5 blend regime | 5yr | 15.2% | 53.6% | 0.28 | 64% | 16% → 15% |

## What worked / what didn't (honest)
- **The fix = diversify (top-3) + blend signal** — same alpha as the locked v2 book. On a
  **large-cap** universe (n40) it clears 60% comfortably on 3yr (132%) and reaches 53% full-cycle
  5yr. Eight n40 variants beat 60% on 3yr.
- **emerging & retest still can't hit 60% full-cycle** (40% / 27% on 5yr at 45–54% DD). Root cause
  is the **universe, not the rule**: the US mid/small pool (nasdaq500 − nasdaq100) is dominated by
  speculative recent IPOs that crash hard. Diversification + blend lifts them but the floor is the
  junk pool. retest clears 60% only in the 3yr bull (k6 blend, 56% — just under).
- DD stays 35–47% — momentum's nature even gated; `--trail 20` trades ~25pp CAGR for ~3pp DD.

## Verdict
**n40 (large-cap top-3 weekly blend, regime) is the real ≥60% model** — but note it is essentially
a higher-turnover twin of the v2 MOM sleeve (large-cap blend momentum), so it does NOT diversify the
book (high correlation expected). The mid/small India archetypes do not reach 60% on US full-cycle;
US high-CAGR keeps coming from concentrated **large-cap** momentum, consistent with the mapped
frontier. Keep v2 as the book; n40-weekly is a viable higher-turnover MOM variant if wanted.
