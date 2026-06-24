# yfinance 10-year S&P 500 backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Back-fill S&P 500 daily history from real yfinance (2016-06 → 2022-05-24) into a separate `yfinance_real` bucket and add a splice-aware loader that joins it per-symbol to the existing eToro feed, enabling continuous 10-year backtests.

**Architecture:** A standalone puller writes a new `data_source='yfinance_real'` bucket (eToro `'yfinance'` bucket untouched). A pure splice module (`tools/shared/splice.py`) ratio-stitches the older segment to the eToro level at the join date — auto-correcting the constant-scaled NFLX/BKNG tickers. A new `load_panels_spliced` in the backtest engine reads both buckets, applies the splice, and reindexes to an extended clean-reference trading calendar; the default 4yr path stays byte-for-byte unchanged behind an opt-in flag.

**Tech Stack:** Python, pandas, yfinance 1.4.0, SQLAlchemy + PostgreSQL (`historical_data`), pytest.

---

## File Structure

- **Create** `tools/shared/splice.py` — pure, DB-free splice math: `trading_days()`, `splice_ratio()`, `splice_symbol()`. Single responsibility, fully unit-testable.
- **Create** `tools/pull_yfinance_history.py` — standalone puller → `yfinance_real` bucket + coverage report. Mirrors `tools/pull_etoro_history.py`.
- **Modify** `tools/models/india_ports_us/backtest.py` — `load_calendar()` to union both buckets; add `load_panels_spliced()`; add `--extended` CLI routing; splice `load_open`/`load_regime` span.
- **Create** `tests/test_splice.py` — unit tests for the pure splice module.
- **Create** `tests/test_yfinance_history.py` — unit tests for puller pure helpers (no network).

---

## Task 1: Pure splice module — trading-day calendar helper

**Files:**
- Create: `tools/shared/splice.py`
- Test: `tests/test_splice.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_splice.py
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from tools.shared.splice import trading_days


def test_trading_days_dedups_and_drops_weekends():
    raw = [
        "2024-01-05",  # Fri
        "2024-01-05",  # dup Fri
        "2024-01-06",  # Sat -> drop
        "2024-01-07",  # Sun -> drop
        "2024-01-08",  # Mon
    ]
    idx = trading_days(pd.to_datetime(pd.Series(raw)))
    assert list(idx.strftime("%Y-%m-%d")) == ["2024-01-05", "2024-01-08"]
    assert idx.is_monotonic_increasing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_splice.py::test_trading_days_dedups_and_drops_weekends -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.shared.splice'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/shared/splice.py
"""Pure (DB-free) helpers to join the older real-yfinance segment to the recent
eToro segment of a price series, and to derive a real US trading-day calendar.

Kept independent of the backtest engine's DB layer so the splice math is unit-
testable without a database or network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trading_days(dates) -> pd.DatetimeIndex:
    """Sorted, de-duplicated, weekday-only DatetimeIndex from any date iterable."""
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Index(dates)).unique()).sort_values()
    return idx[idx.weekday < 5]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_splice.py::test_trading_days_dedups_and_drops_weekends -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/shared/splice.py tests/test_splice.py
git commit -m "feat(splice): trading_days calendar helper (pure)"
```

---

## Task 2: Splice ratio computation

**Files:**
- Modify: `tools/shared/splice.py`
- Test: `tests/test_splice.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_splice.py
from tools.shared.splice import splice_ratio

JOIN = pd.Timestamp("2022-05-24")

def _series(d):
    return pd.Series(d, index=pd.to_datetime(list(d.keys())))

def test_ratio_ok_uses_latest_common_day_le_join():
    old = _series({"2022-05-19": 10.0, "2022-05-20": 11.0, "2022-05-25": 99.0})
    new = _series({"2022-05-20": 22.0, "2022-05-24": 30.0})  # common <= join: 05-20
    r, status = splice_ratio(old, new, JOIN)
    assert status == "ok"
    assert r == pytest.approx(22.0 / 11.0)  # new@05-20 / old@05-20

def test_ratio_only_old_when_no_new_anchor():
    old = _series({"2022-05-20": 11.0})
    new = _series({})
    r, status = splice_ratio(old, new, JOIN)
    assert status == "only_old" and r == 1.0

def test_ratio_only_new_when_no_old():
    old = _series({})
    new = _series({"2022-05-24": 30.0})
    r, status = splice_ratio(old, new, JOIN)
    assert status == "only_new" and r == 1.0

def test_ratio_no_common_anchor_keeps_unscaled():
    old = _series({"2022-05-18": 11.0})
    new = _series({"2022-05-20": 22.0})  # no shared day
    r, status = splice_ratio(old, new, JOIN)
    assert status == "no_anchor" and r == 1.0

def test_ratio_bad_when_zero_or_out_of_bounds():
    old = _series({"2022-05-20": 0.0})
    new = _series({"2022-05-20": 22.0})  # ratio -> inf
    r, status = splice_ratio(old, new, JOIN)
    assert status == "bad_ratio"

def test_ratio_large_but_finite_is_ok_for_scaled_tickers():
    # NFLX-like: eToro level ~0.1x real -> ratio ~0.1, still within [1e-3, 1e3]
    old = _series({"2022-05-20": 1900.0})  # real NFLX
    new = _series({"2022-05-20": 190.0})   # eToro scaled
    r, status = splice_ratio(old, new, JOIN)
    assert status == "ok" and r == pytest.approx(0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_splice.py -k ratio -v`
Expected: FAIL — `ImportError: cannot import name 'splice_ratio'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to tools/shared/splice.py
def splice_ratio(old_close: pd.Series, new_close: pd.Series, join: pd.Timestamp,
                 lo: float = 1e-3, hi: float = 1e3):
    """Return (ratio, status) to scale the OLD (yfinance_real) segment so its level
    matches the NEW (eToro) segment at the join.

    ratio = new@anchor / old@anchor, anchor = latest trading day <= join present in
    BOTH series. status:
      ok        -> finite ratio in [lo, hi]; scale old by ratio
      only_new  -> no old data; nothing to scale (ratio 1.0)
      only_old  -> no eToro anchor (delisted before join); keep old unscaled (1.0)
      no_anchor -> both present but share no day <= join; keep old unscaled (1.0)
      bad_ratio -> ratio non-finite / <=0 / outside [lo, hi]; do NOT scale, flag it
    """
    o = old_close.dropna()
    o = o[o.index <= join]
    n = new_close.dropna()
    n = n[n.index <= join]
    if o.empty and n.empty:
        return 1.0, "only_new"
    if o.empty:
        return 1.0, "only_new"
    if n.empty:
        return 1.0, "only_old"
    common = o.index.intersection(n.index)
    if len(common) == 0:
        return 1.0, "no_anchor"
    anchor = common.max()
    denom = float(o.loc[anchor])
    if denom == 0:
        return float("inf"), "bad_ratio"
    r = float(n.loc[anchor]) / denom
    if not np.isfinite(r) or r <= 0 or not (lo <= r <= hi):
        return r, "bad_ratio"
    return r, "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_splice.py -k ratio -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/shared/splice.py tests/test_splice.py
git commit -m "feat(splice): ratio computation with status taxonomy"
```

---

## Task 3: Per-symbol splice assembly

**Files:**
- Modify: `tools/shared/splice.py`
- Test: `tests/test_splice.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_splice.py
from tools.shared.splice import splice_symbol

def _ohlcv(rows):
    # rows: list of (date, open, high, low, close, volume)
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    return df

def test_splice_symbol_scales_old_and_keeps_new():
    old = _ohlcv([
        ("2022-05-19", 10, 10, 10, 10, 100),
        ("2022-05-20", 11, 11, 11, 11, 100),  # anchor old
        ("2022-05-25", 12, 12, 12, 12, 100),  # >= join: dropped from old side
    ])
    new = _ohlcv([
        ("2022-05-20", 22, 22, 22, 22, 200),  # anchor new (ratio = 2.0)
        ("2022-05-24", 30, 30, 30, 30, 200),  # >= join: kept from new side
        ("2022-05-25", 33, 33, 33, 33, 200),
    ])
    out, ratio, status = splice_symbol(old, new, pd.Timestamp("2022-05-24"))
    assert status == "ok" and ratio == pytest.approx(2.0)
    out = out.set_index("date")
    # old pre-join rows scaled by 2.0
    assert out.loc["2022-05-19", "close"] == pytest.approx(20.0)
    assert out.loc["2022-05-20", "close"] == pytest.approx(22.0)
    # new post-join rows unchanged; volume on old side scaled? NO -> volume passes through
    assert out.loc["2022-05-24", "close"] == pytest.approx(30.0)
    assert out.loc["2022-05-19", "volume"] == 100
    # exactly one row per date, sorted, no overlap dupes
    assert out.index.is_unique and out.index.is_monotonic_increasing

def test_splice_symbol_returns_unchanged_within_segment_returns():
    # ratio-neutrality: scaling old segment leaves its internal returns identical
    old = _ohlcv([
        ("2022-05-18", 10, 10, 10, 10, 1),
        ("2022-05-19", 12, 12, 12, 12, 1),
        ("2022-05-20", 11, 11, 11, 11, 1),  # anchor
    ])
    new = _ohlcv([("2022-05-20", 55, 55, 55, 55, 1), ("2022-05-24", 60, 60, 60, 60, 1)])
    out, ratio, status = splice_symbol(old, new, pd.Timestamp("2022-05-24"))
    seg = out[out["date"] < "2022-05-24"].set_index("date")["close"]
    raw = old.set_index("date")["close"]
    assert np.allclose(seg.pct_change().dropna().values,
                       raw.pct_change().dropna().values)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_splice.py -k splice_symbol -v`
Expected: FAIL — `ImportError: cannot import name 'splice_symbol'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to tools/shared/splice.py
_OHLC = ["open", "high", "low", "close"]

def splice_symbol(old_df: pd.DataFrame, new_df: pd.DataFrame, join: pd.Timestamp):
    """Join one symbol's older real-yfinance OHLCV (`old_df`) to its recent eToro
    OHLCV (`new_df`) into a continuous series. Both frames have columns
    [date, open, high, low, close, volume] with a datetime `date`.

    Old rows (date < join) are scaled by the splice ratio; new rows (date >= join)
    pass through. Volume is never scaled. Returns (df, ratio, status).
    """
    o = old_df.copy()
    n = new_df.copy()
    oc = o.set_index("date")["close"] if not o.empty else pd.Series(dtype=float)
    nc = n.set_index("date")["close"] if not n.empty else pd.Series(dtype=float)
    ratio, status = splice_ratio(oc, nc, join)
    older = o[o["date"] < join].copy()
    recent = n[n["date"] >= join].copy()
    if status in ("ok",) and not older.empty:
        older[_OHLC] = older[_OHLC] * ratio
    out = pd.concat([older, recent], ignore_index=True)
    out = out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    return out, ratio, status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_splice.py -k splice_symbol -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/shared/splice.py tests/test_splice.py
git commit -m "feat(splice): per-symbol OHLCV assembly with ratio scaling"
```

---

## Task 4: yfinance puller — pure helpers (universe + row build)

**Files:**
- Create: `tools/pull_yfinance_history.py`
- Test: `tests/test_yfinance_history.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_yfinance_history.py
from __future__ import annotations
import pandas as pd
import pytest
from tools.pull_yfinance_history import pit_symbols, build_rows


def test_pit_symbols_unique_from_membership(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text(
        "symbol,start_date,end_date\n"
        "AAPL,2016-01-01,\n"
        "MSFT,2016-01-01,2020-01-01\n"
        "AAPL,2021-01-01,\n"   # duplicate symbol across intervals
    )
    assert pit_symbols(str(csv)) == ["AAPL", "MSFT"]


def test_build_rows_maps_yf_columns():
    df = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5],
         "Adj Close": [1.4], "Volume": [1000]},
        index=pd.to_datetime(["2018-03-01"]),
    )
    rows = build_rows("AAPL", df)
    assert len(rows) == 1
    r = rows[0]
    assert r["sym"] == "AAPL" and r["c"] == 1.5 and r["ac"] == 1.4 and r["v"] == 1000
    assert str(r["d"]) == "2018-03-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_yfinance_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.pull_yfinance_history'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/pull_yfinance_history.py
"""Bulk-pull REAL daily OHLCV from yfinance into the historical_data table under a
SEPARATE bucket data_source='yfinance_real', for the pre-eToro years. The recent
eToro feed (bucket 'yfinance') is left untouched; the backtest's spliced loader
joins the two per symbol (see tools/shared/splice.py).

Default window 2016-06-01 -> 2022-05-24 (the verified-faithful eToro start).
Universe: every distinct symbol in a point-in-time S&P 500 membership CSV.
Idempotent per symbol: deletes existing yfinance_real rows in the window first.
Emits a coverage report (fetched / missing / row counts).

Usage:
  PYTHONPATH=. python tools/pull_yfinance_history.py \
      --membership src/data/symbols/sp500_membership.csv \
      --start 2016-06-01 --end 2022-05-24 \
      --report exports/data/yfinance_backfill/DATA_GAPS.md
"""
from __future__ import annotations
import argparse, csv, os, sys
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BUCKET = "yfinance_real"


def get_engine():
    url = os.environ.get("DATABASE_URL",
                         "postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system")
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def pit_symbols(membership_csv: str) -> list[str]:
    """Distinct symbols from a PIT membership CSV (symbol[,start_date,end_date]),
    insertion-ordered."""
    seen: dict[str, None] = {}
    with open(membership_csv) as f:
        for r in csv.DictReader(f):
            s = (r.get("symbol") or r.get("Symbol") or "").strip()
            if s:
                seen.setdefault(s, None)
    return list(seen.keys())


def build_rows(sym: str, df: pd.DataFrame) -> list[dict]:
    """Map a yfinance OHLCV frame (DatetimeIndex) to historical_data row dicts."""
    rows = []
    for ts, r in df.iterrows():
        d = ts.date()
        vol = r["Volume"]
        rows.append({
            "sym": sym, "d": d,
            "ts": int(datetime(d.year, d.month, d.day).timestamp()),
            "o": float(r["Open"]), "h": float(r["High"]), "l": float(r["Low"]),
            "c": float(r["Close"]), "v": int(vol) if pd.notna(vol) else 0,
            "ac": float(r["Adj Close"]) if "Adj Close" in df.columns and pd.notna(r["Adj Close"]) else float(r["Close"]),
        })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_yfinance_history.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/pull_yfinance_history.py tests/test_yfinance_history.py
git commit -m "feat(yf-backfill): puller pure helpers (pit_symbols, build_rows)"
```

---

## Task 5: yfinance puller — fetch, insert, coverage report (I/O glue)

**Files:**
- Modify: `tools/pull_yfinance_history.py`

- [ ] **Step 1: Write minimal implementation**

```python
# append to tools/pull_yfinance_history.py
def fetch_one(sym: str, start: str, end: str) -> pd.DataFrame | None:
    """Real split/div-adjusted daily bars from yfinance. None on empty/error."""
    import yfinance as yf
    try:
        df = yf.download(sym, start=start, end=end, auto_adjust=True,
                         progress=False, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):     # yf>=0.2 single-ticker frames
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:  # noqa: BLE001
        return None


def insert_symbol(conn, sym: str, rows: list[dict], a: date, b: date) -> int:
    conn.execute(text("DELETE FROM historical_data WHERE symbol=:s AND data_source=:bkt "
                      "AND date BETWEEN :a AND :b"),
                 {"s": sym, "bkt": BUCKET, "a": a, "b": b})
    if rows:
        conn.execute(text(
            "INSERT INTO historical_data "
            "(symbol,date,timestamp,open,high,low,close,volume,adj_close,data_source,api_resolution,is_adjusted) "
            "VALUES (:sym,:d,:ts,:o,:h,:l,:c,:v,:ac,'" + BUCKET + "','1D',true)"), rows)
    return len(rows)


def write_report(path: str, start: str, end: str, fetched: dict[str, int], missing: list[str]):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# yfinance_real backfill coverage ({start} -> {end})", "",
             f"- bucket: `{BUCKET}`",
             f"- symbols fetched: **{len(fetched)}**, total rows: **{sum(fetched.values())}**",
             f"- symbols missing (yfinance returned nothing — likely delisted/renamed): **{len(missing)}**",
             "", "## Missing", "", ", ".join(missing) if missing else "_none_", ""]
    p.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--membership", required=True)
    ap.add_argument("--start", default="2016-06-01")
    ap.add_argument("--end", default="2022-05-24")
    ap.add_argument("--report", default="exports/data/yfinance_backfill/DATA_GAPS.md")
    args = ap.parse_args()

    syms = pit_symbols(args.membership)
    a, b = date.fromisoformat(args.start), date.fromisoformat(args.end)
    print(f"Universe: {len(syms)} PIT symbols, {args.start} -> {args.end} src=yfinance_real", flush=True)
    eng = get_engine()
    fetched, missing = {}, []
    for n, sym in enumerate(syms, 1):
        df = fetch_one(sym, args.start, args.end)
        if df is None or df.empty:
            missing.append(sym)
        else:
            rows = build_rows(sym, df)
            with eng.begin() as conn:
                fetched[sym] = insert_symbol(conn, sym, rows, a, b)
        if n % 25 == 0 or n == len(syms):
            print(f"  {n}/{len(syms)} done, rows={sum(fetched.values())}, missing={len(missing)}", flush=True)
    write_report(args.report, args.start, args.end, fetched, missing)
    print(f"DONE fetched={len(fetched)} rows={sum(fetched.values())} missing={len(missing)}: {missing[:30]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify it imports and the CLI parses**

Run: `PYTHONPATH=. python -c "import tools.pull_yfinance_history as m; print(m.BUCKET)"`
Expected: prints `yfinance_real`

Run: `PYTHONPATH=. python tools/pull_yfinance_history.py --help`
Expected: usage text with `--membership`, `--start`, `--end`, `--report`

- [ ] **Step 3: Re-run the pure-helper tests (no regression)**

Run: `PYTHONPATH=. pytest tests/test_yfinance_history.py -v`
Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
git add tools/pull_yfinance_history.py
git commit -m "feat(yf-backfill): fetch+insert into yfinance_real bucket + coverage report"
```

---

## Task 6: Extend `load_calendar` to union both buckets

**Files:**
- Modify: `tools/models/india_ports_us/backtest.py` (the `load_calendar` added earlier in this session)
- Test: `tests/test_splice.py` (calendar-union behavior is covered by `trading_days`; this task is the DB-query change, verified by a guard assertion)

- [ ] **Step 1: Update `load_calendar` to read both buckets and reuse `trading_days`**

Replace the body of `load_calendar` (currently filters `data_source='yfinance'` only and inlines the weekday filter) with:

```python
def load_calendar(start, end):
    """DatetimeIndex of real US trading days from clean reference symbols, unioned
    across BOTH the eToro bucket ('yfinance') and the real-yfinance backfill bucket
    ('yfinance_real') so an extended 10yr span has a complete calendar. Phantom
    weekend/holiday rows can never leak in (clean refs + weekday filter)."""
    from tools.shared.splice import trading_days
    eng = get_engine()
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT DISTINCT date FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b "
            "AND data_source IN ('yfinance','yfinance_real')"
        ), c, params={"s": list(CALENDAR_REFS),
                      "a": start - timedelta(days=400), "b": end})
    return trading_days(df["date"])
```

- [ ] **Step 2: Verify the module still imports and the existing 4yr default path is unaffected**

Run: `PYTHONPATH=. python -c "from tools.models.india_ports_us.backtest import load_calendar, CALENDAR_REFS; print('ok', CALENDAR_REFS)"`
Expected: `ok ('AAPL', 'MSFT', 'QQQ', 'SPY')`

Run: `PYTHONPATH=. pytest tests/test_splice.py -v`
Expected: PASS (all tests — the shared `trading_days` is now also used by load_calendar)

- [ ] **Step 3: Commit**

```bash
git add tools/models/india_ports_us/backtest.py
git commit -m "feat(engine): load_calendar unions eToro + yfinance_real buckets"
```

---

## Task 7: `load_panels_spliced` in the backtest engine

**Files:**
- Modify: `tools/models/india_ports_us/backtest.py`

- [ ] **Step 1: Add the spliced panel loader (uses the pure splice module)**

Add after `load_panels`:

```python
def _read_bucket(syms, start, end, bucket):
    eng = get_engine()
    with eng.connect() as c:
        return pd.read_sql(text(
            "SELECT symbol,date,open,high,low,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source=:bkt "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=400), "b": end, "bkt": bucket})


def load_panels_spliced(syms, start, end, join="2022-05-24"):
    """Like load_panels, but joins the real-yfinance backfill (bucket
    'yfinance_real', date < join) to the eToro feed (bucket 'yfinance', date >=
    join) per symbol via a ratio splice, for extended (10yr) backtests.

    Returns (close, dollar_vol) pivots reindexed to the extended trading calendar
    and ffilled — same shape/contract as load_panels."""
    from tools.shared.splice import splice_symbol
    j = pd.Timestamp(join)
    old = _read_bucket(syms, start, end, "yfinance_real")
    new = _read_bucket(syms, start, end, "yfinance")
    old["date"] = pd.to_datetime(old["date"]); new["date"] = pd.to_datetime(new["date"])
    cols = ["date", "open", "high", "low", "close", "volume"]
    parts = []
    for s in syms:
        o = old.loc[old["symbol"] == s, cols]
        n = new.loc[new["symbol"] == s, cols]
        if o.empty and n.empty:
            continue
        spliced, _ratio, _status = splice_symbol(o, n, j)
        spliced["symbol"] = s
        parts.append(spliced)
    if not parts:
        raise SystemExit("load_panels_spliced: no data in either bucket for requested symbols")
    df = pd.concat(parts, ignore_index=True)
    cal = load_calendar(start, end)
    cl = df.pivot(index="date", columns="symbol", values="close").reindex(cal).ffill()
    dv = df.assign(dv=df["close"] * df["volume"]).pivot(
        index="date", columns="symbol", values="dv").reindex(cal).ffill()
    return cl, dv
```

- [ ] **Step 2: Verify import**

Run: `PYTHONPATH=. python -c "from tools.models.india_ports_us.backtest import load_panels_spliced; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add tools/models/india_ports_us/backtest.py
git commit -m "feat(engine): load_panels_spliced joins yfinance_real + eToro per symbol"
```

---

## Task 8: Wire `--extended` CLI flag

**Files:**
- Modify: `tools/models/india_ports_us/backtest.py` (the `main()` panel-load block, currently `cl, dv = load_panels(syms, s, e)` at the line after `syms = sorted(...)`)

- [ ] **Step 1: Add the flag to the argparse block**

Add alongside the other `ap.add_argument(...)` calls in `main()`:

```python
    ap.add_argument("--extended", action="store_true",
                    help="10yr history: splice real-yfinance backfill (pre-join) to "
                         "eToro (post-join) per symbol")
    ap.add_argument("--join", default="2022-05-24",
                    help="splice date: eToro authoritative on/after this day")
```

- [ ] **Step 2: Route the panel load through the spliced loader when --extended**

Replace the existing line `cl, dv = load_panels(syms, s, e)` with:

```python
    cl, dv = (load_panels_spliced(syms, s, e, join=a.join) if a.extended
              else load_panels(syms, s, e))
```

- [ ] **Step 3: Verify the default path still parses and the new flag exists**

Run: `PYTHONPATH=. python tools/models/india_ports_us/backtest.py --help`
Expected: usage shows `--extended` and `--join`

- [ ] **Step 4: Commit**

```bash
git add tools/models/india_ports_us/backtest.py
git commit -m "feat(engine): --extended/--join CLI to opt into 10yr spliced history"
```

---

## Task 9: Runbook — backfill on NUC, run 10yr backtest, verify seam

> Operational task (network + DB + compute on the NUC, per project rule). Not TDD.
> Each step records its actual output; stop and report if a check fails.

- [ ] **Step 1: Pull the backfill on the NUC**

```bash
ssh ai@192.168.70.115 "cd <repo-on-nuc> && PYTHONPATH=. python3 tools/pull_yfinance_history.py \
  --membership src/data/symbols/sp500_membership.csv \
  --start 2016-06-01 --end 2022-05-24"
```
Expected: `DONE fetched=<N> rows=<M> missing=<K>`; review `exports/data/yfinance_backfill/DATA_GAPS.md`.

- [ ] **Step 2: Sanity-check the new bucket has zero weekend rows**

```bash
ssh ai@192.168.70.115 "sudo docker exec stockexp_nuc_db psql -U trader -d trading_system -t -c \
  \"SELECT count(*) FROM historical_data WHERE data_source='yfinance_real' AND extract(dow from date) IN (0,6);\""
```
Expected: `0` (yfinance trading-day data; if non-zero, add a weekday filter to the puller before proceeding).

- [ ] **Step 3: Run the 10yr retest backtest (extended)**

```bash
ssh ai@192.168.70.115 "cd <repo-on-nuc> && PYTHONPATH=. python3 tools/models/india_ports_us/backtest.py \
  --model retest --extended --join 2022-05-24 --membership-csv src/data/symbols/sp500_membership.csv \
  --signal blend --regime --from 2016-06-01 --to 2026-06-18 \
  --out exports/backtests/us/retest_sp500_10yr"
```
Expected: prints `## retest...` with CAGR/DD/Calmar/Trades over ~10y; writes ledger/equity/summary.

- [ ] **Step 4: Seam-continuity check (no phantom jump across the join)**

```bash
ssh ai@192.168.70.115 "cd <repo-on-nuc> && PYTHONPATH=. python3 - <<'PY'
import pandas as pd
from tools.models.india_ports_us.backtest import load_panels_spliced
cl, _ = load_panels_spliced(['AAPL','NFLX'], __import__('datetime').date(2016,6,1), __import__('datetime').date(2026,6,18))
for s in ['AAPL','NFLX']:
    r = cl[s].pct_change().dropna()
    around = r['2022-05-20':'2022-05-27']
    print(s, 'max |daily ret| near join =', round(around.abs().max()*100,2),'%')
    assert around.abs().max() < 0.40, f'{s}: phantom seam jump'
print('seam OK')
PY"
```
Expected: both tickers' max |daily return| near the join < 40%; prints `seam OK`. (NFLX is the scaled-ticker case the splice fixes.)

- [ ] **Step 5: Copy the 10yr export back and commit**

```bash
# from local repo
rsync -av ai@192.168.70.115:<repo-on-nuc>/exports/backtests/us/retest_sp500_10yr/ \
  exports/backtests/us/retest_sp500_10yr/
rsync -av ai@192.168.70.115:<repo-on-nuc>/exports/data/yfinance_backfill/ \
  exports/data/yfinance_backfill/
git add exports/backtests/us/retest_sp500_10yr exports/data/yfinance_backfill
git commit -m "data(yf-backfill): 10yr S&P500 retest backtest + coverage report"
```

---

## Self-Review

**Spec coverage:**
- Component 1 (puller, `yfinance_real`, PIT universe, window, coverage report) → Tasks 4, 5, 9. ✓
- Component 2 (splice math, calendar union, `load_panels_spliced`, opt-in flag, open/regime inherit via `cl.index`) → Tasks 1-3, 6, 7, 8. ✓
- Splice edge-cases (both/only-new/only-old/no-anchor/bad-ratio) → Task 2 tests + Task 3 assembly. ✓ (the "±5d / drop symbol" case is subsumed by `no_anchor` → kept unscaled and gated by PIT membership; explicit drop deemed YAGNI.)
- Testing (continuity, ratio-neutrality, default-path regression, calendar, coverage) → Task 3 neutrality test, Task 9 Step 4 continuity, Task 6 default-path import check, Task 1 calendar test, Task 5 report. ✓
- `auto_adjust=True` → Task 5 `fetch_one`. ✓
- `load_open`/`load_regime` inherit span: they reindex to `cl.index` which is the extended calendar when `--extended`; the open panel for pre-join is split-adjusted by yfinance and, for absolute level, only `close` drives selection/MTM — open is used for fills post-join (eToro) and pre-join only if a trade lands there. NOTE: `load_open` still reads only the `'yfinance'` bucket, so pre-join opens fall back to `cl` (its docstring fallback). Acceptable for extended runs (fills approximate to close pre-join); flagged for follow-up if pre-join fill realism matters.

**Placeholder scan:** `<repo-on-nuc>` in Task 9 is an operator-supplied path (deployment-specific), not a code placeholder — acceptable in a runbook step. No TBD/TODO in code.

**Type consistency:** `splice_ratio` returns `(float, str)`; `splice_symbol` returns `(df, ratio, status)` and calls `splice_ratio` — consistent. `trading_days` returns `DatetimeIndex`, used by `load_calendar`. `build_rows`/`insert_symbol` row-dict keys (`sym,d,ts,o,h,l,c,v,ac`) match the INSERT bind params. `BUCKET='yfinance_real'` used consistently in puller + loader queries.

**Known limitation (documented, not a gap):** pre-join fills use close (open backfill not spliced) — see Component-2 note above; in-scope only if fill realism on 2016-2022 trades is later required.
