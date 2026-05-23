# Iron Condor & Options Income — Archived Findings

**Period explored:** 2026-05-22 → 2026-05-23
**Outcome:** All options-income variants ABANDONED. Live model stays
`momentum_n100_top5_max1` (equity momentum, +87 % CAGR walk-forward).

This file consolidates ~30 commits' worth of exploration into a single
reference so future sessions can skip re-attempting these dead ends.

---

## 🚨 Top-line critical findings

1. **NSE bhavcopy `volume` = total contracts (a single big trade or many
   small ones look identical).** For real fill assessment use
   `num_trades` (UDiFF only, post-Jul-2024) + `volume × lot × close` as
   traded-value proxy.
2. **NSE `VAL_INLAKH` / `TtlTrfVal` field is NOTIONAL (contracts × lot ×
   strike), NOT actual traded value.** Misleading name; verified by
   inspection. Real traded value = `volume × lot × close`.
3. **Backtest without volume gate = fantasy.** ~57-72 % of historical IC
   entries had ≥ 1 leg with 0 traded contracts on the close price the
   backtest "filled" against. Naive backtest CAGR +1,034 % collapsed to
   +20.6 % once entry day required all 4 legs to have non-zero volume.
4. **No IC variant beats equity momentum at ANY capital level.** Best IC
   = OTM 2 / W 200 / week-2 entry = +10.92 % CAGR / -52.8 % DD. Equity
   momentum = +87 % CAGR / -6 % DD. ~8× edge to momentum.
5. **All viable IC variants are drawdown-heavy.** Even otm20_w150 (lowest
   DD) draws -31 %. The wing geometry is fundamentally risky.

---

## 📊 OTM × Wing grid (FINNIFTY, week-2 entry, 4-leg-volume gate, ₹2L, 5 lots)

| Variant | Trades | WR % | Total % | CAGR % | Max DD % |
|---|---:|---:|---:|---:|---:|
| **otm20_w200** ⭐ best CAGR | 17 | 64.7 | +34.64 | **+10.92** | -52.80 |
| **otm20_w150** ⭐ best DD | 15 | 66.7 | +20.61 | +6.97 | **-31.08** |
| otm20_w300 ⚠️ blown | 16 | 75.0 | +15.41 | +6.03 | **-112.19** |
| otm30_w200 | 13 | 69.2 | -2.37 | -1.67 | -25.05 |
| otm30_w150 | 11 | 63.6 | -12.02 | -8.40 | -24.87 |
| otm40_w300 | 10 | 60.0 | -33.63 | -16.99 | -41.57 |
| otm40_w200 | 11 | 54.5 | -30.18 | -22.08 | -27.51 |
| otm40_w150 | 11 | 45.5 | -32.60 | -23.69 | -38.45 |
| otm30_w300 | 13 | 61.5 | -64.27 | -32.04 | -77.38 |

**Pattern:** OTM 2 row only profitable. OTM 3-4 all negative.

---

## 📅 Entry-week comparison (FINNIFTY OTM 2 / W 150 / 5 lots)

| Entry week | Trades | WR % | Total % | Zero-vol % | Risky-fill % |
|---|---:|---:|---:|---:|---:|
| Week 1 (first weekday) | 10 | 20.0 | **-105.9** | 4.4 | 5.6 |
| **Week 2 (best)** | 15 | 66.7 | +20.6 | 2.1 | 5.7 |
| Week 3 | 27 | 66.7 | -27.3 | 0.1 | 16.6 |

**Reads:**
- Week 1 entry = blown account. Wings just listed, sparse volume → backtest fills against zero-trade contracts.
- Week 2 = sweet spot. Volume thickens, time decay still strong.
- Week 3 = paradoxically worst return despite best liquidity. Too close to expiry, gamma risk dominates.

---

## 🔬 Cross-underlying comparison (NIFTY / FINNIFTY / BANKNIFTY)

At ₹2L capital, peak-safe lot sizing, volume-filtered backtest, best variant per underlying:

| Index | Best variant | CAGR | Max DD | WR |
|---|---|---:|---:|---:|
| FINNIFTY | OTM 2.5 / W 150 / TUE / no-SL | +13.1 % | -4.3 % | 90.9 % |
| NIFTY 50 | OTM 5 / W 500 / THU / no-SL | +10.4 % | -2.3 % | 90.9 % |
| BANKNIFTY | OTM 1.5 / W 500 / WED / no-SL | +10.2 % | -11.2 % | 61.1 % |

⚠️ These numbers come from the FIRST volume-gate version which rejected
the FULL basket if any leg had < 100 vol. Earlier session (commit
ea940ca9 → 95c3ec6b) — superseded by the more honest "require all 4
legs > 0 vol on entry day" gate which collapsed all returns by 50-90 %.

**At ₹5L+ capital these may be revisited.** At ₹2L, equity momentum
wins regardless of underlying choice.

---

## ❌ Stock CSP wheel (formula-based, 19 NSE F&O stocks)

All 5 variants delivered ≤ +1.2 % CAGR over 3 yr:

| Variant | Trades | WR % | CAGR | Max DD |
|---|---:|---:|---:|---:|
| Naked CSP | 22 | 90.9 | **-11.4 %** | -38.4 % |
| Put spread W3 % | ~26 | ~85 | ~+0.3 % | n/a |
| Spread + SL 2.5× | ~26 | ~73 | ~-0.3 % | n/a |
| Naked + SL 2.5× | 5 | 80.0 | +1.2 % | -0.1 % |
| Spread, exclude banks | 31 | 80.6 | +0.7 % | -6.9 % |

**Root causes:**
- 19-stock universe too narrow — 1 MARUTI/SBIN crash wipes 20 wins.
- 2023-2026 was low-IV bull market — credit spreads collect ₹3-5/unit,
  wing cost ≈ 50 % of premium. Net theta tiny.
- Stop-loss exits trigger on intraday spikes that revert.

---

## ⚙️ Live infrastructure kept (still useful)

These code/schema changes survived the cleanup because they're
foundationally sound even if no IC strategy ships:

| Component | What | Why kept |
|---|---|---|
| `migrations/2026_05_23_audit_orders_depth_margin.sql` | +6 columns on audit_orders | Live audit applies regardless of strategy |
| `migrations/2026_05_23_historical_options_trades_turnover.sql` | num_trades + turnover_lakh | Liquidity analysis foundation |
| `src/models/audit_models.py` | depth-snapshot + margin columns | Live executor writes them |
| `src/services/audit_service.py` | optional kwargs for depth/margin | Equity callers unchanged |
| `tools/live/option_depth_check.py` | depth-gate + LIMIT-walk + tier scaling | Used by `fyers_executor_options.py` |
| `tools/live/fyers_executor_options.py` | F&O multi-leg executor | Used if any options strategy revived |
| `tools/shared/prefetch_bhav.py` | NSE UDiFF ingester with num_trades + turnover_lakh | Backfills `historical_options` columns |

## 🗑️ Deleted (with this commit)

- `tools/models/finnifty_ic_otm4_w300_lots5/` (entire folder — all sweep/run scripts)
- `exports/models/finnifty_ic_otm4_w300_lots5/` (entire folder — all CSV/SUMMARY)
- All scripts referenced ~30 commits of dead-end exploration. Re-deriving any of them is straightforward from this archive.

---

## 🔄 NSE bhavcopy column gotchas (for next ingester)

| Field | OLD format pre-2024-07-07 | UDiFF post-2024-07-07 |
|---|---|---|
| Contracts traded | `r[10]` CONTRACTS | `TtlTradgVol` |
| Open interest | `r[12]` OPEN_INT | `OpnIntrst` |
| Notional (lakhs) | `r[11]` VAL_INLAKH | `TtlTrfVal` ⚠️ not "TtlTrnvrInRsrL" |
| Number of trades | NOT AVAILABLE | `TtlNbOfTxsExctd` |
| Date | `r[14]` TIMESTAMP (DD-MON-YYYY) | `TradDt` (YYYY-MM-DD) |

**`turnover_lakh` column = NOTIONAL not traded value.** Compute real
traded value as `volume × lot × close`. Mislabeled but kept for raw NSE
parity.

`historical_options.turnover_lakh` is `NUMERIC(20, 2)` — needed widening
from initial `NUMERIC(14, 2)` because UDiFF emits raw notionals exceeding
10^12 lakhs on highly-liquid days.

---

## 🎯 If you ever want to revisit options income

Prerequisites:
1. **Capital ≥ ₹5L** — absolute rupees scale linearly so edge becomes meaningful.
2. **Volume gate at entry IS mandatory.** All 4 legs must have actual trades on entry day. No exceptions. Fantasy fills will mislead.
3. **Test STOP-loss variations.** No-SL won early sweeps but with proper volume gate, results may shift. Tested only 3× SL with 4-leg gate.
4. **Try DTE windows other than ~25-30 days** — closer-to-expiry weekly cycles may collect theta faster but require more execution per month.
5. **Try Iron Butterfly instead of Iron Condor.** ATM short + tight wings — different risk/reward profile. Never tested.

**Reproduce final OTM × wing grid** (if scripts deleted — re-derive
from `tools/shared/prefetch_bhav.py` ingester + sweep template; the
backtest engine is simple enough to re-write in ~300 lines):

```python
# Pseudo-code reminder:
# 1. for each monthly expiry: pick week-2 first day with all 4 legs vol > 0
# 2. enter at close + tiered slip
# 3. walk daily close → exit at 3x credit stop OR expiry intrinsic
# 4. record daily volume per leg for audit
# 5. require strictly volume > 0 on entry day (not on exit day)
```

---

## 📝 Commits archived in this finding doc

Range: `e70f46bc` → `ea940ca9` (2026-05-23). All in `origin/main`.

Key milestones:
- `e70f46bc` audit_orders +6 depth/margin columns
- `43c9c218` compute_ic_margin SPAN+exposure formula
- `e6961587` volume-aware limit_walk + ₹2L peak-safe rescale
- `c146e40b` first volume-filter in backtest (later relaxed)
- `527e35ff` every-weekday entry fallthrough
- `bfbdb02e` exhaustive 1620-backtest sweep
- `33ac126b` stock CSP wheel ABANDONED
- `9efaeaf2` require non-zero volume on ALL 4 legs at entry day (the honest gate)
- `9d7163f4` NSE VAL_INLAKH = NOTIONAL not traded value
- `ea940ca9` OTM × wing 3x3 grid — OTM 2 / W 200 wins (+10.92 % CAGR)

---

## ✅ Live recommendation (unchanged from session start)

**`momentum_n100_top5_max1`** — equity momentum rotation on Nifty 100.
- Backtest: +87 % CAGR, -6 % DD, walk-forward validated
- Live: running prod via `tools/live/fyers_executor.py`, ₹30k cap per model

Don't switch to any IC config. Don't re-attempt CSP wheel at <₹5L
capital. Don't believe headline-CAGR numbers from any options backtest
that doesn't enforce a 4-leg-volume gate at entry day.
