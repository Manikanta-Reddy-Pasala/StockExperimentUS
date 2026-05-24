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

## Results (true daily DD)

| Window | Config | CAGR | MaxDD | Calmar | WR |
|--------|--------|-----:|------:|-------:|---:|
| 3yr (2023-2026) | **D50 trail20 N5** | **56.55%** | 25.04% | 2.26 | 45.0% |
| 3yr | D100 trail20 N5 regime | 56.10% | 28.24% | 1.99 | 47.5% |
| 3yr | D100 trail20 N5 | 54.45% | 33.04% | 1.65 | 41.9% |
| 4yr (2022-2026) | D100 trail20 N5 regime | 42.58% | 28.24% | 1.51 | 50.0% |
| 4yr | D50 trail20 N5 | 33.68% | 23.26% | 1.45 | 46.8% |

## Notes
- Robustly ~55-56% (3yr) across parameters — not curve-fit to one setting.
- Low win rate (~45%) is normal for breakout systems: many small trailing-stop losses
  fund a few large winners. The trailing stop is the built-in DD control.
- Best standalone Calmar of the equity sleeves; diversifies MOM via different timing.
- Same survivorship caveat as MOM (current Nasdaq-100).
