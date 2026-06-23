# yfinance 10-year S&P 500 backfill + spliced loader — design

**Date:** 2026-06-24
**Status:** Approved (design), pending implementation plan

## Goal

Extend the backtestable price history for the S&P 500 models from the ~4–5 year
eToro window to a full **10-year window (2016-06 → 2026-06)** by back-filling the
older years from real yfinance data, joined per-symbol to the existing eToro feed
into one continuous, returns-faithful series.

## Background / constraints

- The existing daily-bar history lives in `historical_data` under the stored
  label `data_source='yfinance'`. That label is a **storage bucket**, not a live
  yfinance dependency — the bars in it actually come from eToro
  (`tools/pull_etoro_history.py`).
- eToro bars span ~2021-06 → 2026-06; only **2022-05-24 onward** is the
  verified-faithful window (`tools/analysis/verify_cagr.py`).
- eToro prices are price-faithful for almost all tickers **except NFLX and BKNG**,
  whose absolute level is a constant-scaled unit (return-neutral within eToro, but
  it makes a naive join to real prices jump at the seam).
- A separate data bug (phantom weekend/holiday candle rows) was found and fixed in
  the same session: DB cleaned (1,536 rows deleted) and a `load_calendar()`
  trading-day guard added to `india_ports_us/backtest.py`. The extended loader must
  preserve that guard over the 10-year window.

## Decisions (locked during brainstorming)

1. **Seam handling:** ratio-splice into a **separate bucket**. yfinance goes into a
   new `data_source='yfinance_real'` bucket; the eToro `'yfinance'` bucket is left
   untouched (reversible). At backtest load, the older yfinance segment is rescaled
   per symbol by the eToro/real ratio at the join date so the joined series is
   continuous — this auto-corrects the scaled NFLX/BKNG tickers.
2. **Window / join:** yfinance covers **2016-06-01 → 2022-05-24**; eToro is
   authoritative from **2022-05-24** on. Seam sits at the verified-faithful eToro
   start.
3. **Universe:** point-in-time `src/data/symbols/sp500_membership.csv`. Pull every
   symbol it ever lists; log the ones yfinance cannot return (delisted/renamed).

## Components

### Component 1 — `tools/pull_yfinance_history.py` (new, standalone)

Mirrors `tools/pull_etoro_history.py`. Differences:

- Source: `yfinance` with `auto_adjust=True` (split/dividend-adjusted continuous
  series).
- Universe: every distinct symbol in `sp500_membership.csv`.
- Window: 2016-06-01 → 2022-05-24 (CLI `--start` / `--end`, defaults to these).
- Writes to **new bucket** `data_source='yfinance_real'`. Same column set as the
  eToro writer (`symbol,date,timestamp,open,high,low,close,volume,adj_close,
  data_source,api_resolution,is_adjusted`).
- Idempotent per symbol: delete `WHERE symbol=:s AND data_source='yfinance_real'
  AND date BETWEEN window` before insert.
- Emits a coverage report: symbols fetched / missing (unfetchable, likely
  delisted) / row counts → `exports/data/yfinance_backfill/DATA_GAPS.md`.
- Runs on the NUC (DB lives there); `DATABASE_URL` honored, default localhost.

### Component 2 — splice-aware loader (in `tools/models/india_ports_us/backtest.py`)

New `load_panels_spliced(syms, start, end, join="2022-05-24")`:

1. Read both buckets (`yfinance_real` for `date < join`, `yfinance` for
   `date >= join`) for the requested symbols.
2. Per symbol compute the splice ratio at the join date:
   `ratio = etoro_close@join / yfinance_close@join`, using the nearest trading day
   `<= join` present on **both** sides. Scale the older yfinance segment
   (`open/high/low/close`) by `ratio`; volume passes through unscaled.
3. Concatenate older(scaled) + recent(eToro) per symbol; pivot to `cl` (close) and
   `dv` (close×volume).
4. `load_calendar` is extended to union the clean-reference (`AAPL/MSFT/QQQ/SPY`)
   dates across **both** buckets over the 10-year span, weekday-filtered. Reindex
   `cl`/`dv` to it and `ffill`.
5. Gated: the default `load_panels` path is **byte-for-byte unchanged**. Extended
   history is opt-in via a CLI flag (`--extended` / equivalent) that selects
   `load_panels_spliced`. `load_open`/`load_regime` reuse the same calendar via
   `cl.index`, so they inherit the splice and the extended span. The open panel is
   spliced by the same per-symbol ratio.

### Splice edge-cases (at join date)

| Case | Handling |
|---|---|
| Present both sides | Ratio splice as above. |
| Only eToro (listed after join) | Use eToro as-is; no older history. |
| Only yfinance (delisted before join) | Keep yfinance unscaled (no eToro anchor); PIT membership gates it out post-delisting; flag in report. |
| Ratio is zero/garbage (outside [1e-3, 1e3]) | Do not scale; log as suspect seam. NFLX/BKNG large-but-finite ratios are expected (that is the fix). |
| No bar within ±5 trading days of join on either side | Drop symbol from extended history; log. |

## Data flow

```
sp500_membership.csv (PIT)
   |
pull_yfinance_history.py --auto_adjust--> historical_data[data_source='yfinance_real']  (2016-06 -> 2022-05-24)
                                                  |
load_panels_spliced(syms, start, end, join)       |   historical_data[data_source='yfinance']  (eToro, 2021-06 -> 2026-06)
   |- load_calendar: union clean-ref dates (both buckets) -> 10yr trading index
   |- per-symbol ratio splice at join
   `- reindex -> calendar, ffill --> cl, dv (continuous 10yr panels)
                                      |
                              run_n40 / run_retest (unchanged engine) --> 10yr ledger/equity
```

## Testing

- **Splice continuity:** for a faithful ticker (AAPL) and a scaled one (NFLX),
  assert the day-over-day return across the join date has no >40% phantom jump
  (reuse verify_cagr glitch-scan).
- **Ratio neutrality:** scaling a segment by a constant leaves within-segment
  returns unchanged — assert pre/post-splice returns equal for the older segment.
- **Default-path regression:** non-extended `load_panels` output byte-identical to
  current; existing 4yr exports reproduce.
- **Calendar:** extended 10yr calendar has zero weekend/holiday dates.
- **Coverage report:** `DATA_GAPS.md` lists fetched / missing / suspect-seam
  counts.

## Out of scope

- Re-running / regenerating the production 4yr exports (`momentum_sp100`,
  `retest_sp500`) for the weekend-bug fix — tracked separately; uses the same fixed
  engine.
- Changing live-signal observers (they read the recent eToro bucket only; the
  extended history is a backtest-only concern).
- Backfilling non-S&P-500 universes (Nasdaq, India ports).
