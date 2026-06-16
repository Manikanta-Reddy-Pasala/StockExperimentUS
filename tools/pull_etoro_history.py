"""Bulk-pull daily OHLCV from eToro into the historical_data table.

Writes rows with plain US tickers (no NSE prefix). The data_source column stays
'yfinance' — that string is the canonical daily-bar storage bucket every
backtest filters on (`WHERE data_source='yfinance'`); it is a stored label, not
a live yfinance dependency. Bars now come from eToro via the shared core.
Idempotent per symbol: deletes existing rows in the bucket/window before insert.

Usage:
  PYTHONPATH=. python tools/pull_etoro_history.py \
      --universe src/data/symbols/nasdaq500.csv \
      --start 2022-05-24 --end 2026-05-24
"""
from __future__ import annotations
import argparse, csv, os, sys
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Shared history core — same eToro fetch path the live executor + broker use.
try:
    from src.services.data.price_history_provider import fetch_daily_bars
except Exception:  # noqa: BLE001
    fetch_daily_bars = None


def get_engine():
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system")
    # normalize psycopg(v3) dialect to psycopg2 if v3 not installed
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def load_universe(path: str) -> list[str]:
    syms = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("Series", "EQ").strip() == "EQ":
                syms.append(row["Symbol"].strip())
    return syms


def insert_symbol(conn, sym: str, df: pd.DataFrame) -> int:
    conn.execute(text("DELETE FROM historical_data WHERE symbol=:s AND data_source='yfinance' "
                      "AND date BETWEEN :a AND :b"),
                 {"s": sym, "a": df.index.min().date(), "b": df.index.max().date()})
    rows = []
    for ts, r in df.iterrows():
        d = ts.date()
        vol = r["Volume"]
        rows.append({
            "sym": sym, "d": d, "ts": int(datetime(d.year, d.month, d.day).timestamp()),
            "o": float(r["Open"]), "h": float(r["High"]), "l": float(r["Low"]),
            "c": float(r["Close"]), "v": int(vol) if pd.notna(vol) else 0,
            "ac": float(r["Adj Close"]) if "Adj Close" in df.columns and pd.notna(r["Adj Close"]) else float(r["Close"]),
        })
    if rows:
        conn.execute(text(
            "INSERT INTO historical_data "
            "(symbol,date,timestamp,open,high,low,close,volume,adj_close,data_source,api_resolution,is_adjusted) "
            "VALUES (:sym,:d,:ts,:o,:h,:l,:c,:v,:ac,'yfinance','1D',false)"), rows)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True)
    ap.add_argument("--start", default="2022-05-24")
    ap.add_argument("--end", default=date.today().isoformat())
    args = ap.parse_args()

    syms = load_universe(args.universe)
    print(f"Universe: {len(syms)} symbols, {args.start} -> {args.end} src=etoro", flush=True)
    eng = get_engine()

    # Shared-core path: identical eToro fetch logic to the live executor/broker.
    if fetch_daily_bars is None:
        print("! shared price_history_provider unavailable; aborting", file=sys.stderr)
        return 1
    total, failed = 0, []
    for n, sym in enumerate(syms, 1):
        try:
            df = fetch_daily_bars(sym, args.start, args.end)
            if df is None or df.empty:
                failed.append(sym); continue
            with eng.begin() as conn:
                total += insert_symbol(conn, sym, df)
        except Exception as e:  # noqa: BLE001
            failed.append(sym); print(f"  ! {sym}: {e}", file=sys.stderr, flush=True)
        if n % 25 == 0 or n == len(syms):
            print(f"  {n}/{len(syms)} done, rows={total}", flush=True)
    print(f"DONE rows={total} failed={len(failed)}: {failed[:30]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
