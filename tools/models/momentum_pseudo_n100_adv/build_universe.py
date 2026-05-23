"""Build PSEUDO-Nifty-100 universe via ADV ranking from N500.

This is the V1 / "aggressive" universe used by momentum_pseudo_n100_adv model:
top-100 stocks by 20-day Average Daily ₹ Value traded from the Nifty 500 list.

Difference vs `momentum_n100_top5_max1/build_universe.py`:
  - That model uses REAL NSE Nifty 100 from `src/data/symbols/nifty100.csv`
  - This one ranks dynamically by ADV — captures retail-volume mid-caps that
    real N100 excludes (BSE, MAZDOCK, NETWEB, GRSE, IRFC, IDEA, ITI, NBCC,
    PAYTM, COFORGE, COHANCE, HFCL, etc.)

Usage:
  python tools/models/momentum_pseudo_n100_adv/build_universe.py --top 100 \
    --end-date 2025-05-13 \
    --out exports/backtests/pseudo_n100_2025-05-13.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import read_cached  # noqa: E402
from tools.shared.universes import nifty500_symbols  # noqa: E402

log = logging.getLogger("build_pseudo_n100")


def compute_adv(symbol: str, end_dt: datetime, days: int = 60) -> float:
    """Avg daily ₹ value traded over last `days` calendar days, in lakh."""
    start_dt = end_dt - timedelta(days=days)
    try:
        df = read_cached(symbol, "D", int(start_dt.timestamp()), int(end_dt.timestamp()))
    except Exception:
        return 0.0
    if df.empty or len(df) < 5:
        return 0.0
    df["value"] = df["close"].astype(float) * df["volume"].astype(float)
    return float(df["value"].tail(20).mean()) / 1e5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--end-date", default=None, help="YYYY-MM-DD (default today)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-adv-lakh", type=float, default=50.0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    end_dt = (datetime.strptime(args.end_date, "%Y-%m-%d")
              if args.end_date else datetime.now())

    universe = nifty500_symbols()
    log.info(f"Ranking {len(universe)} N500 symbols by ADV @ {end_dt.date()}")

    rows = []
    for i, (sym, name) in enumerate(universe):
        if i % 50 == 0:
            log.info(f"  {i}/{len(universe)}")
        adv = compute_adv(sym, end_dt)
        if adv >= args.min_adv_lakh:
            rows.append({"symbol": sym, "name": name, "adv_lakh": adv})

    rows.sort(key=lambda r: -r["adv_lakh"])
    top_n = rows[:args.top]

    out = {
        "generated_at": datetime.now().isoformat(),
        "end_date": end_dt.date().isoformat(),
        "method": "Pseudo-N100: top-100 by 20-day ADV from NIFTY 500",
        "top_n": args.top,
        "stocks": top_n,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    log.info(f"Wrote {args.out}")
    log.info(f"Top 10: {[r['symbol'] for r in top_n[:10]]}")


if __name__ == "__main__":
    main()
