"""Build midcap_narrow universe from N500 by ADV ranking.

Method:
  1. Compute 20-day ADV for every N500 stock.
  2. Sort by ADV descending.
  3. SKIP top-30 (large caps already covered by momentum_n100_top5_max1).
  4. Take next 100 = midcap_narrow.

Output: selector JSON compatible with backtest.py --universe-file.

Usage:
  python tools/models/midcap_narrow_60d_breakout/build_universe.py \
    --skip-top 30 --top 100 \
    --out logs/momrot/universes/midcap_narrow.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import read_cached  # noqa: E402
from tools.shared.universes import nifty500_symbols  # noqa: E402

log = logging.getLogger("build_midcap_narrow")


def compute_adv(symbol: str, end_dt: datetime, days: int = 60) -> float:
    """Avg daily ₹ value traded over last `days` calendar days, in lakh."""
    start_dt = end_dt - timedelta(days=days)
    df = read_cached(symbol, "D", int(start_dt.timestamp()), int(end_dt.timestamp()))
    if df.empty or len(df) < 5:
        return 0.0
    df["value"] = df["close"].astype(float) * df["volume"].astype(float)
    return float(df["value"].tail(20).mean()) / 1e5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-top", type=int, default=30,
                    help="Skip top-N largest caps (excluded from midcap pool)")
    ap.add_argument("--top", type=int, default=100,
                    help="How many midcaps to keep after skip")
    ap.add_argument("--end-date", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-adv-lakh", type=float, default=20.0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    end_dt = (datetime.strptime(args.end_date, "%Y-%m-%d")
              if args.end_date else datetime.now())

    universe = nifty500_symbols()
    log.info(f"Computing ADV for {len(universe)} N500 symbols as of {end_dt.date()}")

    rows = []
    for i, (sym, name) in enumerate(universe):
        if i % 50 == 0:
            log.info(f"  {i}/{len(universe)}")
        adv = compute_adv(sym, end_dt)
        if adv >= args.min_adv_lakh:
            rows.append({"symbol": sym, "name": name, "adv_lakh": adv})

    rows.sort(key=lambda r: -r["adv_lakh"])

    # Skip top-N largest, take next `top`
    midcap_band = rows[args.skip_top:args.skip_top + args.top]

    out = {
        "generated_at": datetime.now().isoformat(),
        "end_date": end_dt.date().isoformat(),
        "method": f"ADV-ranked, skip top-{args.skip_top} large caps, keep next {args.top}",
        "skip_large": args.skip_top,
        "top_n": args.top,
        "stocks": midcap_band,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    log.info(f"Wrote {args.out}")
    log.info(
        f"Top 5: "
        f"{[r['symbol'].split(':')[-1].replace('-EQ', '') for r in midcap_band[:5]]}"
    )


if __name__ == "__main__":
    main()
