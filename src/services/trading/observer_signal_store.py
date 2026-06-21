"""Persist observer-mode signals into Postgres (partitioned by year).

Observer signals are written primarily as JSON files
(``/app/logs/observer/signals/{date}_{model}.json``). This helper ALSO upserts
each signal into the ``observer_signals`` table so they are SQL-queryable and
retained across container restarts. JSON write stays primary — callers wrap
``save_signal`` in a best-effort try/except so a DB outage never blocks signal
generation.

Schema (created by ``ensure_table``)::

    observer_signals(
        id          serial PRIMARY KEY,
        model_name  text NOT NULL,
        signal_date date NOT NULL,
        year        int  NOT NULL,
        regime_on   bool,
        targets     jsonb,
        payload     jsonb,
        created_at  timestamptz DEFAULT now(),
        UNIQUE(model_name, signal_date)
    )

with an index on ``(year, model_name)``. ``year`` is derived from
``signal_date`` (the payload's ``asof``) so the table is naturally
year-partitionable / year-filterable.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text

# Reuse the backtest's engine factory so DB config never drifts between the
# backtest, the live signal, and this store.
from tools.models.india_ports_us.backtest import get_engine

log = logging.getLogger(__name__)


_DDL = """
CREATE TABLE IF NOT EXISTS observer_signals (
    id          SERIAL PRIMARY KEY,
    model_name  TEXT NOT NULL,
    signal_date DATE NOT NULL,
    year        INT  NOT NULL,
    regime_on   BOOLEAN,
    targets     JSONB,
    payload     JSONB,
    created_at  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT observer_signals_model_date_uniq UNIQUE (model_name, signal_date)
);
CREATE INDEX IF NOT EXISTS observer_signals_year_model_idx
    ON observer_signals (year, model_name);
"""


def ensure_table(engine=None) -> None:
    """Create the ``observer_signals`` table + index if they don't exist."""
    eng = engine or get_engine()
    with eng.begin() as c:
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                c.execute(text(stmt))


def _parse_signal_date(payload: dict) -> date:
    """Resolve the signal date from the payload's ``asof`` (YYYY-MM-DD).

    Falls back to today's date if ``asof`` is missing/unparseable.
    """
    asof = payload.get("asof")
    if asof:
        try:
            return date.fromisoformat(str(asof)[:10])
        except (ValueError, TypeError):
            log.warning("observer_signal_store: bad asof %r, using today", asof)
    return datetime.now().date()


def save_signal(model_name: str, payload: dict, engine=None) -> Optional[int]:
    """Upsert one observer signal row. Returns the row id (or None on no-op).

    - ``signal_date`` = ``payload['asof']`` (the data's as-of date).
    - ``year``        = ``signal_date.year``.
    - ``regime_on``   = ``payload['regime_on']`` (bool, if present).
    - ``targets``     = ``payload['targets']`` (jsonb).
    - ``payload``     = the full dict (jsonb).

    ON CONFLICT (model_name, signal_date) DO UPDATE — re-running the same day
    overwrites in place (idempotent).

    Best-effort: callers should still wrap this in try/except. The table is
    created on demand so the very first call self-bootstraps.
    """
    eng = engine or get_engine()
    ensure_table(eng)

    signal_date = _parse_signal_date(payload)
    year = signal_date.year
    regime_on = payload.get("regime_on")
    targets = payload.get("targets")

    row = {
        "model_name": model_name,
        "signal_date": signal_date,
        "year": year,
        "regime_on": bool(regime_on) if regime_on is not None else None,
        "targets": json.dumps(targets) if targets is not None else None,
        "payload": json.dumps(payload, default=str),
    }
    with eng.begin() as c:
        rid = c.execute(text(
            """
            INSERT INTO observer_signals
                (model_name, signal_date, year, regime_on, targets, payload)
            VALUES
                (:model_name, :signal_date, :year, :regime_on,
                 CAST(:targets AS JSONB), CAST(:payload AS JSONB))
            ON CONFLICT (model_name, signal_date) DO UPDATE SET
                year       = EXCLUDED.year,
                regime_on  = EXCLUDED.regime_on,
                targets    = EXCLUDED.targets,
                payload    = EXCLUDED.payload,
                created_at = now()
            RETURNING id
            """
        ), row).scalar()
    log.info("observer_signals upsert: model=%s date=%s year=%s id=%s",
             model_name, signal_date, year, rid)
    return int(rid) if rid is not None else None
