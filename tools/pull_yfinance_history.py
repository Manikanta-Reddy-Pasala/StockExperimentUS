"""Bulk-pull REAL yfinance daily OHLCV into a separate storage bucket.

Back-fills genuine split/div-adjusted S&P500 history for the pre-eToro years
into ``historical_data`` under ``data_source='yfinance_real'``. This is a NEW
bucket kept deliberately distinct from the existing ``data_source='yfinance'``
bucket — that label now stores the recent eToro feed and is left UNTOUCHED here.
A spliced loader joins the two buckets (yfinance_real for older years, the eToro
'yfinance' bucket for the recent window) so backtests can run on a longer window.

- default window: 2016-06-01 -> 2021-05-31 (day before the eToro feed begins)
- universe: distinct symbols from the PIT sp500_membership.csv
- idempotent per symbol: deletes existing rows in the bucket/window before insert
- emits a coverage report listing symbols yfinance returned nothing for

Usage:
  PYTHONPATH=. python tools/pull_yfinance_history.py \
      --membership src/data/symbols/sp500_membership.csv \
      --start 2016-06-01 --end 2021-05-31 \
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


def fetch_one(sym: str, start: str, end: str):
    """Real split/div-adjusted daily bars from yfinance. None on empty/error."""
    import yfinance as yf
    try:
        df = yf.download(sym, start=start, end=end, auto_adjust=True,
                         progress=False, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
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


def write_report(path: str, start: str, end: str, fetched: dict, missing: list):
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
    ap.add_argument("--end", default="2021-05-31")
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
