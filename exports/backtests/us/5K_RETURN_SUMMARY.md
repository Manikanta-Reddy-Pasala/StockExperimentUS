# $5,000-per-model return summary — 4yr / 5yr / 10yr

Generated 2026-06-25. Two production models, freshly re-run on NUC against the
corrected spliced feed (eToro `yfinance` ≥ 2022-05-18, backfill `yfinance_real`
2016-06-01→2022-05-16, ratio-spliced at join **2022-05-18**). All windows end
**2026-05-22**. Backtest capital $1,000,000; `$5k` columns scale the realized
multiple to a $5,000 stake.

Both models share the **same engine** (`tools/models/n40_largecap_weekly/backtest.py`,
weekly top-K, blend signal `avg(21/63/126d ret)`, QQQ 200d regime gate, next-open
+T+1 fills, $0 commission + 8bps slippage + $1/txn):

- **momentum_sp100** = engine `--top 1` (single-stock) → `n40_top1_blend_reg`
- **n40_largecap_weekly** = engine `--top 3` → `n40_top3_blend_reg`

4yr is pure eToro era (no splice). 5yr/10yr use `--extended` splice.

---

## momentum_sp100 (top-1 single-stock)

| Window | Years | CAGR | MaxDD | Calmar | Trades | WR | Multiple | **$5k →** |
|--------|------:|-----:|------:|-------:|-------:|----:|---------:|----------:|
| 4yr  | 3.99 | 119.22% | 56.70% | 2.10 | 38  | 63.2% | 23.00× | **$114,990** |
| 5yr  | 4.99 |  70.16% | 70.49% | 1.00 | 78  | 53.8% | 14.22× | **$71,104**  |
| 10yr | 9.97 |  43.08% | 79.69% | 0.54 | 144 | 56.9% | 35.59× | **$177,970** |

## n40_largecap_weekly (top-3 blend)

| Window | Years | CAGR | MaxDD | Calmar | Trades | WR | Multiple | **$5k →** |
|--------|------:|-----:|------:|-------:|-------:|----:|---------:|----------:|
| 4yr  | 3.99 | 102.39% | 46.57% | 2.20 | 96  | 67.7% | 16.72× | **$83,577**  |
| 5yr  | 4.99 |  62.53% | 54.09% | 1.16 | 187 | 58.3% | 11.31× | **$56,534**  |
| 10yr | 9.97 |  45.35% | 54.04% | 0.84 | 371 | 56.3% | 41.63× | **$208,156** |

---

## $5,000 stake — side by side

| Window | momentum_sp100 | n40_largecap_weekly |
|--------|---------------:|--------------------:|
| 4yr  | **$114,990** (57% DD) | $83,577 (47% DD) |
| 5yr  | $71,104 (70% DD) | **$56,534** (54% DD) |
| 10yr | $177,970 (**80% DD**) | **$208,156** (54% DD) |

## Read

- **4yr**: momentum (top-1) wins on $ (+$31k) but rides a 57% drawdown.
- **10yr**: n40 (top-3) wins on **both** $ ($208k vs $178k) **and** DD (54% vs 80%).
  top-1's 80% MaxDD is margin-call / account-blowup territory — uninvestable in
  practice despite the headline multiple.
- Longer the horizon, more the single-stock concentration hurts: momentum CAGR
  decays 119→43%, n40 102→45%. n40 is the survivable book holding.
- Gross backtest: no tax, no financing, no real fills/slippage beyond 8bps. Treat
  as relative ranking, not a promise.

## Sources
- `momentum_sp100/{4yr,5yr,10yr}/n40_top1_blend_reg/summary.json`
- `n40_largecap_weekly/{4yr,5yr,10yr}/n40_top3_blend_reg/summary.json`
