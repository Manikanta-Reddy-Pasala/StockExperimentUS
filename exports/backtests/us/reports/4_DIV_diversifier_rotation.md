# Model 4 — DIV · diversifier rotation (non-equity)

**Mechanism:** cross-asset momentum rotation over NON-equity asset classes. Its job is
NOT raw return — it is the **shock absorber** with ~0.07 correlation to the three tech
sleeves.
**File:** `tools/models/sector_rotation/backtest.py` (engine) + `diversifier_universe.csv`
**Live config:** `--etf-csv src/data/symbols/diversifier_universe.csv --top 3 --no-gate`

## Rules
- **Universe (7 ETFs):** DBMF, KMLM, CTA (managed-futures / CTA trend funds), GLD (gold),
  TLT (20+yr Treasuries), DBC (commodities), UUP (US dollar).
- **Signal:** rank by mean(3-month, 6-month return), monthly.
- **Hold:** top-3 equal-weight (risk-off → BIL when the absolute gate is on).
- **Costs:** $0 commission + 8 bps slippage. Daily MTM DD.

## Results (true daily DD)

| Window | Config | CAGR | MaxDD | Calmar | corr to tech |
|--------|--------|-----:|------:|-------:|-------------:|
| 3yr (2023-2026) | **top3 no-gate** | 13.59% | 10.39% | 1.31 | **~0.07-0.09** |
| 3yr | top1 absgate | 18.75% | 19.21% | 0.98 | — |
| 4yr (2022-2026) | top3 no-gate | 6.31% | 25.41% | 0.25 | — |
| since 2021-01 | top3 no-gate | 9.60% | 25.41% | 0.38 | — |

## Notes — read honestly
- **Weak standalone** (6-14% CAGR, window-dependent; its 10% DD on 3yr was favorable,
  4yr DD is 25%). It will NOT win on its own numbers.
- **Its entire value is the ~0.07 correlation** to MOM/TQQQ/BRK (they are all long tech
  beta; DIV holds bonds/gold/commodities/dollar/managed-futures). Adding it to the book
  cuts portfolio drawdown (e.g., 4yr blend DD 25.7% → 20.8%, Calmar 2.65 → 2.82).
- **Caveat:** managed-futures ETFs are young — DBMF from 2019-05, KMLM 2020-12, CTA
  2022-03 — so this sleeve has NO long-cycle test. Its famous 2022 strength (managed
  futures rose while stocks+bonds fell) is mostly before the backtest windows here, and
  the equity sleeves' own regime gates already sidestep bears, muting DIV's marginal
  benefit on these specific windows.
- **Verdict:** keep ONLY if you want lower portfolio drawdown and accept ~10pp less
  blend CAGR. Drop it if you want maximum CAGR (run the 3 equity sleeves alone).
- All 7 ETFs are plain cash-buyable at IBKR (no margin).
