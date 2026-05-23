"""Bulk-prefetch OHLCV from Fyers into the existing Postgres tables.

Run this ONCE before yearly backtests. Pulls 1H + daily bars (the only
intervals with existing tables: historical_data_1h, historical_data)
for the full backtest window (last 3 years + 400d EMA200 warmup buffer
= ~1500 calendar days).

15m bars NOT prefetched here — EMA harness must use --no-use-15m
(sustain falls back to 1H close). 5m bars (ORB) also skipped (no cache
table).

After this script completes, the yearly orchestrator's
realistic_capital_sim / monthly_profile / backtest harnesses read
entirely from DB — Fyers is hit only on cache miss (which should be
near-zero after prefetch).

Idempotent: each per-symbol fetch upserts via ON CONFLICT DO NOTHING.
Re-running adds only the missing bars.

Usage:
  python tools/shared/prefetch_ohlcv.py --universe n50,n500 \
    --days 1500 --intervals 1h,D
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Reuse fetcher + writer from existing modules.
from tools.shared.ohlcv_cache import (  # noqa: E402
    _get_engine, write_rows, read_cached, _to_fyers_sym,
)


def load_universe(name: str) -> List[Tuple[str, str]]:
    """Return [(plain_ticker, company_name), ...] for the requested universe."""
    from tools.shared.universes import (
        NIFTY50_SYMBOLS, nifty500_symbols,
    )
    if name in ("n50", "nifty50"):
        return list(NIFTY50_SYMBOLS)
    if name in ("n500", "nifty500"):
        return nifty500_symbols()
    if name in ("all", "all-stocks", "all_stocks"):
        # Every NSE-EQ symbol from the `stocks` master table. Strips the
        # NSE:...-EQ wrapper so the rest of this pipeline sees plain
        # tickers (matches n50/n500 format).
        from sqlalchemy import text
        eng = _get_engine()
        if eng is None:
            raise RuntimeError("DB unavailable — cannot enumerate 'all' universe")
        with eng.connect() as c:
            rows = c.execute(text(
                "SELECT symbol, name FROM stocks "
                "WHERE symbol LIKE 'NSE:%-EQ' ORDER BY symbol"
            )).fetchall()
        out = []
        for sym, name_ in rows:
            plain = sym.replace("NSE:", "").replace("-EQ", "")
            out.append((plain, name_ or plain))
        return out
    raise ValueError(f"Unknown universe: {name}")


def fetch_one(symbol: str, interval: str, days: int, user_id: int = 1):
    """Direct Fyers fetch (bypasses cache check). Returns DataFrame."""
    from tools.shared.universes import (
        _fetch_fyers_interval, _FYERS_CACHE, _fetch_daily_fyers_raw,
    )
    _FYERS_CACHE["user_id"] = user_id
    if interval == "1h":
        return _fetch_fyers_interval(symbol, days, user_id,
                                     interval="1h", chunk_days=95)
    if interval == "15m":
        return _fetch_fyers_interval(symbol, days, user_id,
                                     interval="15m", chunk_days=30)
    if interval in ("D", "daily"):
        return _fetch_daily_fyers_raw(symbol, days, user_id, chunk_days=365)
    raise ValueError(f"Unsupported interval: {interval}")


def current_coverage(symbol: str, interval: str, days: int) -> int:
    """Return cached row count for the requested window (used to skip
    already-prefetched symbols)."""
    from datetime import datetime, timedelta
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    df = read_cached(symbol, interval,
                     int(start_dt.timestamp()), int(end_dt.timestamp()))
    return len(df)


def expected_bars(interval: str, days: int) -> int:
    trading_days = max(1, int(days * 250 / 365))
    return {
        "1h":  trading_days * 6,
        "15m": trading_days * 25,
        "5m":  trading_days * 75,
        "D":   trading_days,
    }.get(interval, trading_days)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="n50,n500",
                    help="Comma-sep: n50,n500. Use 'all' for both.")
    ap.add_argument("--days", type=int, default=1500,
                    help="Calendar days back. 1500 covers 3y + 400d warmup.")
    ap.add_argument("--intervals", default="1h,D",
                    help="Comma-sep: 1h, 15m, D. Default: 1h,D")
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--skip-frac", type=float, default=0.85,
                    help="Skip symbol if cache has >= this fraction of "
                         "expected rows for the window.")
    ap.add_argument("--max-symbols", type=int, default=None,
                    help="Limit number of symbols (for testing)")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="Seconds to sleep between symbols to avoid Fyers rate-limit.")
    ap.add_argument("--retry-passes", type=int, default=1,
                    help="Number of passes to retry partial-coverage stocks.")
    args = ap.parse_args()

    universes = [u.strip() for u in args.universe.split(",") if u.strip()]
    # NOTE: 'all' is now a real universe loader (every NSE-EQ in stocks table).
    # If user passes 'all', use only that — combining with n50/n500 is redundant
    # since 'all' is a superset.
    if "all" in universes:
        universes = ["all"]
    intervals = [iv.strip() for iv in args.intervals.split(",") if iv.strip()]

    # De-dupe symbols across universes (N50 fully contained in N500 mostly).
    seen = set()
    symbols: List[Tuple[str, str]] = []
    for u in universes:
        for sym, name in load_universe(u):
            if sym in seen:
                continue
            seen.add(sym)
            symbols.append((sym, name))
    if args.max_symbols:
        symbols = symbols[: args.max_symbols]

    print(f"Prefetch start: {len(symbols)} unique symbols, "
          f"intervals={intervals}, window={args.days} days")
    eng = _get_engine()
    if eng is None:
        print("ERR: no DB engine — aborting")
        return 1

    t_start = time.time()
    n_done = 0
    n_skipped = 0
    n_fetched = 0
    total_rows = 0
    # Incremental-pull guard: skip-logic only meaningful for backfill windows.
    # Small windows (e.g. --days 2 = 1 expected bar) cause skip-frac to round
    # to 0 → every symbol skipped → today's candle never fetched.
    skip_enabled = args.days >= 30
    if not skip_enabled:
        print(f"Incremental mode (--days={args.days} < 30): skip-frac disabled, "
              f"always fetching latest bars.")

    for sym, name in symbols:
        n_done += 1
        per_interval_summary = []
        for iv in intervals:
            exp = expected_bars(iv, args.days)
            have = current_coverage(sym, iv, args.days)
            if skip_enabled and have >= int(exp * args.skip_frac):
                per_interval_summary.append(f"{iv}=skip({have}/{exp})")
                n_skipped += 1
                continue
            try:
                df = fetch_one(sym, iv, args.days, args.user_id)
            except Exception as e:
                per_interval_summary.append(f"{iv}=err({e})")
                continue
            if df is None or len(df) == 0:
                per_interval_summary.append(f"{iv}=nodata")
                continue
            wrote = write_rows(sym, iv, df)
            total_rows += wrote
            n_fetched += 1
            per_interval_summary.append(f"{iv}=+{wrote}")
        elapsed = time.time() - t_start
        rate = n_done / max(elapsed, 1)
        eta = (len(symbols) - n_done) / max(rate, 1e-6)
        print(f"[{n_done}/{len(symbols)}] {sym}: {' '.join(per_interval_summary)} "
              f"(elapsed={elapsed/60:.1f}m, eta={eta/60:.1f}m)",
              flush=True)
        if args.sleep > 0 and n_done < len(symbols):
            time.sleep(args.sleep)
    print("---")
    print(f"Prefetch done: {n_done} symbols, "
          f"{n_fetched} fetched, {n_skipped} skipped, "
          f"{total_rows} rows added, "
          f"total time {(time.time()-t_start)/60:.1f}m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
