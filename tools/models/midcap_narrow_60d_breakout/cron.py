"""Cron registration for midcap_narrow_60d_breakout.

Data side:
  register_data_jobs(schedule) — daily N500 OHLCV + monthly universe refresh.
Trading side:
  register_trading_jobs(schedule) — daily live_signal + Fyers execute (always live).
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from tools.models.midcap_narrow_60d_breakout.data_pull import (
    pull_daily_ohlcv, refresh_universe,
)

log = logging.getLogger(__name__)

MODEL_NAME = "midcap_narrow_60d_breakout"
UNIVERSE_FILE = "/app/logs/momrot/universes/midcap_narrow.json"
SIGNALS_DIR = Path("/app/logs/midcap_narrow/signals")


# ---- Trading-side jobs ----

def emit_signal():
    log.info("\n" + "=" * 80)
    log.info(f"RUNNING {MODEL_NAME} live signal")
    log.info("=" * 80)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    signals_out = SIGNALS_DIR / f"{today}_midcap_narrow.json"
    cmd = [
        "python3",
        "tools/models/midcap_narrow_60d_breakout/live_signal.py",
        "--universe-file", UNIVERSE_FILE,
        "--signals-out", str(signals_out),
    ]
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
    signals_file = SIGNALS_DIR / f"{today}_midcap_narrow.json"
    if not signals_file.exists():
        log.info(f"{MODEL_NAME} execute: no signal at {signals_file}, skipping.")
        return
    log.info(f"PLACING {MODEL_NAME} FYERS ORDERS")
    user_id = os.environ.get("USER_ID", "1")
    cmd = [
        "python3", "tools/live/fyers_executor.py",
        "--signals", str(signals_file),
        "--user-id", user_id,
        "--model-name", MODEL_NAME,
    ]
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


# ---- Data-side jobs ----

def _monthly_universe():
    if datetime.now().day == 1:
        refresh_universe()


# ---- Registration entrypoints ----

def register_data_jobs(schedule):
    """Daily OHLCV + monthly universe refresh."""
    # N500 OHLCV — covers midcap_narrow (subset of N500)
    schedule.every().day.at("20:45").do(pull_daily_ohlcv)
    # Universe refresh — 1st of month only (no-op other days)
    schedule.every().day.at("06:35").do(_monthly_universe)


def register_trading_jobs(schedule):
    """Daily signal + Fyers execute (event-driven, daily check)."""
    # Signal scan — runs daily after market open to detect breakouts + exits
    schedule.every().day.at("09:25").do(emit_signal)
    # Execute orders
    schedule.every().day.at("09:32").do(execute_orders)
    # Also check exit conditions at market close (catches end-of-day SMA breaks)
    schedule.every().day.at("15:25").do(emit_signal)
