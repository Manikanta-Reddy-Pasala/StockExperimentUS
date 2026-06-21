# US universe + PIT study — 2026-06-21

Data: **eToro** daily bars (sole source), 794 symbols, 2021-06-01 → 2026-06-18.
Backtests run on the NUC (`stockexp_nuc`).

## Membership / universe lists committed

| File | What | Source |
|---|---|---|
| `src/data/symbols/sp500_membership.csv` | S&P 500 **point-in-time** (symbol, start, end) | fja05680/sp500 (real index history) |
| `src/data/symbols/nasdaq100_membership.csv` | Nasdaq-100 **PIT** (149 names incl. removed) | Wikipedia Added/Removed changes table |
| `src/data/symbols/sp100.csv` | S&P 100 (OEX) current snapshot (101) | Wikipedia |
| `src/data/symbols/combined_us_universe.csv` | S&P500 ∪ Nasdaq500 ∪ Nasdaq100 (842) | union |
| `src/data/symbols/pit/nasdaq500_{2023..2026}.csv` | Yearly Nasdaq-500-by-ADV (no official index exists) | constructed from data |
| `src/data/symbols/pit/sp100_{2023..2026}.csv` | Yearly S&P-100-by-ADV within S&P-500 PIT members | constructed |

Reconstitution cadence: S&P 500 = ad-hoc ~20-25/yr; Nasdaq-100 = annual (Dec) + interim; "Nasdaq 500" = not an official index (top-500-by-mktcap snapshot).

## Universe comparison — regime/momentum engine, identical 3.93y window

| Universe | CAGR | MaxDD | Calmar |
|---|---|---|---|
| Nasdaq 100 | 74.2% | 37.7% | 1.97 |
| S&P 500 | 61.1% | 35.6% | 1.72 |
| Nasdaq 500 | 55.2% | 40.9% | 1.35 |

US momentum alpha concentrates in large-cap → narrow beats broad. (Opposite of India's Nifty-500 breadth.)

## Models >100% CAGR — HONEST 5yr (2022 crash included), n40 recipe

n40 recipe = top-40-ADV → top-3 by blend signal → weekly rebal → QQQ 200d regime gate.
Leverage modest (margin cost 6% APR modeled).

| Model (universe) | lev | CAGR | MaxDD | Calmar | WR |
|---|---|---|---|---|---|
| **n40 @ S&P 500** | 1.10 | **129.9%** | 37.8% | 3.44 | 79.7% |
| **n40 @ Nasdaq 100** | 1.10 | **108.4%** | 41.1% | 2.64 | 76.2% |
| **n40 @ S&P 100** | 1.25 | **102.7%** | 33.2% | 3.10 | 80.5% |
| n40 @ Nasdaq 500 | 1.20 | 88.5% | 44.6% | 1.98 | 75.1% |

Un-leveraged n40 @ Nasdaq-100 = 98% / 37.6% DD. S&P 500 universe + 1.1× lev is the standout (130%, Calmar 3.44).

### Honesty notes
- Earlier 137%/132% figures were on the **3yr 2023-2026 AI-bull window** (survivorship-biased, current-snapshot universe) — inflated. The numbers above are full 5yr incl. the 2022 crash.
- Survivorship: eToro (a broker) serves only currently-tradeable instruments, so ~75 delisted S&P names (ATVI, CTXS, SIVB…) are absent — a residual upward bias no broker feed can fix.
- 100%+ is leverage-dependent; un-leveraged ceiling ≈ 98% (n40) / 60-75% (others).

---

## ADDENDUM — PIT membership wired (survivorship-corrected) 2026-06-21

`tools/shared/us_index_membership.py` (`eligible_at(date)`) now feeds the n40
engine via `--membership-csv`. At each rebalance the universe = panel ∩ members
eligible on that date (no look-ahead). Regression-checked: non-PIT path unchanged.

### Current-universe (inflated) vs PIT (honest), 2021-06→2026-06, matched vintage

| Config | non-PIT CAGR/DD | **PIT CAGR/DD/Calmar** | inflation |
|---|---|---|---|
| n40 @ S&P 500 (1.1×)  | 132% / 38% | **57.1% / 40.3% / 1.42** | −75pp |
| n40 @ Nasdaq 100 (1.1×) | 106% / 41% | **65.1% / 38.2% / 1.70** | −41pp |
| n40 @ S&P 100 (1.25×) | 103% / 33% | **94.3% / 34.0% / 2.78** | −8pp |

The "S&P 500" headline was the most inflated — non-PIT it was really
sp500 ∩ today's-Nasdaq-100 (pre-selected mega-cap survivors). DD ~flat under PIT:
survivorship inflated **returns, not risk**.

### Honest 100%+ — leverage cost on PIT data
- **S&P 100 @ 1.35× = 102.3% CAGR / 36.4% DD / Calmar 2.81** — the ONE config that clears 100% honestly at sane risk (stable OEX membership).
- Nasdaq 100: 94.6% even @ 1.7× (55% DD). S&P 500: 86% even @ 1.9× (63% DD).

**Conclusion:** survivorship-corrected, the honest ceiling is ~94% un-stressed
(S&P 100, 1.25×) / ~102% at 1.35×. Three models >100% on honest data is NOT
achievable at sane leverage — only S&P 100 makes it. Earlier 100-137% figures
carried 40-75pp survivorship inflation.
