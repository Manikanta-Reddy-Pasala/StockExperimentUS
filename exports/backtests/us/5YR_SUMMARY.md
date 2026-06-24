# 5-YEAR summary — trades + performance (FIXED regime data)

Generated 2026-06-25. Window **2021-05-24 → 2026-05-22 (4.99y)**, spliced history
(yfinance_real before 2022-05-18, eToro after) on the **fixed** QQQ/SPY regime data.
$1M backtest capital; `$5k` scales the realized multiple. This is the focus deliverable;
10yr is a secondary note at the bottom.

Configs (both = weekly, blend signal, QQQ 200d+50d gate, daily regime exit, 8% crash
trigger, next-open+T+1 fills, $0 commission + 8bps slip + $1/txn):
- **momentum_sp100** = `--top 1 --fast-sma 50 --regime-daily --dd-exit 0.08`
- **n40_largecap_weekly** = `--top 3 --regime-daily --dd-exit 0.08`

## Performance — 5yr
| Model | CAGR | MaxDD | Calmar | Trades | Win% | Final ($1M) | **$5k →** |
|-------|-----:|------:|-------:|-------:|-----:|------------:|----------:|
| **momentum_sp100** | **101.8%** | 39.9% | 2.55 | 58  | 60.3% | $33.31M | **$166,554** |
| **n40_largecap_weekly** | 78.8% | **36.8%** | 2.14 | 152 | 60.5% | $18.21M | **$91,056** |

- momentum (top-1) clears **100% CAGR**; DD pinned ~40% = one name's own max drawdown.
- n40 (top-3) clears the **≤38% DD** target; CAGR 79%, smoother (152 trades vs 58).

## Trades — momentum_sp100 (58 trades, 35 wins / 60%, total +$20.3M)
Top winners:
| Symbol | Entry → Exit | Ret | PnL |
|--------|--------------|----:|----:|
| SNDK | 2025-10-08 → 2025-11-18 | +111% | +$6.21M |
| SNDK | 2026-01-28 → 2026-02-04 | +30% | +$4.85M |
| SNDK | 2026-01-07 → 2026-01-21 | +35% | +$4.22M |
| APP  | 2024-09-25 → 2025-01-13 | +140% | +$2.08M |
| PLTR | 2025-05-14 → 2025-08-19 | +35% | +$1.13M |

Worst: APP −18% (−$0.69M), MSTR −20% (−$0.30M), ARM −9%, PLTR −8%, MRVL −8%.
Most-traded: NVDA×12, PLTR×9, APP×5, SNDK×5, AMD×4.

## Trades — n40_largecap_weekly (152 trades, 92 wins / 61%, total +$14.4M)
Top winners:
| Symbol | Entry → Exit | Ret | PnL |
|--------|--------------|----:|----:|
| SNDK | 2025-10-08 → 2026-03-23 | +492% | +$6.62M |
| WDC  | 2026-04-15 → 2026-05-12 | +41% | +$1.83M |
| APP  | 2024-09-25 → 2025-03-05 | +151% | +$0.89M |
| PLTR | 2024-09-18 → 2025-03-05 | +139% | +$0.80M |
| WDC  | 2025-09-24 → 2025-12-09 | +53% | +$0.64M |

Worst: MSTR −33% (−$0.22M), MSTR −20%, ARM −20%/−21%, MSTR −12%.
Most-traded: NVDA×11, PLTR×10, TSLA×9, CRWD×8, AMD×7, MU×7.

## Honest caveats
- **Concentration tail:** both books lean on a few monster trades (SNDK alone = ~$15M
  of momentum's $20M, and a +492% SNDK run for n40). Strip the single best name and
  CAGR falls hard — this is real top-1/top-3 single-name dependence, not diversified alpha.
- Gross backtest: no tax/financing; fills modeled at next-open + 8bps + $1/txn only.
- DD floor ~37-40% is structural for a concentrated long-only momentum book even with
  the (now-correct) regime gate.

## Full data
`{momentum_sp100,n40_largecap_weekly}_improved/5yr/*/` → `summary.json`,
`trade_ledger.csv` (every entry/exit + PnL), `transactions.csv`, `equity_curve.csv`.

---

## 10-year — NOTE only (not the focus, kept for reference)
Regenerated on the fixed regime data but **not re-detailed here per request**:
- momentum_sp100 10yr: 68.5% CAGR / 39.9% DD / Calmar 1.72 ($5k → $907,539)
- n40_largecap_weekly 10yr: 45.5% CAGR / 42.6% DD / Calmar 1.07 ($5k → $209,946)

Files exist at `*_improved/10yr/` if needed; treat as secondary to the 5yr book above.
Full multi-window detail in `IMPROVED_MODELS.md`.
