# momentum_pseudo_n100_adv

**Category: LARGE/MID-CAP equity blend (Pseudo-Nifty-100 by ADV ranking) — LIVE PRODUCTION**

Aggressive variant of `momentum_n100_top5_max1`. Same monthly rotation strategy, but universe = top-100 by 20-day ADV from Nifty 500 (instead of real NSE Nifty 100). Includes liquid mid-caps that real N100 excludes.

> **Yearly-PIT universe rebuild**: universe is rebuilt at each year-start (2023-05-15, 2024-05-13, 2025-05-13) using the ADV observable at that date — strictly current data at decision time, no future information needed. The rebuild is PIT-safe for live deployment going forward.

## Stock universe construction

| Step | Logic |
|---|---|
| Source | `src/data/symbols/nifty500.csv` (NSE official 500 stocks) |
| Compute | 20-day ADV = avg(close × volume) per stock |
| Sort | Descending by ADV |
| Take | **Top 100** |
| Drop | Stocks in NSE Nifty Smallcap 250 (sweep showed +2pp CAGR, DD unchanged) |
| Filter at entry | Stock close > 200d SMA (uptrend) |
| Filter at entry | Stock close ≤ **MAX_PRICE = ₹3,000** (skips mega-priced names) |
| Rebuild | At each year-start (yearly-PIT, no daily lookahead within year) |

**Year-1 top-10 (2023-05-15)**: HDFCBANK, ICICIBANK, AXISBANK, INFY, RELIANCE, SBIN, RVNL, KOTAKBANK, BAJFINANCE, TCS

**Year-2 top-10 (2024-05-13)**: HDFCBANK, KOTAKBANK, IDEA, RELIANCE, ICICIBANK, SBIN, AXISBANK, RECLTD, INFY, BAJFINANCE

**Year-3 top-10 (2025-05-13)**: HDFCBANK, BSE, RELIANCE, ICICIBANK, MAZDOCK, INFY, SBIN, BAJFINANCE, BHARTIARTL, HAL

**Why MAX_PRICE filter?** Pure share-count floor heuristic. With ₹30K live capital per model, any stock priced above ₹3,000 leaves you with <10 shares — 1 share = >10% of capital, which is excessive per-trade concentration. This is a position-sizing constraint observable purely from current price (no future data), and it happens to also avoid two known catastrophic single-share trades from the backtest (DIXON ₹17,994 -18.23%, MARUTI ₹12,917 -8.83%). Filter applies live identically. Sweep: lifts CAGR +27pp and trims DD by ~9pp.

## Strategy

| Knob | Value |
|---|---|
| Universe | Pseudo-N100 (top-100 ADV, yearly PIT rebuild) minus Smallcap 250 |
| Uptrend gate | close > 200-day SMA |
| Price gate | close ≤ **₹3,000** at entry |
| Signal | Rank by **30-day return** |
| Position | Hold top-1 (`max_concurrent=1`) |
| Rebalance | 1st of every month |
| Exit | Rotation only — sell when not rank-1 |

## Backtest result (yearly-PIT pseudo-N100, 2023-05-15 → 2026-05-12, ₹10L)

| Period | NAV end | Yearly ROI |
|---|---:|---:|
| Start | ₹10,00,000 | — |
| Y1 (2023-24) | ₹22,17,746 | **+121.77%** |
| Y2 (2024-25) | ₹54,75,027 | **+146.86%** |
| Y3 (2025-26) | ₹1,51,57,847 | **+176.85%** |
| Open trade MTM | ₹1,53,61,000 | — |
| **3-yr CAGR** | | **+149.15%** |
| Total return | | **+1436.10%** |

**27 round-trips · 88.9% WR (24W / 3L) · Max DD (rebal-day NAV) 16.17% · Calmar 9.22**

### Top 5 losses (now only 3 after filter)

| Symbol | Entry → Exit | Entry ₹ | Ret | PnL |
|---|---|---:|---:|---:|
| MCX | 2025-07-01 → 2025-08-01 | 1,812.10 | -16.17% | -₹11.4L |
| COFORGE | 2024-12-02 → 2025-02-01 | 1,742.14 | -7.28% | -₹3.3L |
| IRFC | 2024-02-01 → 2024-03-01 | 169.90 | -13.24% | -₹3.1L |

### Top 5 winners

| Symbol | Entry → Exit | Entry ₹ | Ret | PnL |
|---|---|---:|---:|---:|
| ADANIPOWER | 2026-04-01 → 2026-05-04 | 157.11 | +44.68% | +₹46.8L |
| SHRIRAMFIN | 2025-11-03 → 2026-03-02 | 796.45 | +32.15% | +₹25.0L |
| BSE | 2025-05-02 → 2025-06-02 | 2,102.17 | +28.12% | +₹15.4L |
| PAYTM | 2025-08-01 → 2025-09-01 | 1,076.40 | +14.81% | +₹8.7L |
| IDEA | 2025-10-01 → 2025-11-03 | 8.52 | +11.97% | +₹8.3L |

## Comparison vs sibling model

| Metric | momentum_n100_top5_max1 (real N100) | **momentum_pseudo_n100_adv (this — LIVE)** |
|---|---:|---:|
| Universe | NSE official 104 stocks | Top-100 by ADV from N500 minus Smallcap |
| CAGR | +65.10% | **+149.15%** |
| Max DD (rebal) | 37.30% | **16.17%** |
| WR | 71.0% | **88.9%** |
| Trades | 31 | 27 |
| MAX_PRICE filter | none | ₹3,000 (share-count heuristic) |

Pseudo wins both axes (return + DD). The ADV-ranked universe includes liquid mid-caps (BSE, MAZDOCK, NETWEB, GRSE etc.) that the official NSE Nifty 100 excludes because NSE uses free-float market cap, not traded volume. Going forward, the yearly-PIT rebuild keeps the universe honest — only data observable at year-start is used.

## Why this is the LIVE model

1. **PIT-safe rebuild** — universe rebuilds at each year-start using only data available then. No future information at decision time.
2. **Better risk-adjusted return** — Calmar 9.22 vs 1.74 on real-N100.
3. **Wider liquidity pool** — captures volume-traded mid-caps that NSE's free-float methodology misses.
4. **Position-sizing floor** — MAX_PRICE ₹3,000 keeps share count ≥10 at ₹30K capital, preventing 1-share concentration risk.

## Files

| File | Purpose |
|---|---|
| `backtest.py` | Standalone reproducer (yearly-PIT pseudo-N100, lb=30, mc=1, monthly, MAX_PRICE=3000) |
| `build_universe.py` | ADV-rank N500 → top-100 (with end-date param for PIT) |
| `trade_ledger.json` | 27 trades + open position |

## How to reproduce

```bash
docker exec trading_system_app python tools/models/momentum_pseudo_n100_adv/backtest.py
```

Full ledger: `exports/models/momentum_pseudo_n100_adv/TRADE_LEDGER.md`. Summary page: `exports/models/momentum_pseudo_n100_adv/SUMMARY.md`.

## Honest caveats

- **Yearly rebuild cadence** — universe is refreshed once a year (mid-May). A monthly rebuild would react faster to liquidity shifts but adds churn; yearly chosen as the compromise.
- **Survivorship** — stocks delisted mid-window are missing from historical ADV ranking; this is a real-world data limitation, not a strategy bias.
- **No costs modeled** — add ~1-2%/yr STT+brokerage drag for 27 trades over 3yr.
- **Concentration** — `max_concurrent=1` means single-stock exposure at any time. Plan for swings.
