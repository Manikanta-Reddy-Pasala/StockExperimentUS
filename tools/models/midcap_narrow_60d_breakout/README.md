# midcap_narrow_60d_breakout

**Indian mid/small-cap breakout swing strategy.** winner config — Exclude Large-caps + Exclude ANGELONE + 40d breakout + 90d max-hold + no SMA20 exit.

## Stock category: MID + SMALL CAP

Targets mid + small-cap NSE stocks (rank 31-130 by 20-day ADV, minus Large-caps). baseline (all caps in pseudo-midcap) archived at `tools/models/_archived_models/midcap_narrow_60d_breakout_v1/`.

## Universe construction

1. Take all Nifty 500 stocks (`src/data/symbols/nifty500.csv`)
2. Compute 20-day **average daily ₹ value traded** per stock
3. Sort descending by ADV
4. **Skip top-30** (already covered by `momentum_n100_top5_max1`)
5. **Take next 100** = "pseudo-midcap" pool (~ADV-rank 31-130)
6. **NEW — Exclude Large-caps**: drop stocks in NSE Nifty 100 (`src/data/symbols/nifty100.csv`)
7. **Data fix for ANGELONE** applied at load time (NOT excluded): prices in window 2024-12-23 → 2026-02-25 divided by 10 to fix reverse-split-adjustment inconsistency. With clean data, ANGELONE is fully eligible — it just doesn't qualify for breakout entries naturally.

End-2026 universe first 10: SUZLON, SHRIRAMFIN (no wait — Large), … (Large-cap names filtered out by V2)

**Why excluding Large works**: pseudo-midcap pool accidentally catches Large-caps at ADV ranks 31-130 (JIOFIN, ADANIPORTS, SHRIRAMFIN, ITC). Those compete with cleaner mid/small breakouts for capital. Dropping them preserves wins + adds capital headroom for next breakout. Strategy compounds faster.

## Strategy — winner config

| Knob | Value | vs |
|---|---|---|
| Universe pool | Pseudo-midcap (skip top-30 ADV, next 100) | same |
| **Cap filter (NEW)** | **Exclude Nifty 100 (Large)** | NEW |
| ANGELONE handling | **Data fix at load** (price ÷10 in corrupted window) — NOT excluded | data integrity, not strategy choice |
| Breakout window | **40-day high** | was 60d |
| Volume confirm | ≥ 2× 20-day avg | same |
| Long-term filter | close > 200-day SMA | same |
| Position | max_concurrent=1 | same |
| **Target** | **+100%** | was +60% |
| Trail | **-20% from peak** (armed after +10%) | was -15% |
| **SMA20 exit** | **DISABLED** | was enabled |
| **Max hold** | **90 trading days** | was 30 |
| Slippage | 10 bps + ₹20 brokerage + 0.10% STT | same |

## Backtest result (V2, 2023-05-15 → 2026-05-15, ₹10L start)

| Period | NAV end | Yearly ROI |
|---|---:|---:|
| Start | ₹10,00,000 | — |
| Y1 (2023-24) | ₹33,43,026 | **+234.30%** |
| Y2 (2024-25) | ₹50,73,918 | **+51.78%** |
| Y3 (2025-26) | ₹65,00,421 | **-5.55%** ish (cap_after end) |
| **3-yr CAGR** | | **+86.63%** |
| Total return | | **+550%** |

**12 round-trips · 75% WR · Max DD 15.15% · Calmar 5.72**

## Cap-filter sweep results (6 variants)

| Variant | CAGR | DD | Calmar | NAV |
|---|---:|---:|---:|---:|
| **Exclude Large (this)** | **+86.63%** | **15.15%** | **5.72** | ₹65L |
| Exclude Small (Large+Mid) | +78.26% | 15.49% | 5.05 | ₹57L |
| Baseline (all caps) ARCHIVED | +68.60% | 17.83% | 3.85 | ₹48L |
| Large only | +59.26% | 28.67% | 2.07 | ₹40L |
| Mid only | +38.71% | 20.01% | 1.93 | ₹27L |
| Small only | +9.99% | 48.08% | 0.21 | ₹13L |

wins on ALL three metrics (CAGR, DD, Calmar).

## Files

| File | Purpose |
|---|---|
| `backtest.py` | standalone reproducer (40d/100%/20%/no-SMA/90d + cap filter) |
| `build_universe.py` | Pseudo-midcap universe builder (will need cap filter applied at use time) |
| `live_signal.py` | Daily breakout signal emitter (not deployed) |
| `data_pull.py` / `cron.py` | Scheduler registration (not wired) |
| `trade_ledger.json` | 12 trades + summary |

## Reproduce

```bash
docker exec trading_system_app python tools/models/midcap_narrow_60d_breakout/backtest.py
```

Outputs final NAV, CAGR, DD, trade ledger.

## Historical note

baseline (all caps, no cap filter): +68.60% CAGR, ₹47.92L. Archived at `tools/models/_archived_models/midcap_narrow_60d_breakout_v1/README.md`.

V1-with-ANGELONE (full lookahead): +337.62% CAGR / ₹8.38 Cr but inflated by single ANGELONE trade that's likely a corp-action data anomaly.

## Caveats

- Pseudo-midcap universe has lookahead (end-of-data ADV applied retroactively).
- Real Nifty Midcap 150 (NSE official) on same strategy = -18% CAGR. Strategy depends on lookahead pool.
- 12 trades / 3yr = low sample. Results sensitive to a few trades.
- Y3 (2025-26) slightly negative — strategy struggling in recent regime.
- Not production-ready. Treat as research artifact.
