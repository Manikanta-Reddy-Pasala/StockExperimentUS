# leveraged_regime_tqqq (TQQQ)

**Mechanism:** index timing with a leveraged ETF. Hold a 3× ETF (default **TQQQ** =
3× Nasdaq-100) when the *underlying index* (QQQ) is above its 200-day SMA; otherwise
sit in cash (or BIL). The regime signal is read off QQQ, **not** the leveraged ETF.
Signal computed at close of day *t*, applied to day *t+1* (no lookahead). Equity is a
daily mark-to-market curve → true MaxDD.

All instruments are **cash-buyable** — the leverage lives inside the ETF, not in your
account (no margin). TQQQ inception is 2010-02-11, so this is the only sleeve with a
full-cycle (16-year) record.

## Knobs (the point of this model is drawdown control)

| Flag | Default | Effect |
|------|---------|--------|
| `--sma` | 200 | main trend gate length |
| `--second-sma` | 0 | faster exit gate (50 = also exit under 50d). **Whipsaws — usually hurts.** |
| `--partial` | 1.0 | fraction in the 3× ETF when risk-on (rest → risk-off asset). 0.5 ≈ 1.5× effective, much lower DD |
| `--buffer-pct` | 0.0 | exit only this % below the SMA (hysteresis) |
| `--confirm-days` | 1 | require N consecutive risk-off closes before exiting |
| `--riskoff` | cash | `cash` or `bil` (T-bill ETF, earns idle yield) |
| `--lev` | TQQQ | leveraged ETF symbol (e.g. `SOXL` for 3× semis) |

## Results (true daily DD)

| Window | Config | CAGR | MaxDD | Calmar |
|--------|--------|-----:|------:|-------:|
| 3yr (2023-2026) | base 200d (all-in) | 64.19% | 37.37% | 1.72 |
| 3yr | partial 0.66 (~2×) | 44.58% | 26.06% | 1.71 |
| 3yr | partial 0.5 (~1.5×) | 33.47% | 20.25% | 1.65 |
| 4yr (2022-2026) | base 200d | 56.24% | 37.37% | 1.50 |
| **16yr (2010-2026)** | base 200d | **33.55%** | **54.92%** | **0.61** |
| 16yr | partial 0.5 | 18.73% | 31.38% | 0.60 |
| 16yr | buy-hold QQQ (no lev) | 19.81% | 35.12% | 0.56 |

**Honest read:** over the full cycle the gated 3× ETF (Calmar 0.61) barely beats
unleveraged buy-and-hold QQQ (0.56). De-levering (`--partial`) cleanly trades CAGR for
DD ~1:1. The 50d second gate whipsaws and does not help. `--lev SOXL` reaches higher
CAGR on bulls but 80%+ DD over the cycle — not recommended.

## Run

```bash
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py --sweep --from 2010-02-11 --to 2026-05-24
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py --sma 200 --out exports/backtests/us/leveraged_regime_tqqq
```
