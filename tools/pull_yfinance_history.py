"""Bulk-pull REAL yfinance daily OHLCV into a separate storage bucket.

Back-fills genuine split/div-adjusted S&P500 history for the pre-eToro years
into ``historical_data`` under ``data_source='yfinance_real'``. This is a NEW
bucket kept deliberately distinct from the existing ``data_source='yfinance'``
bucket — that label now stores the recent eToro feed and is left UNTOUCHED here.
A spliced loader joins the two buckets (yfinance_real for older years, the eToro
'yfinance' bucket for the recent window) so backtests can run on a longer window.

- default window: 2016-06-01 -> 2022-05-24 (ends where the eToro feed begins)
- universe: distinct symbols from the PIT sp500_membership.csv
- idempotent per symbol: deletes existing rows in the bucket/window before insert
- emits a coverage report listing symbols yfinance returned nothing for

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
