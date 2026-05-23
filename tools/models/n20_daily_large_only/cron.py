"""Cron registration for n20_daily_large_only.

Daily rotation model — signal runs every weekday morning (no monthly gate).
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from tools.models.n20_daily_large_only.data_pull import (  # noqa: E402
    pull_daily_ohlcv, refresh_universe,
)

log = logging.getLogger(__name__)

MODEL_NAME = "n20_daily_large_only"
SIGNALS_DIR = Path("/app/logs/n20_daily/signals")


# ---- Trading-side jobs ----

def emit_signal():
    """Emit daily rotation signal. Weekday-gated inside live_signal.py."""
    log.info("\n" + "=" * 80)
    log.info(f"RUNNING {MODEL_NAME} live signal")
    log.info("=" * 80)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    signals_out = SIGNALS_DIR / f"{today}_n20.json"
    cmd = [
        "python3", "tools/models/n20_daily_large_only/live_signal.py",
        "--signals-out", str(signals_out), "--top-n", "1",
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
    signals_file = SIGNALS_DIR / f"{today}_n20.json"
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

def _quarterly_universe():
    """Refresh Nifty 100 CSV on first weekday of Mar/Sep (NSE rebalance)."""
    today = datetime.now()
    if today.month in (3, 9) and today.day == 1 and today.weekday() < 5:
        refresh_universe()


# ---- Registration entrypoints ----

def register_data_jobs(schedule):
    """Daily OHLCV at 20:40 (after n100 pull). Quarterly N100 refresh."""
    schedule.every().day.at("20:40").do(pull_daily_ohlcv)
    schedule.every().day.at("06:33").do(_quarterly_universe)


def register_trading_jobs(schedule):
    """Daily signal 09:25 + execute 09:30."""
    schedule.every().day.at("09:25").do(emit_signal)
    schedule.every().day.at("09:30").do(execute_orders)
