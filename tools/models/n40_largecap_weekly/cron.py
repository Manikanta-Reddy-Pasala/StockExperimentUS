"""Cron registration for the TWO final WEEKLY OBSERVER models.

The system is reduced to exactly two signal-only (observer) models — NO orders,
NO executor, NO leverage (all cash, lev 1.0):

  momentum_sp100  n40 recipe on S&P 100: top-40-by-ADV (topadv 50) -> top-3 by
                  blend momentum, weekly, QQQ 200d regime, held at the BLEND
                  WEIGHTS [0.7333, 0.1333, 0.1333] (= the 60/40 blend of the
                  top-1 + top-3 S&P100 sleeves = 107% CAGR / 33.5% DD).
                  Universe src/data/symbols/sp100.csv.
                  -> tools/models/n40_largecap_weekly/live_signal.py --weights

  retest_sp500    India retest engine on S&P 500: top-2, weekly, QQQ 200d regime,
                  nasdaq500 pool PIT-filtered by sp500_membership = 134% CAGR /
                  34% DD. -> tools/models/india_ports_us/live_signal.py

OBSERVER MODE: these emit a target-holdings JSON only. There is NO execute job,
NO executor call, NO order placement — they shadow the live book for monitoring.

Two register functions (matching the other US models):
  register_data_jobs(schedule)    -- no-op (US uses static CSV universes + the
                                     shared daily OHLCV refresh, nothing
                                     model-specific to pull)
  register_trading_jobs(schedule) -- registers the weekly observer signal emit
                                     for BOTH final models
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

SIGNALS_DIR = Path("/app/logs/observer/signals")

# Blend weights for momentum_sp100: rank1=0.7333, rank2=0.1333, rank3=0.1333.
# This equals the 60/40 blend of the top-1 + top-3 S&P100 sleeves.
SP100_BLEND_WEIGHTS = "0.8,0.1,0.1"   # 70/30 blend (fine-tuned): 112% CAGR / 34.9% DD (was 60/40 .733/.133/.133 = 107%/33.5%)


def emit_momentum_sp100(force: bool = False):
    """Emit momentum_sp100 OBSERVER signal (n40 S&P100 top-1 single-stock).

    Signal-only — never calls an executor. The live_signal self-skips on
    non-rebalance days (writes an empty file), so this is safe to fire daily.
    """
    model_name = "momentum_sp100"
    log.info("\n" + "=" * 80)
    log.info(f"RUNNING OBSERVER signal: {model_name} (S&P100 top-1 single-stock)"
             + (" [FORCE]" if force else " [weekly-gated]"))
    log.info("=" * 80)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    signals_out = SIGNALS_DIR / f"{today}_{model_name}.json"
    # top-1 SINGLE-STOCK (no --weights) so the live signal is byte-identical to the
    # backtest: both call the shared pick_n40_holdings(top=1) — zero drift. User chose
    # top-1 for max CAGR: +121.4% / 39.0% DD / Calmar 3.11 (vs top-2 102%/28%/3.65).
    cmd = [
        "python3", "tools/models/n40_largecap_weekly/live_signal.py",
        "--universe-csv", "src/data/symbols/sp100.csv",
        "--lev", "1.0",
        "--top", "1",
        "--topadv", "50",
        "--signal", "blend",
        "--model-name", model_name,
        "--signals-out", str(signals_out),
    ]
    cmd.append("--force" if force else "--rebalance-only")
    _run(model_name, cmd, signals_out)


def emit_retest_sp500(force: bool = False):
    """Emit retest_sp500 OBSERVER signal (India retest engine, S&P500 PIT top-2).

    Signal-only — never calls an executor. The live_signal self-skips on
    non-rebalance days (writes an empty file), so this is safe to fire daily.
    """
    model_name = "retest_sp500"
    log.info("\n" + "=" * 80)
    log.info(f"RUNNING OBSERVER signal: {model_name} (S&P500 PIT retest top-2)"
             + (" [FORCE]" if force else " [weekly-gated]"))
    log.info("=" * 80)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    signals_out = SIGNALS_DIR / f"{today}_{model_name}.json"
    cmd = [
        "python3", "tools/models/india_ports_us/live_signal.py",
        "--universe-csv", "src/data/symbols/nasdaq500.csv",
        "--membership-csv", "src/data/symbols/sp500_membership.csv",
        "--k", "2",
        "--model-name", model_name,
        "--signals-out", str(signals_out),
    ]
    cmd.append("--force" if force else "--rebalance-only")
    _run(model_name, cmd, signals_out)


def _run(model_name: str, cmd: list, signals_out: Path):
    """Run an observer live_signal subprocess and log the result."""
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
    log.debug("observer models: no model-specific data jobs (static CSV universes)")


def register_trading_jobs(schedule):
    """Register the weekly OBSERVER signal emit for BOTH final models.

    OBSERVER: signal-only. No execute job is registered — these models never
    place orders. Emits the CURRENT target holdings DAILY (force=True) so
    Today's Picks always shows live holdings — not an empty "[]" self-skip on
    non-rebalance days (which broke the picks ranking endpoint).
    """
    schedule.every().day.at("13:50").do(lambda: emit_momentum_sp100(force=True))
    schedule.every().day.at("13:50").do(lambda: emit_retest_sp500(force=True))
    log.debug("registered observer trading jobs: momentum_sp100, retest_sp500")
