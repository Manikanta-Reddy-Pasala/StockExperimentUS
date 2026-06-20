"""Tag each trade with its market-cap segment (large/mid/other).

Mirrors the India cap-tag API so model backtests and the web layer share one
classifier. US classification is current-snapshot (see tools.shared.market_cap);
there is no point-in-time index history, so `cap_for` accepts a date for API
parity but the date does not change the result.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List

from tools.shared.market_cap import classify_pit


def _to_date(on):
    """Coerce a date/datetime/ISO-str/epoch into a date (None on failure)."""
    if on is None:
        return None
    if hasattr(on, "date") and not isinstance(on, date):  # datetime
        try:
            return on.date()
        except Exception:
            return None
    if isinstance(on, date):
        return on
    if isinstance(on, (int, float)):
        try:
            from datetime import datetime as _dt
            return _dt.fromtimestamp(on).date()
        except Exception:
            return None
    if isinstance(on, str):
        try:
            return date.fromisoformat(on[:10])
        except Exception:
            return None
    return None


def cap_for(sym: str, entry_date=None) -> str:
    """Cap segment for `sym` -> large|mid|other.

    Accepts a date, datetime, ISO string, or epoch for `entry_date` (kept for
    API parity with India; US classification is snapshot-based)."""
    on = _to_date(entry_date)
    try:
        return classify_pit(sym, on)
    except Exception:
        return "other"


def annotate_caps(trades: List[Dict]) -> List[Dict]:
    """In-place: set t['cap'] on every trade (from t['sym'] or t['symbol'] and
    t['entry_date']). Returns the same list. No-op safe on missing fields."""
    for t in trades:
        sym = t.get("sym") or t.get("symbol") or ""
        t["cap"] = cap_for(sym, t.get("entry_date") or t.get("trade_at") or t.get("trade_date"))
    return trades


def cap_summary(trades: List[Dict]) -> Dict[str, int]:
    """Count of trades per cap segment (for summary.json / displays)."""
    out: Dict[str, int] = {}
    for t in trades:
        c = t.get("cap") or cap_for(t.get("sym") or t.get("symbol") or "",
                                    t.get("entry_date") or t.get("trade_at"))
        out[c] = out.get(c, 0) + 1
    return out
