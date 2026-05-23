"""Cron registration for momentum_pseudo_n100_adv.

Two register functions:
  register_data_jobs(schedule)   -- called by data_scheduler.py
  register_trading_jobs(schedule) -- called by scheduler.py (technical_scheduler)

The yearly-PIT universe is rebuilt at year-start (mid-May) using current
data at that time — PIT-safe for live deployment. The live_signal will
short-circuit if the enabled flag is False (toggle via UI).
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from tools.models.momentum_pseudo_n100_adv.data_pull import (  # noqa: E402
    pull_daily_ohlcv, refresh_universe,
)

log = logging.getLogger(__name__)

MODEL_NAME = "momentum_pseudo_n100_adv"
UNIVERSES_FILE = (
    "/app/tools/models/momentum_pseudo_n100_adv/yearly_universes.json"
)
SIGNALS_DIR = Path("/app/logs/momrot_pseudo/signals")


# ---- Trading-side jobs ----

def emit_signal(force: bool = False):
    """Emit pseudo-N100 momentum signal. Rebalance-gated unless force=True.

    Also short-circuits if model_settings.enabled is False.
    """
    label = ("pseudo-N100 momentum signal"
             + (" (FORCE)" if force else " (rebalance-gated)"))
    log.info("\n" + "=" * 80)
    log.info(f"RUNNING {label}")
    log.info("=" * 80)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    signals_out = SIGNALS_DIR / f"{today}_pseudo_n100.json"
    cmd = [
        "python3", "tools/models/momentum_pseudo_n100_adv/live_signal.py",
        "--universes-file", UNIVERSES_FILE,
        "--top-n", "5",
        "--signals-out", str(signals_out),
    ]
    cmd.append("--force" if force else "--rebalance-only")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            log.info(f"✅ {MODEL_NAME} signal -> {signals_out}")
            if r.stdout:
                log.info(r.stdout[-500:])
            try:
                from tools.live.telegram_notify import notify_signals
                notify_signals(MODEL_NAME, str(signals_out))
            except Exception as _te:
                log.debug(f"TG notify failed: {_te}")
        else:
            log.error(f"❌ {MODEL_NAME} signal failed ({r.returncode})")
            if r.stderr:
                log.error(r.stderr[-500:])
    except Exception as e:
        log.error(f"❌ {MODEL_NAME} signal error: {e}")


def execute_orders():
    """Place Fyers orders from today's signal file."""
    today = datetime.now().strftime("%Y-%m-%d")
    signals_file = SIGNALS_DIR / f"{today}_pseudo_n100.json"
    if not signals_file.exists():
        log.info(f"{MODEL_NAME} execute: no signal at {signals_file}, skipping.")
        return
    log.info(f"PLACING {MODEL_NAME} FYERS ORDERS")
    user_id = os.environ.get("USER_ID", "1")
    cmd = ["python3", "tools/live/fyers_executor.py",
           "--signals", str(signals_file), "--user-id", user_id,
           "--model-name", MODEL_NAME]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            log.info(f"✅ {MODEL_NAME} Fyers execute complete")
            if r.stdout:
                log.info(r.stdout[-500:])
        else:
            log.error(f"❌ {MODEL_NAME} Fyers execute failed ({r.returncode})")
            if r.stderr:
                log.error(r.stderr[-500:])
    except Exception as e:
        log.error(f"❌ {MODEL_NAME} Fyers execute error: {e}")


# ---- Data-side helpers ----

def _yearly_universe():
    """Rebuild PIT universe only in May (NSE rebalance proxy)."""
    if datetime.now().month == 5 and datetime.now().day == 15:
        refresh_universe()


# ---- Registration entrypoints ----

def register_data_jobs(schedule):
    """Daily OHLCV + yearly universe refresh."""
    schedule.every().day.at("20:35").do(pull_daily_ohlcv)
    # PIT universe rebuild — May 15 only (no-op other days)
    schedule.every().day.at("06:32").do(_yearly_universe)


def register_trading_jobs(schedule):
    """Signal at 09:25 (rebalance-gated) + execute at 09:30."""
    schedule.every().day.at("09:25").do(emit_signal)
    schedule.every().day.at("09:30").do(execute_orders)
