# Model 3 — BRK · breakout_n100

**Mechanism:** event-driven breakout momentum (let winners run, cut losers via a
trailing stop). Different timing/DD profile from the monthly-rotation MOM sleeve.
**File:** `tools/models/breakout_n100/backtest.py`
**Live config (LOCKED v2):** `--donchian 50 --trail 20 --maxn 5 --regime`

> v2 upgrade: **regime gate ON** (only enter when QQQ > 200d SMA). Near-free win —
> CAGR 56→66% (3yr) AND DD 48→37% (10yr), Calmar 0.54→0.73 (10yr).

## Rules
- **Universe:** real Nasdaq-100.
- **Entry:** close makes a new 50-day high AND close > 200-day SMA. Checked daily
  (event-driven, not on a calendar). If more breakouts than free slots, take highest
  60-day momentum.
- **Hold:** up to 5 equal-weight.
- **Exit:** close ≤ peak-since-entry × (1 − 20%) trailing stop, OR close < 100-day SMA.
- **Costs:** $0 commission + 8 bps slippage. Daily MTM DD.

## Results — LOCKED config (`--donchian 50 --trail 20 --maxn 5 --regime`), true daily DD

| Window | CAGR | MaxDD | Calmar |
|--------|-----:|------:|-------:|
| 3yr (2023-2026) | 66.34% | 25.51% | 2.60 |
| 4yr (2022-2026) | 34.07% | 21.18% | 1.61 |
| 10yr (2016-2026, incl. 2018/2020/2022) | 26.85% | 36.68% | 0.73 |

Regime gate ON is the v2 upgrade — vs no-regime it adds CAGR (56→66% on 3yr) AND cuts DD
(48→37% on 10yr). Low win rate (~45%) is normal for breakouts: small trailing-stop losses
fund a few big winners.

## Notes
- Robustly ~55-56% (3yr) across parameters — not curve-fit to one setting.
- Low win rate (~45%) is normal for breakout systems: many small trailing-stop losses
  fund a few large winners. The trailing stop is the built-in DD control.
- Best standalone Calmar of the equity sleeves; diversifies MOM via different timing.
- Same survivorship caveat as MOM (current Nasdaq-100).
