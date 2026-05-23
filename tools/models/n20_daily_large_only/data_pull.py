"""Data pulls for n20_daily_large_only.

Daily (post-market close):
  - N500 daily close OHLCV (shared infra via prefetch_ohlcv.py). Daily PIT
    ranking pool is N500, narrowed to top-20 ADV ∩ N100 at signal time.

Quarterly (NSE Nifty 100 rebalance: Mar/Sep):
  - Refresh nifty100.csv (handled by momentum_n100 already; we register a
    no-op fallback here for self-containment).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)


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
    """Incremental N500 daily OHLCV — also covers n20 PIT pool."""
    log.info("=" * 80)
    log.info("n20_daily_large_only daily OHLCV pull (N500)")
    log.info("=" * 80)
    _run(
        ["python3", "tools/shared/prefetch_ohlcv.py",
         "--universe", "n50,n500", "--days", "5",
         "--intervals", "D", "--sleep", "0.2"],
        "prefetch_ohlcv_daily", timeout=1800,
    )


def refresh_universe():
    """Refresh nifty100.csv from NSE archive (proxies N100 rebalance)."""
    log.info("=" * 80)
    log.info("n20_daily_large_only universe refresh (Nifty 100 from NSE)")
    log.info("=" * 80)
    _run(
        ["python3", "tools/refresh_nifty100.py"],
        "refresh_nifty100_csv", timeout=120,
    )
