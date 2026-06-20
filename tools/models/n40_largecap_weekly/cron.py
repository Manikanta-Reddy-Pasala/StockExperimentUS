"""Cron registration for the n40 large-cap WEEKLY OBSERVER models.

Three signal-only variants of the n40 strategy (top-40 ADV → top-3 blend →
weekly → QQQ 200d regime), each on a different large-cap universe + leverage:

  n40_sp500_lev11      src/data/symbols/sp500.csv      lev 1.10  (5yr ~129.9% / 37.8% DD)
  n40_nasdaq100_lev11  src/data/symbols/nasdaq100.csv  lev 1.10  (~108.4% / 41.1% DD)
  n40_sp100_lev125     src/data/symbols/sp100.csv      lev 1.25  (~102.7% / 33.2% DD)

OBSERVER MODE: these emit a target-holdings JSON only. There is NO execute job,
NO executor call, NO order placement — they shadow the live book for monitoring.

Two register functions (matching the other US models):
  register_data_jobs(schedule)    -- called by data_scheduler.py (no-op; US uses
                                     static CSV universes + the shared daily OHLCV
                                     refresh, so there is nothing model-specific)
  register_trading_jobs(schedule) -- called by scheduler.py; registers the weekly
                                     observer signal emit for all three variants
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

SIGNALS_DIR = Path("/app/logs/n40_observer/signals")

# (model_name, universe_csv, leverage)
VARIANTS = [
    ("n40_sp500_lev11", "src/data/symbols/sp500.csv", 1.10),
    ("n40_nasdaq100_lev11", "src/data/symbols/nasdaq100.csv", 1.10),
    ("n40_sp100_lev125", "src/data/symbols/sp100.csv", 1.25),
]


def emit_observer_signal(model_name: str, universe_csv: str, lev: float,
                         force: bool = False):
    """Emit one variant's OBSERVER signal. Weekly-gated unless force=True.

    Signal-only — never calls an executor. The live_signal self-skips on
    non-rebalance days (writes an empty file), so this is safe to fire daily.
    """
    log.info("\n" + "=" * 80)
    log.info(f"RUNNING n40 OBSERVER signal: {model_name} "
             f"(universe={universe_csv} lev={lev:g})"
             + (" [FORCE]" if force else " [weekly-gated]"))
    log.info("=" * 80)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    signals_out = SIGNALS_DIR / f"{today}_{model_name}.json"
    cmd = [
        "python3", "tools/models/n40_largecap_weekly/live_signal.py",
        "--universe-csv", universe_csv,
        "--lev", str(lev),
        "--model-name", model_name,
        "--signals-out", str(signals_out),
    ]
    cmd.append("--force" if force else "--rebalance-only")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            log.info(f"✅ {model_name} OBSERVER signal -> {signals_out}")
            if r.stdout:
                log.info(r.stdout[-500:])
        else:
            log.error(f"❌ {model_name} OBSERVER signal failed ({r.returncode})")
            if r.stderr:
                log.error(r.stderr[-500:])
    except Exception as e:
        log.error(f"❌ {model_name} OBSERVER signal error: {e}")


# ---- Registration entrypoints ----

def register_data_jobs(schedule):
    """No model-specific data pulls.

    US universes are static CSVs (no per-model universe refresh) and OHLCV is
    kept fresh by the shared daily pipeline in data_scheduler.py. Nothing to do.
    """
    log.debug("n40_observer: no model-specific data jobs (static CSV universes)")


def register_trading_jobs(schedule):
    """Register the weekly OBSERVER signal emit for all three variants.

    OBSERVER: signal-only. No execute job is registered — these models never
    place orders. live_signal self-skips on non-Monday days, so daily firing is
    safe; 13:50 sits just after the 13:45 US-book DRY-RUN signal slot.
    """
    for model_name, universe_csv, lev in VARIANTS:
        # Bind loop vars via defaults so the closure captures the right values.
        schedule.every().day.at("13:50").do(
            lambda m=model_name, u=universe_csv, l=lev: emit_observer_signal(m, u, l)
        )
        log.debug(f"registered n40 observer trading job: {model_name}")
