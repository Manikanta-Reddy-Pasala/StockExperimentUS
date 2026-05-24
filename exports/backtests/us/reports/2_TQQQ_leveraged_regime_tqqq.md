# Model 2 — TQQQ · leveraged_regime_tqqq

**Mechanism:** index timing with a leveraged ETF (the leverage is inside the ETF — no
margin in your account).
**File:** `tools/models/leveraged_regime_tqqq/backtest.py`
**Live config:** `--sma 200` (all-in TQQQ when risk-on)

## Rules
- **Instrument:** TQQQ (3× Nasdaq-100). Risk-off → cash (or BIL).
- **Regime:** read off the underlying QQQ, NOT TQQQ. Hold TQQQ when QQQ > 200-day SMA,
  else cash. Signal at close of day *t*, applied to *t+1* (no lookahead).
- **Costs:** $0 commission + 8 bps slippage on switches. TQQQ's 0.84% expense +
  volatility decay already in its real prices. Daily MTM DD.
- TQQQ inception 2010-02-11 → only sleeve with a full-cycle (16-year) record.

## Results — LOCKED config (`--sma 200`, all-in), true daily DD

| Window | CAGR | MaxDD | Calmar |
|--------|-----:|------:|-------:|
| 3yr (2023-2026) | 67.94% | 37.37% | 1.82 |
| 4yr (2022-2026) | 56.19% | 37.37% | 1.50 |
| 10yr (2016-2026) | 44.76% | 54.92% | 0.81 |
| 16yr (2010-2026, full cycle) | 33.55% | 54.92% | 0.61 |

DD-control variants (3yr): partial 0.66 → 44.6%/26.1% · partial 0.5 → 33.5%/20.3%.
Reference: buy-hold QQQ (no leverage) 16yr = 19.8%/35.1%/0.56 — leverage barely beats it
risk-adjusted over a full cycle. TQQQ is the highest-DD sleeve; trimmed to 15% in the book.

## Notes
- **Sobering 16-year truth:** gated 3× (Calmar 0.61) barely beats unleveraged buy-hold
  QQQ (0.56). Leverage only shines in the post-2022 window; the 200-day daily gate
  can't catch fast crashes (2020 COVID gap, 2022 grind).
- `--partial` cleanly trades CAGR for DD (~1:1). The 50d second gate whipsaws — skip it.
- `--lev SOXL` reaches higher bull CAGR but 80%+ cycle DD — rejected.
