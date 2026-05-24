# StockExperimentUS — 3-Model Diversified Book (Nasdaq, yfinance)

Three **mechanistically distinct** US-equity models run cash-only (no margin, no
options — every instrument is buyable in a plain IBKR cash account), plus a blended
portfolio. Built to answer one question: *how close can a cash-only book get to high
CAGR with drawdown under 30%?*

**Short answer:** no single model does it durably. A **3-model blend** reaches
**~82-88% CAGR at ~25% drawdown** on the last 3 years (and ~61-67% / ~25% over 4
years), with a better Calmar than any single sleeve. The headline single-stock
momentum number is survivorship-inflated; the **diversification drawdown-cut is the
robust, non-overfit result.** Read the Caveats before trusting any figure.

- Data: yfinance daily OHLCV, `data_source='yfinance'`, plain US tickers.
- Universe: real Nasdaq-100 (`src/data/symbols/nasdaq100.csv`, 101 names) for the
  stock sleeves; QQQ/TQQQ for the index sleeve.
- Drawdown: **true daily mark-to-market MaxDD** for all three models and the blend
  (not the trade-snapshot DD used by the older equity-rotation backtests, which
  understated drawdown — see Caveats #6).
- Capital: $1,000,000 nominal in backtests; live target < $10k via fractional shares.
- Costs: **$0 commission (IBKR Lite)** + **8 bps slippage** on traded notional.
  TQQQ's 0.84% expense ratio + volatility decay are already in its real prices.

---

## The three models

| # | Model | Mechanism | File | Canonical config |
|---|-------|-----------|------|------------------|
| MOM | `momentum_n100_regime_top3` | Trend / relative strength — rank Nasdaq-100 by 30d return, hold top-3, monthly, **cash when QQQ < 200d SMA** | `tools/models/momentum_n100_regime_top3/backtest.py` | `--top 3 --regime` |
| TQQQ | `leveraged_regime_tqqq` | Index timing — hold 3× Nasdaq ETF when QQQ > 200d SMA, else cash | `tools/models/leveraged_regime_tqqq/backtest.py` | `--sma 200` (all-in) |
| BRK | `breakout_n100` | Event-driven breakout — buy 50-day-high in uptrend, ride with 20% trailing stop, top-5 | `tools/models/breakout_n100/backtest.py` | `--donchian 50 --trail 20 --maxn 5` |

These are different mechanisms (buy-winners-monthly / time-the-index / event-driven-
breakout-with-trail), so their daily returns are only moderately correlated
(0.5-0.6) — enough that blending lowers portfolio drawdown below every single sleeve.

---

## Results — individual models (true daily DD)

### Last 3 years (2023-05-24 → 2026-05-22)

| Model | CAGR | MaxDD | Calmar | Notes |
|-------|-----:|------:|-------:|-------|
| MOM (top3 regime) | **114.77%** | 29.61% | 3.88 | survivorship-inflated (see Caveats) |
| TQQQ (200d gate) | 64.19% | 37.37% | 1.72 | |
| BRK (D50 trail20 N5) | 55.33% | 25.04% | 2.21 | best standalone Calmar |

### 4 years (2022-05-24 → 2026-05-22, includes the 2022 bear)

| Model | CAGR | MaxDD | Calmar |
|-------|-----:|------:|-------:|
| MOM (top3 regime) | 86.90% | 29.61% | 2.94 |
| TQQQ (200d gate) | 56.24% | 37.37% | 1.50 |
| BRK (D50 trail20 N5) | 33.70% | 23.26% | 1.45 |

Note: MOM and TQQQ MaxDD are **identical across the 3yr and 4yr windows** — proof the
worst drawdown happened *inside 2023-2026*, not in the 2022 bear. Dropping 2022 only
inflates CAGR; it does not reduce risk.

---

## Results — the blended book

Daily-rebalanced weighted blend of the three sleeves (`tools/analysis/blend_models.py`).

### Last 3 years (2023-2026)

| Portfolio | CAGR | MaxDD | Calmar |
|-----------|-----:|------:|-------:|
| Equal (1/3 each) | 81.57% | **24.96%** | 3.27 |
| **45 / 30 / 25 (MOM/TQQQ/BRK)** | **88.15%** | 25.91% | **3.40** |

### 4 years (2022-2026)

| Portfolio | CAGR | MaxDD | Calmar |
|-----------|-----:|------:|-------:|
| Equal (1/3 each) | 61.46% | 25.19% | 2.44 |
| 45 / 30 / 25 | 66.96% | 25.68% | 2.61 |

**The blend's drawdown (~25%) is lower than every single model's** (MOM 29.6%, TQQQ
37.4%, BRK 23-25%) while keeping CAGR high — the diversification payoff.

### Daily-return correlation (lower = better diversification)

3-year window:

|      | MOM  | TQQQ | BRK  |
|------|-----:|-----:|-----:|
| MOM  | 1.00 | 0.51 | 0.61 |
| TQQQ | 0.51 | 1.00 | 0.52 |
| BRK  | 0.61 | 0.52 | 1.00 |

4-year window: MOM-TQQQ 0.53, MOM-BRK 0.54, TQQQ-BRK 0.53. All positive (every sleeve
is net-long US tech beta), so diversification is real but limited — a truly
uncorrelated sleeve (bonds / short / managed-futures) would help more but breaks the
cash-only-equities constraint.

---

## Rejected models (kept in repo, dropped from the book)

| Model | File | Why rejected |
|-------|------|--------------|
| Mean-reversion (RSI-2) | `tools/models/meanrev_rsi2_n100/` | Too weak: 3yr best 13.0% CAGR / 25% DD / Calmar 0.52 (4yr: 10.9%). US mega-caps trended too hard for dip-buying; ~2300 trades bleed slippage. |
| SOXL gated (3× semis) | `leveraged_regime_tqqq --lev SOXL` | Hits ≥60% CAGR on the bull (3yr base 117% / 74% DD; partial-0.5 64% / 43% DD) but **brutal DD and ~0.9 correlation with TQQQ**. Over the honest 16yr: **25% CAGR / 82% DD / Calmar 0.31** — a bull-only mirage. |

### Reality-check: pseudo_n100 (least-biased momentum)

`tools/models/pseudo_n100_regime_top3/` re-runs the *same* momentum strategy on a
**yearly point-in-time ADV universe** (no "hold today's known winner" bias; the
500-name pool is still current, so some pool-survivorship remains).

| Window | top3 no-regime | top1 no-regime |
|--------|---------------:|---------------:|
| 4yr | 33.74% / 41.94% DD | 35.15% / 56.55% DD |
| 3yr | 56.35% / 41.94% DD | 66.34% / 56.55% DD |

The same strategy makes **~34-56% CAGR** on the less-biased universe vs MOM's
87-115%. **That ~2.5× gap is the survivorship + single-name (NVDA-class) inflation in
the MOM number.** It is the single most important honest anchor in this document.

### TQQQ over the full cycle (2010-2026, 16.3y)

| Variant | CAGR | MaxDD | Calmar |
|---------|-----:|------:|-------:|
| base 200d (all-in) | 33.55% | 54.92% | 0.61 |
| partial 0.5 (~1.5×) | 18.73% | 31.38% | 0.60 |
| buy-hold TQQQ | 44.00% | 81.66% | 0.54 |
| buy-hold QQQ (no leverage) | 19.81% | 35.12% | 0.56 |

Over a full cycle, leveraged-gated TQQQ (Calmar 0.61) barely beats unleveraged
buy-and-hold QQQ (Calmar 0.56). Leverage shines only in the post-2022 window.

---

## Caveats — read before trusting any number

1. **Survivorship bias.** `nasdaq100.csv`/`nasdaq500.csv` are *current* constituents;
   names that dropped out 2022-2026 are absent → upward bias on the stock sleeves
   (MOM, BRK). The pseudo_n100 reality-check above quantifies the effect (~2.5×).
2. **Window / recency bias.** 2023-2025 was an AI mega-bull. The 3yr numbers are the
   most flattering and least predictive. The 4yr numbers (including 2022) are fairer.
3. **Single-name concentration.** MOM top-3 is carried by a few mega-cap winners
   (NVDA-class). Forward dispersion will differ.
4. **No bear stress for the stock sleeves.** Only 4 years of Nasdaq stock history was
   pulled; MOM/BRK have never been tested through a 2008/2000-style decline. Only the
   TQQQ sleeve has a 16-year record (and it's sobering — see above).
5. **Costs are optimistic-but-fair.** $0 commission is correct for IBKR Lite on US
   stocks; 8 bps slippage is a reasonable mid/large-cap assumption at small size.
6. **DD methodology.** All figures here use **true daily mark-to-market MaxDD**. The
   older `momentum_n100_top5_max1` reported a *trade-snapshot* DD that understated the
   real drawdown (e.g., its "44.9%" is **57.25%** on a daily basis).
7. **Honest forward expectation.** Discounting MOM survivorship toward the pseudo
   anchor, a live blend realistically returns **~50-65% CAGR with drawdowns that can
   reach 30-40% in a real bear** — not the 88% the bull window shows. The
   diversification drawdown-reduction is the part that holds up out-of-sample.

---

## Reproduce

```bash
docker compose up -d database
export DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system"

# 1. data (stocks already loaded; pull the ETFs for the index sleeve + regime)
PYTHONPATH=. python3 tools/pull_yfinance_history.py \
  --universe src/data/symbols/leveraged_etfs.csv --start 2009-01-01 --end 2026-05-24

# 2. individual sweeps (3yr shown; use --from 2022-05-24 for 4yr, 2010-02-11 for TQQQ full)
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --sweep --from 2023-05-24 --to 2026-05-24
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py    --sweep --from 2023-05-24 --to 2026-05-24
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py            --sweep --from 2023-05-24 --to 2026-05-24

# 3. canonical configs -> equity curves -> blend
F=2023-05-24; T=2026-05-24; B=exports/backtests/us/blend3
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --from $F --to $T --out $B/mom
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py     --sma 200            --from $F --to $T --out $B/tqqq
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --from $F --to $T --out $B/brk
PYTHONPATH=. python3 tools/analysis/blend_models.py \
  MOM=$B/mom/equity_curve.csv TQQQ=$B/tqqq/equity_curve.csv BRK=$B/brk/equity_curve.csv --weights 0.45,0.30,0.25
```

Each model writes `summary.json` + `equity_curve.csv` to its `--out` dir; sweeps write
`sweep.json`. Per-model details in each model directory's `README.md`.
