"""Per-model execution timing (US RTH, America/New_York).

India ran a walk-forward study that split large-cap timing (SELL into the 09:15
open pop, BUY at 09:30 after it faded). US has not been walk-forward swept yet, so
every model uses a single unified time at the regular-session open (09:30 ET).
Update EXEC_TIMES if/when a US per-side timing study is run.
"""
from __future__ import annotations

from typing import Dict

# All times are America/New_York (ET), 24h "HH:MM". US RTH open = 09:30.
EXEC_TIMES: Dict[str, Dict[str, str]] = {
    "momentum_n100_top5_max1":   {"buy": "09:30", "sell": "09:30"},
    "momentum_pseudo_n100_adv":  {"buy": "09:30", "sell": "09:30"},
    "midcap_narrow_60d_breakout": {"buy": "09:30", "sell": "09:30"},
    "n20_daily_large_only":      {"buy": "09:30", "sell": "09:30"},
    "n40_largecap_weekly":       {"buy": "09:30", "sell": "09:30"},
}

# Back-compat: single time per model.
EXEC_TIME: Dict[str, str] = {m: t["buy"] for m, t in EXEC_TIMES.items()}

_DEFAULT = "09:30"


def buy_time(model: str) -> str:
    return EXEC_TIMES.get(model, {}).get("buy", _DEFAULT)


def sell_time(model: str) -> str:
    return EXEC_TIMES.get(model, {}).get("sell", _DEFAULT)


def is_split(model: str) -> bool:
    """True if SELL and BUY times differ (needs two execute jobs)."""
    return buy_time(model) != sell_time(model)


def emit_time(model: str, lead_min: int = 5) -> str:
    """When to emit the signal: lead_min before the earliest exec time, floor 09:00."""
    earliest = min(buy_time(model), sell_time(model))
    h, m = (int(x) for x in earliest.split(":"))
    total = max(9 * 60, h * 60 + m - lead_min)
    return f"{total // 60:02d}:{total % 60:02d}"
