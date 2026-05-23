"""Build NIFTY 100 universe file from REAL NSE constituents.

Source: ``src/data/symbols/nifty100.csv`` (refresh via ``tools/refresh_nifty100.py``).

Previously this script ADV-ranked top-100 from Nifty 500 — that produced
"pseudo-N100" with 47/100 stocks NOT in the real index (HFCL, GROWW, BSE,
COHANCE etc.). Replaced with curated NSE list to match index methodology.

Output JSON is compatible with momentum_n100_top5_max1/live_signal.py.

Usage:
  python tools/models/momentum_n100_top5_max1/build_universe.py \
    --out /app/logs/momrot/universes/n100_current.json

  # Optional: include ADV for ranking visibility (not used for selection)
  python tools/models/momentum_n100_top5_max1/build_universe.py \
    --out /app/logs/momrot/universes/n100_current.json --include-adv
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import read_cached  # noqa: E402
from tools.shared.universes import nifty100_symbols  # noqa: E402

log = logging.getLogger("build_universe")


def compute_adv(symbol: str, end_dt: datetime, days: int = 60) -> float:
    """Return avg daily ₹ value traded over last `days` calendar days, in lakh."""
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
    ap.add_argument("--end-date", default=None, help="YYYY-MM-DD (for ADV calc only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--include-adv", action="store_true",
                    help="Compute & include ADV per stock (slower, informational)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    end_dt = (datetime.strptime(args.end_date, "%Y-%m-%d")
              if args.end_date else datetime.now())

    n100 = nifty100_symbols()
    if not n100:
        log.error("Real Nifty 100 list empty. Run tools/refresh_nifty100.py first.")
        return 1

    log.info(f"Loaded real NIFTY 100 ({len(n100)} stocks) from NSE CSV")

    stocks: List[dict] = []
    for i, (sym, name) in enumerate(n100):
        entry = {"symbol": sym, "name": name}
        if args.include_adv:
            if i % 20 == 0:
                log.info(f"  ADV {i}/{len(n100)}")
            entry["adv_lakh"] = compute_adv(sym, end_dt)
        stocks.append(entry)

    out = {
        "generated_at": datetime.now().isoformat(),
        "end_date": end_dt.date().isoformat(),
        "method": "Real NIFTY 100 constituents (NSE archives)",
        "source_csv": "src/data/symbols/nifty100.csv",
        "stocks": stocks,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    log.info(f"Wrote {args.out}")
    log.info(f"First 10: {[s['symbol'] for s in stocks[:10]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
