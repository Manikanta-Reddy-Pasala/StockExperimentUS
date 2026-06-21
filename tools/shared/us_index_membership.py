"""Point-in-time US index membership — survivorship-correct universe gating.

Loads a membership CSV (schema: ``symbol,start_date,end_date``; half-open
intervals where ``end_date == 2099-12-31`` means "still a member") and answers
"which symbols were index members on date D?".

Ticker normalization: membership files use the dotted form (``BRK.B``) while the
price DB / universe CSVs use the dash form (``BRK-B``). Both ``load_membership``
and ``eligible_at`` normalize ``.`` and ``-`` to a common key so callers can
match either form. ``eligible_at`` returns symbols in BOTH spellings (dotted and
dashed) so an intersection with a dash-form panel (``cl.columns``) just works.
"""
from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache


def _norm(sym: str) -> str:
    """Canonical key: strip whitespace, fold '.'/'-' to '-' (DB/universe form)."""
    return sym.strip().upper().replace(".", "-")


@lru_cache(maxsize=None)
def load_membership(csv_path: str) -> tuple:
    """Parse a membership CSV into an immutable tuple of intervals.

    Returns a tuple of ``(norm_key, raw_symbol, start_date, end_date)`` rows
    (cached by path). ``norm_key`` is the dash-folded form; ``raw_symbol`` is the
    original spelling from the file. Dates are ``datetime.date``.
    """
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            sym = (r.get("symbol") or "").strip()
            if not sym:
                continue
            try:
                sd = date.fromisoformat(r["start_date"].strip())
                ed = date.fromisoformat(r["end_date"].strip())
            except (KeyError, ValueError):
                continue
            rows.append((_norm(sym), sym, sd, ed))
    return tuple(rows)


def eligible_at(intervals: tuple, on_date) -> set:
    """Symbols that are members on ``on_date`` (start <= on_date < end).

    ``intervals`` is the tuple returned by ``load_membership``. ``on_date`` may
    be a ``date``, ``datetime``, or pandas ``Timestamp`` (anything with
    ``.year/.month/.day`` or convertible via ``.date()``).

    Returns symbols in BOTH the dash form and the original dotted form so the
    result can be intersected with either a DB-style or dotted-style universe.
    """
    if hasattr(on_date, "date") and callable(getattr(on_date, "date")):
        # datetime, pandas/np Timestamp -> plain date (also normalizes the
        # date-subclass Timestamp, which would otherwise fail richcmp vs date)
        on_date = on_date.date()
    elif not isinstance(on_date, date):
        on_date = date.fromisoformat(str(on_date)[:10])

    out = set()
    for norm_key, raw_symbol, sd, ed in intervals:
        if sd <= on_date < ed:
            out.add(norm_key)
            out.add(raw_symbol)
    return out
