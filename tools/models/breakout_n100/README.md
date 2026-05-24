# breakout_n100 (BRK)

**Mechanism:** event-driven breakout momentum. Enter when a Nasdaq-100 name closes at
a new N-day high while in an uptrend; ride it with a percentage trailing stop; exit
only when the trail (or a 100d-SMA backstop) is hit — no calendar rebalance. This is a
different trade-timing and drawdown profile from the monthly-rotation momentum model
(let winners run, cut losers via the trail), so it diversifies that sleeve.

Equity is a daily mark-to-market curve → true MaxDD. Costs: $0 commission (IBKR Lite),
8 bps slippage. Data: `data_source='yfinance'`, real Nasdaq-100.

## Rules / knobs

| Flag | Default | Meaning |
|------|---------|---------|
| `--donchian` | 100 | breakout lookback (new N-day high triggers entry) |
| `--trail` | 20 | % trailing stop from the peak since entry |
| `--maxn` | 5 | max concurrent equal-weight positions |
| `--mom` | 60 | momentum window used to rank when more breakouts than free slots |
| `--regime` | off | also require QQQ > 200d SMA for new entries |

Entry also requires `close > 200d SMA` (trend filter). Exit if
`close ≤ peak×(1−trail)` **or** `close < 100d SMA`.

## Canonical config

```
--donchian 50 --trail 20 --maxn 5
```

## Results (true daily DD)

| Window | Config | CAGR | MaxDD | Calmar | WR |
|--------|--------|-----:|------:|-------:|---:|
| 3yr (2023-2026) | D50 trail20 N5 | 56.55% | 25.04% | 2.26 | 45% |
| 3yr | D100 trail20 N5 regime | 56.10% | 28.24% | 1.99 | 48% |
| 3yr | D100 trail20 N5 | 54.45% | 33.04% | 1.65 | 42% |
| 4yr (2022-2026) | D100 trail20 N5 regime | 42.58% | 28.24% | 1.51 | 50% |
| 4yr | D50 trail20 N5 | 33.68% | 23.26% | 1.45 | 47% |

Robustly ~55-56% CAGR on the 3yr window across parameters (not curve-fit to a single
setting). Low win rate (~45%) is typical of breakout systems — many small trailing-stop
losses funding a few large winners. Best standalone Calmar of the three sleeves.

## Run

```bash
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --sweep --from 2023-05-24 --to 2026-05-24
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --out exports/backtests/us/breakout_n100
```
