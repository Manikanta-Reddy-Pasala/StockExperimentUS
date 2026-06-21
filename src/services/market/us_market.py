"""US (NYSE/Nasdaq) market calendar + status — observer UI.

Pure-stdlib (zoneinfo). Reports whether the US market is open right now in ET,
the regular session hours, the next open, today's holiday (if any), the next
holiday, and the weekly rebalance schedule for the observer models.

NYSE regular session: 09:30–16:00 ET, Mon–Fri, excluding the holidays below.
Early-close (13:00 ET) half-days are flagged but not required for observer use.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

OPEN_T = time(9, 30)
CLOSE_T = time(16, 0)
EARLY_CLOSE_T = time(13, 0)

# NYSE full-day holidays (2025–2027). Verified against the published NYSE calendar.
HOLIDAYS: dict[str, str] = {
    # 2025
    "2025-01-01": "New Year's Day", "2025-01-20": "Martin Luther King Jr. Day",
    "2025-02-17": "Washington's Birthday", "2025-04-18": "Good Friday",
    "2025-05-26": "Memorial Day", "2025-06-19": "Juneteenth",
    "2025-07-04": "Independence Day", "2025-09-01": "Labor Day",
    "2025-11-27": "Thanksgiving Day", "2025-12-25": "Christmas Day",
    # 2026
    "2026-01-01": "New Year's Day", "2026-01-19": "Martin Luther King Jr. Day",
    "2026-02-16": "Washington's Birthday", "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day", "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)", "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving Day", "2026-12-25": "Christmas Day",
    # 2027
    "2027-01-01": "New Year's Day", "2027-01-18": "Martin Luther King Jr. Day",
    "2027-02-15": "Washington's Birthday", "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day", "2027-06-18": "Juneteenth (observed)",
    "2027-07-05": "Independence Day (observed)", "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving Day", "2027-12-24": "Christmas Day (observed)",
}

# Early-close (13:00 ET) half-days.
EARLY_CLOSE: dict[str, str] = {
    "2025-07-03": "Independence Day eve", "2025-11-28": "Day after Thanksgiving",
    "2025-12-24": "Christmas Eve",
    "2026-11-27": "Day after Thanksgiving", "2026-12-24": "Christmas Eve",
    "2027-11-26": "Day after Thanksgiving",
}


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_trading_day(d: date) -> bool:
    return not _is_weekend(d) and d.isoformat() not in HOLIDAYS


def holiday_name(d: date) -> Optional[str]:
    return HOLIDAYS.get(d.isoformat())


def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def next_holiday(d: date) -> Optional[dict]:
    for i in range(0, 400):
        c = d + timedelta(days=i)
        nm = HOLIDAYS.get(c.isoformat())
        if nm and c >= d:
            return {"date": c.isoformat(), "name": nm,
                    "days_away": (c - d).days}
    return None


def _close_time_for(d: date) -> time:
    return EARLY_CLOSE_T if d.isoformat() in EARLY_CLOSE else CLOSE_T


def next_weekly_rebalance(d: date) -> date:
    """Observer models rebalance the first trading day of each ISO week
    (Monday, or the next trading day if Monday is a holiday)."""
    dow = d.weekday()
    monday = d + timedelta(days=((7 - dow) % 7) or 7)  # next Monday
    while not is_trading_day(monday):
        monday += timedelta(days=1)
    return monday


def market_status(now: Optional[datetime] = None) -> dict:
    """Full market state in ET. now defaults to current ET time."""
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    today = now.date()
    hol = holiday_name(today)
    early = EARLY_CLOSE.get(today.isoformat())
    close_t = _close_time_for(today)

    if _is_weekend(today):
        state, reason = "CLOSED", "Weekend"
    elif hol:
        state, reason = "HOLIDAY", hol
    else:
        t = now.time()
        if t < OPEN_T:
            state, reason = "PRE_MARKET", "Opens 09:30 ET"
        elif t >= close_t:
            state, reason = "CLOSED", f"Closed {close_t.strftime('%H:%M')} ET"
        else:
            state, reason = ("EARLY_CLOSE" if early else "OPEN"), \
                (early or "Regular session")

    is_open = state in ("OPEN", "EARLY_CLOSE")

    # Next open datetime (ET)
    if is_open:
        next_open_dt = None
    else:
        if (not _is_weekend(today) and not hol and now.time() < OPEN_T):
            nd = today
        else:
            nd = next_trading_day(today)
        next_open_dt = datetime.combine(nd, OPEN_T, tzinfo=ET)

    reb = next_weekly_rebalance(today)
    return {
        "now_et": now.strftime("%Y-%m-%d %H:%M ET"),
        "state": state,
        "is_open": is_open,
        "reason": reason,
        "session": {
            "open": OPEN_T.strftime("%H:%M"),
            "close": close_t.strftime("%H:%M"),
            "tz": "America/New_York (ET)",
            "early_close": bool(early),
        },
        "today_is_trading_day": is_trading_day(today),
        "today_holiday": hol,
        "next_open": next_open_dt.strftime("%a %Y-%m-%d %H:%M ET") if next_open_dt else None,
        "next_trading_day": next_trading_day(today).isoformat() if not is_trading_day(today) else today.isoformat(),
        "next_holiday": next_holiday(today),
        "rebalance": {
            "cadence": "Weekly — first trading day of each ISO week (Mon)",
            "signal_emit": "13:50 container-local (observer signal-only)",
            "next_rebalance": reb.isoformat(),
            "days_away": (reb - today).days,
        },
    }
