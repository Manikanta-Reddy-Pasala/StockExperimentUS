"""Data pulls required by momentum_pseudo_n100_adv.

Daily (post-market close):
  - N500 daily close OHLCV (shared with momentum_n100 and midcap_narrow via
    tools/shared/prefetch_ohlcv.py — same historical_data table). The
    pseudo-N100 PIT universe is a subset of N500 so this covers it.

Yearly (May rebalance):
  - Rebuild yearly_universes.json by ranking N500 by 20d ADV at year-start.
    Uses only data observable at the rebuild date — PIT-safe for live
    deployment.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

UNIVERSES_FILE = (
    "/app/tools/models/momentum_pseudo_n100_adv/yearly_universes.json"
)


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
    """Incremental N500 daily OHLCV (2 days lookback)."""
    log.info("=" * 80)
    log.info("momentum_pseudo_n100_adv daily OHLCV pull (N500)")
    log.info("=" * 80)
    _run(
        ["python3", "tools/shared/prefetch_ohlcv.py",
         "--universe", "n50,n500", "--days", "5",
         "--intervals", "D", "--sleep", "0.2"],
        "prefetch_ohlcv_daily", timeout=1800,
    )


def refresh_universe():
    """Rebuild PIT universe via build_universe.py (top-100 by ADV) and
    MERGE the result into yearly_universes.json under today's date key.

    Called on month-1 of each year (May) by cron, or on-demand from the
    /admin 'Pull Data Now' button. Output side-effect:
      - One-off snapshot at /app/exports/backtests/pseudo_n100_{date}.json
      - Same symbols merged into yearly_universes.json under "YYYY-MM-DD"
        key so live_signal.pick_universe_for() finds it immediately.
    """
    import json
    log.info("=" * 80)
    log.info("momentum_pseudo_n100_adv yearly PIT universe refresh")
    log.info("=" * 80)
    end_date = datetime.now().strftime("%Y-%m-%d")
    out_file = f"/app/exports/backtests/pseudo_n100_{end_date}.json"
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    ok = _run(
        ["python3",
         "tools/models/momentum_pseudo_n100_adv/build_universe.py",
         "--top", "100", "--end-date", end_date, "--out", out_file],
        "build_pseudo_n100_universe", timeout=600,
    )
    if not ok:
        log.error("build_universe failed — yearly_universes.json NOT updated")
        return
    try:
        snapshot = json.loads(Path(out_file).read_text())
        if isinstance(snapshot, dict):
            entries = snapshot.get("stocks") or snapshot.get("symbols") or []
        else:
            entries = snapshot
        symbols = [e["symbol"] if isinstance(e, dict) else e for e in entries]
        if len(symbols) < 50:
            log.warning(f"build_universe returned only {len(symbols)} — skipping merge")
            return
        yearly = {}
        if Path(UNIVERSES_FILE).exists():
            yearly = json.loads(Path(UNIVERSES_FILE).read_text())
        yearly[end_date] = [{"symbol": s} for s in symbols]
        Path(UNIVERSES_FILE).write_text(json.dumps(yearly, indent=2))
        log.info(f"  merged {len(symbols)} symbols into yearly_universes.json as '{end_date}'")
    except Exception as e:
        log.error(f"  yearly_universes.json merge failed: {e}", exc_info=True)
