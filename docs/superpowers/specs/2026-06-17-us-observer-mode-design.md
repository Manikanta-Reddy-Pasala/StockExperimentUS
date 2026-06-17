# US Observer Mode + UI Wiring — Design Spec

**Date:** 2026-06-17
**Status:** Approved for planning
**Approach:** A — register models in the existing admin registry + a JSON adapter; global `OBSERVER_MODE` lock; reuse the existing v2 UI + PWA.

## 1. Goal

Run the US trading system like the India experiment: **observer (signal-only) mode** — every model generates and displays its daily picks/target weights in the existing India-style v2 UI, and **no real orders are ever placed**. The UI is already an installable PWA; verify and lightly polish it.

Non-goals (YAGNI): position/P&L tracking, paper-fill simulation, live order routing, new page layouts, India CSS restyle, sourcing an external S&P400 constituent list.

## 2. Definitions

- **Observer mode** = signal-only. Scheduler → eToro signals → JSON artifact → UI. No order placement, no position/P&L tracking.
- **`OBSERVER_MODE`** = global boolean flag (env + `config.py`), default **true** in this deployment. It is the hard safety lock: when true, every order-placement code path is blocked and logs the intended (not placed) orders.

## 3. Current state (verified)

- `tools/live/us_executor.py --model book` computes the v2 book (MOM 45% / TQQQ 15% / BRK 40% over N100 + TQQQ + QQQ) and writes `logs/us_signals/{date}_{model}.json` with shape `{asof, model, why, nav, target_weights, orders}`. It *can* place IBKR orders; the scheduler runs it dry-run.
- `data_scheduler.py:generate_us_book_signal()` runs `us_executor --model book` daily at 13:45 (dry-run, logs only). Per-model momentum data/signal cron jobs are registered via each model's `tools/models/<name>/cron.py`.
- The v2 UI (`src/web/templates/v2/*`) fetches from `/admin/*` endpoints:
  - dashboard → `/admin/models/portfolio`, `/admin/signals/today`
  - picks → `/admin/<model_key>/ranking?top=5&recalc=1`
  - model_signals → `/admin/audit/signals?days=N`
- `MODEL_PATHS` (admin_routes.py:1807) registers 4 models: `momentum_n100_top5_max1`, `momentum_pseudo_n100_adv`, `midcap_narrow_60d_breakout`, `n20_daily_large_only`. Each has `signals_dir`, `ranking_dir`, `live_signal`, `extra_args`, `label`, `universe_path`. Endpoints parse the **momrot signal/ranking file format**.
- The US book (`logs/us_signals/`) is **not** in `MODEL_PATHS`, and its JSON shape differs from the momrot format → the UI cannot see it.
- `midcap_narrow_60d_breakout` points at `nifty_midcap150` (India universe) → no US/eToro data → empty on US.
- **PWA already exists**: `/manifest.json` + `/sw.js` Flask routes serving `static/manifest.json` + `static/sw.js`; `v2/base.html` has `<link rel="manifest">`, `theme-color`, `apple-touch-icon`, icons `icon-192.png`/`icon-512.png`/`icon.svg`, service-worker registration with update-on-`controllerchange`, and standalone-mode handling.

## 4. Design

### 4.1 Observed model set

| model_key | universe | change |
|---|---|---|
| momentum_n100_top5_max1 | N100 (US) | none |
| momentum_pseudo_n100_adv | pseudo-N100 (US) | none |
| n20_daily_large_only | N100∩ADV (US) | none |
| midcap_narrow_60d_breakout | **US midcap** | repoint universe (4.4) |
| **us_book** | N100+TQQQ+QQQ | **new registry entry + adapter** |

### 4.2 `us_book` registry entry

Add to `MODEL_PATHS`:
```python
"us_book": {
    "signals_dir": "<logs>/us_signals",
    "ranking_dir": "<logs>/us_signals",      # same dir; adapter derives ranking from target_weights
    "live_signal": "tools/live/us_executor.py",
    "extra_args": ["--model", "book"],
    "label": "US v2 Book (MOM/TQQQ/BRK) — Observer",
    "universe_path": None,
    "format": "us_book",                       # marks adapter routing (momrot is the default)
}
```
A `format` key distinguishes book-shaped JSON from momrot-shaped files. Default (absent) = momrot.

### 4.3 Observer adapter — `src/web/observer_adapter.py` (new)

Pure, side-effect-free functions translating the latest `us_signals/{date}_book.json` into the three shapes the existing endpoints already return. Endpoints check `MODEL_PATHS[key].get("format") == "us_book"` and route through the adapter instead of the momrot parser.

- `load_latest_book(signals_dir) -> dict | None` — newest `*_book.json` (by date in filename, tiebreak mtime).
- `to_signals_today(book) -> dict` — `{model, asof, why, picks:[{symbol, weight}], count}` matching `/admin/signals/today` item shape.
- `to_ranking(book, top) -> list[dict]` — `target_weights` sorted desc → `[{rank, symbol, weight, sleeve?}]` matching `/admin/<model>/ranking`.
- `to_portfolio(book) -> dict` — book weights as the "portfolio" row for `/admin/models/portfolio` (NAV from `nav`, holdings from `target_weights`).

The adapter never recomputes signals; `recalc=1` for `us_book` is a no-op that re-reads the latest artifact (recompute happens only in the scheduler via `us_executor`). The exact target field names are pinned to the existing momrot endpoint responses during implementation (read the endpoint return dicts; match keys exactly).

### 4.4 US midcap universe

- New `src/data/symbols/us_midcap.csv` = `nasdaq500.csv` − `nasdaq100.csv` (the US mid/small Nasdaq names; the India ports already use this exact pool as the "emerging" universe). Columns `Symbol,Series` to match the loader.
- Repoint `midcap_narrow_60d_breakout`: `universe_path` and its `extra_args --universe-file` → the US midcap file; update the model's backtest/live universe constant if it hardcodes `nifty_midcap150`.
- **No new data pull** — these symbols are already in the DB (`data_source='yfinance'` bucket, eToro-sourced, 4yr).

### 4.5 `OBSERVER_MODE` global lock

- Define in `config.py` (`OBSERVER_MODE = env bool, default True`) and document in `.env.production`.
- Enforce (defense in depth) at every order-placement path:
  - `tools/live/us_executor.py`: if `OBSERVER_MODE`, skip the IBKR place loop entirely (still compute + write the signal artifact), log `"OBSERVER: N intended orders, none placed"`. Applies even if `--place`/live flags are passed.
  - `src/web/admin_routes.py` `admin_run_signal` + rebalance endpoints: if `OBSERVER_MODE`, force `dry_run=true` and return `{observer_mode: true, message: "...signal-only..."}`.
- The lock is model-agnostic: because it gates the *shared* execution paths, all five models are observer by construction.

### 4.6 UI

- `v2/base.html`: OBSERVER badge in the header (small pill, theme-color background), rendered when `OBSERVER_MODE` is true (inject via a context processor or template global).
- `v2/settings.html`: read-only "Mode: OBSERVER (signal-only)" row.
- No layout/CSS redesign.

### 4.7 PWA (verify + polish)

- Verify `/manifest.json` and `/sw.js` serve HTTP 200 with correct MIME; app installs/standalone.
- `static/manifest.json`: ensure `name`/`short_name`/`description` reflect the observer app; `display: standalone`, `start_url: /`, theme/background colors, 192+512 icons present.
- `static/sw.js`: ensure the cache list pre-caches the v2 observer shell (`/`, `/picks`, `/portfolio`, `/history`, `/settings`, base CSS/JS) so the shell loads offline; bump cache version.

## 5. Data flow

```
data_scheduler (per-model cron + 13:45 book) 
  └─► signal generators (us_executor --model book; each model's live_signal.py)  [OBSERVER: signal-only]
        └─► JSON artifacts (logs/us_signals/*.json ; logs/<model>/signals|ranking/*.json)
              └─► /admin/* endpoints  (us_book via observer_adapter; others via momrot parser)
                    └─► v2 UI (dashboard / picks / model_signals / portfolio / history) + OBSERVER badge
                          └─► installable PWA (manifest + sw offline shell)
```

## 6. Testing

- `tests/test_observer_adapter.py`: sample `*_book.json` → `to_signals_today/to_ranking/to_portfolio` produce expected keys + ordering; missing/empty file → safe empties.
- `tests/test_observer_lock.py`: `us_executor` with `OBSERVER_MODE=true` computes + writes artifact but never calls `place_order` (mock broker); admin execute endpoint with flag returns `dry_run=true` / `observer_mode=true`.
- Endpoint smoke (Flask test client): `/admin/us_book/ranking` returns the book picks; `/manifest.json` + `/sw.js` return 200 with correct MIME.
- Midcap: `midcap_narrow` live/backtest on `us_midcap.csv` returns non-empty US names for the 4yr window.

## 7. Files touched

| File | Change |
|---|---|
| `config.py` | `OBSERVER_MODE` flag |
| `.env.production` | document `OBSERVER_MODE=true` |
| `tools/live/us_executor.py` | observer lock (skip place loop) |
| `src/web/admin_routes.py` | register `us_book`; repoint midcap; adapter routing in signals_today/ranking/portfolio; lock admin execute |
| `src/web/observer_adapter.py` | **new** — book JSON → endpoint shapes |
| `src/data/symbols/us_midcap.csv` | **new** — n500 − n100 |
| `tools/models/midcap_narrow_60d_breakout/*` | repoint universe constant if hardcoded |
| `src/web/templates/v2/base.html` | OBSERVER badge |
| `src/web/templates/v2/settings.html` | mode row |
| `src/web/static/manifest.json` | observer branding |
| `src/web/static/sw.js` | pre-cache observer shell + version bump |
| `tests/test_observer_adapter.py`, `tests/test_observer_lock.py` | **new** |

## 8. Risks / open items

- Adapter output keys must exactly match the existing momrot endpoint response schema so the v2 JS renders unchanged — pin by reading the endpoint return dicts during implementation.
- `MODEL_PATHS` uses absolute `/app/...` (container) paths; `us_book`/`us_midcap` entries must follow the same base-path convention the other models use (verify how the code resolves these in local vs container runs).
- midcap_narrow's selection logic was tuned on India midcap; on US midcap it will produce *some* signals but is not return-validated here (observer display only, acceptable for signal-only scope).
