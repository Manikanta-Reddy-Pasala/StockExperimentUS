"""Data pulls for midcap_narrow_60d_breakout.

Daily (post-market close):
  - NIFTY 500 daily close OHLCV (shared with momentum_n100_top5_max1 via
    tools/shared/prefetch_ohlcv.py — same `historical_data` table)
  - Symbols in midcap_narrow universe are a subset of N500, so the N500
    pull already covers them. We include an explicit incremental pull
    here as a model-local fallback.

Monthly (1st trading day):
  - Refresh midcap_narrow.json universe (ADV rank drift)
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

UNIVERSE_OUT = "/app/logs/momrot/universes/midcap_narrow.json"
SKIP_TOP = 30
KEEP_NEXT = 100


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
    """Incremental N500 daily OHLCV (2 days lookback). Covers midcap_narrow."""
    log.info("=" * 80)
    log.info("midcap_narrow_60d_breakout daily OHLCV pull (N500)")
    log.info("=" * 80)
    _run(
        ["python3", "tools/shared/prefetch_ohlcv.py",
         "--universe", "n500", "--days", "5",
         "--intervals", "D", "--sleep", "0.2"],
        "prefetch_ohlcv_daily", timeout=1800,
    )


def refresh_universe():
    """Rebuild midcap_narrow by ADV (skip top-30, take next 100). Monthly."""
    log.info("=" * 80)
    log.info("midcap_narrow universe refresh (ADV-ranked, skip large caps)")
    log.info("=" * 80)
    Path(UNIVERSE_OUT).parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["python3", "tools/models/midcap_narrow_60d_breakout/build_universe.py",
         "--skip-top", str(SKIP_TOP),
         "--top", str(KEEP_NEXT),
         "--out", UNIVERSE_OUT],
        "build_midcap_narrow_universe", timeout=600,
    )
