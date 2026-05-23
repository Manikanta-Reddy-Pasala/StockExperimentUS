"""Data pulls required by Model 3 — momentum_n100_top5_max1.

Daily (post-market close):
  - NIFTY 100 daily close OHLCV (cache via prefetch_ohlcv)

Quarterly (NSE rebalance: Mar/Sep):
  - Refresh src/data/symbols/nifty100.csv from NSE archives
  - Rebuild n100_current.json from updated CSV
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

UNIVERSE_OUT = "/app/logs/momrot/universes/n100_current.json"


def _run(cmd: list, label: str, timeout: int = 1800) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            log.info(f"  ✅ {label} ok")
            return True
        log.error(f"  ❌ {label} failed (rc={r.returncode})")
        if r.stderr:
            log.error(r.stderr[-500:])
    except subprocess.TimeoutExpired:
        log.error(f"  ❌ {label} timeout ({timeout}s)")
    except Exception as e:
        log.error(f"  ❌ {label} error: {e}")
    return False


def pull_daily_ohlcv():
    """Incremental N500 daily OHLCV (2 days lookback, just-in-case backfill)."""
    log.info("=" * 80)
    log.info("Model 3 daily OHLCV pull (N500)")
    log.info("=" * 80)
    _run(
        ["python3", "tools/shared/prefetch_ohlcv.py",
         "--universe", "n50,n500", "--days", "5",
         "--intervals", "D", "--sleep", "0.2"],
        "prefetch_ohlcv_daily", timeout=1800,
    )


def refresh_universe():
    """Refresh real Nifty 100 from NSE CSV + rebuild universe file."""
    log.info("=" * 80)
    log.info("Model 3 universe refresh (real NIFTY 100 from NSE)")
    log.info("=" * 80)
    Path(UNIVERSE_OUT).parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["python3", "tools/refresh_nifty100.py"],
        "refresh_nifty100_csv", timeout=120,
    )
    _run(
        ["python3", "tools/models/momentum_n100_top5_max1/build_universe.py",
         "--out", UNIVERSE_OUT],
        "build_universe", timeout=120,
    )
