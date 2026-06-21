"""
Admin Routes for Manual Triggers
Provides UI controls to manually trigger automated processes.
"""

from flask import Blueprint, render_template, jsonify, request
from datetime import datetime
from typing import Dict
import subprocess
import threading
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _tg_safe(text: str):
    """Best-effort Telegram alert. Never raises."""
    try:
        from tools.live.telegram_notify import send
        send(text, parse_mode="Markdown")
    except Exception:
        logger.debug("tg notify skipped", exc_info=True)

# Track running tasks (in-memory cache + database persistence)
running_tasks = {}


def save_task_to_db(task_id, task_data):
    """Save task state to database for persistence across page refreshes."""
    from src.models.database import get_database_manager
    from sqlalchemy import text
    import json

    db_manager = get_database_manager()
    with db_manager.get_session() as session:
        # Convert steps list to JSON
        steps_json = json.dumps(task_data.get('steps', []))

        # Upsert task
        query = text("""
            INSERT INTO admin_task_tracking
            (task_id, task_type, description, status, start_time, end_time, steps, output, error, updated_at)
            VALUES
            (:task_id, :task_type, :description, :status, :start_time, :end_time, CAST(:steps AS jsonb), :output, :error, NOW())
            ON CONFLICT (task_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                end_time = EXCLUDED.end_time,
                steps = EXCLUDED.steps,
                output = EXCLUDED.output,
                error = EXCLUDED.error,
                updated_at = NOW()
        """)

        session.execute(query, {
            'task_id': task_id,
            'task_type': task_data.get('type', 'unknown'),
            'description': task_data.get('description', ''),
            'status': task_data.get('status', 'pending'),
            'start_time': task_data.get('start_time'),
            'end_time': task_data.get('end_time'),
            'steps': steps_json,
            'output': task_data.get('output', ''),
            'error': task_data.get('error', '')
        })
        session.commit()


def get_task_from_db(task_id):
    """Get task state from database."""
    from src.models.database import get_database_manager
    from sqlalchemy import text
    import json

    db_manager = get_database_manager()
    with db_manager.get_session() as session:
        query = text("""
            SELECT task_id, task_type, description, status, start_time, end_time, steps, output, error
            FROM admin_task_tracking
            WHERE task_id = :task_id
        """)

        result = session.execute(query, {'task_id': task_id}).fetchone()

        if result:
            # PostgreSQL JSONB is already parsed as Python object, no need for json.loads()
            steps = result[6] if result[6] else []
            return {
                'type': result[1],
                'description': result[2],
                'status': result[3],
                'start_time': result[4].isoformat() if result[4] else None,
                'end_time': result[5].isoformat() if result[5] else None,
                'steps': steps if isinstance(steps, list) else json.loads(steps) if steps else [],
                'output': result[7] or '',
                'error': result[8] or ''
            }
    return None


def get_active_tasks_from_db():
    """Get all active (running) tasks from database."""
    from src.models.database import get_database_manager
    from sqlalchemy import text
    import json

    db_manager = get_database_manager()
    with db_manager.get_session() as session:
        query = text("""
            SELECT task_id, task_type, description, status, start_time, end_time, steps, output, error
            FROM admin_task_tracking
            WHERE status IN ('running', 'pending')
            OR (status IN ('failed', 'completed') AND updated_at > NOW() - INTERVAL '1 hour')
            ORDER BY created_at DESC
            LIMIT 10
        """)

        results = session.execute(query).fetchall()

        tasks = {}
        for row in results:
            # PostgreSQL JSONB is already parsed as Python object
            steps = row[6] if row[6] else []
            tasks[row[0]] = {
                'type': row[1],
                'description': row[2],
                'status': row[3],
                'start_time': row[4].isoformat() if row[4] else None,
                'end_time': row[5].isoformat() if row[5] else None,
                'steps': steps if isinstance(steps, list) else json.loads(steps) if steps else [],
                'output': row[7] or '',
                'error': row[8] or '',
                'failed': row[3] == 'failed',
                'completed': row[3] == 'completed'
            }

        return tasks


def run_command_async(task_id, command, description):
    """Run a command asynchronously and track its status.

    Persists task state to DB on every status change so the /admin/task/<id>/status
    poll works across multiple Gunicorn workers (in-memory running_tasks is
    per-process and is invisible to other workers).
    """
    try:
        task_data = {
            'type': 'command',
            'status': 'running',
            'description': description,
            'start_time': datetime.now().isoformat(),
            'output': '',
            'error': '',
            'steps': [],
        }
        running_tasks[task_id] = task_data
        try:
            save_task_to_db(task_id, task_data)
        except Exception as _e:
            logger.warning(f"save_task_to_db (start) failed for {task_id}: {_e}")

        # Get the project root directory (where run_pipeline.py lives)
        project_root = '/app' if os.path.exists('/app/run_pipeline.py') else os.getcwd()

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
            cwd=project_root
        )

        running_tasks[task_id]['status'] = 'completed' if result.returncode == 0 else 'failed'
        running_tasks[task_id]['output'] = result.stdout
        running_tasks[task_id]['error'] = result.stderr
        running_tasks[task_id]['return_code'] = result.returncode
        running_tasks[task_id]['end_time'] = datetime.now().isoformat()
        try:
            save_task_to_db(task_id, running_tasks[task_id])
        except Exception as _e:
            logger.warning(f"save_task_to_db (end) failed for {task_id}: {_e}")

    except subprocess.TimeoutExpired:
        running_tasks[task_id]['status'] = 'timeout'
        running_tasks[task_id]['error'] = 'Task timeout after 1 hour'
        running_tasks[task_id]['end_time'] = datetime.now().isoformat()
        try:
            save_task_to_db(task_id, running_tasks[task_id])
        except Exception:
            pass
    except Exception as e:
        running_tasks[task_id]['status'] = 'error'
        running_tasks[task_id]['error'] = str(e)
        running_tasks[task_id]['end_time'] = datetime.now().isoformat()
        try:
            save_task_to_db(task_id, running_tasks[task_id])
        except Exception:
            pass


@admin_bp.route('/')
def admin_dashboard():
    """Admin dashboard with manual trigger controls."""
    return render_template('admin/dashboard.html')


def run_function_async(task_id, func, description, task_type='generic', *args, **kwargs):
    """Run a Python function asynchronously and track its status."""
    try:
        task_data = {
            'type': task_type,
            'status': 'running',
            'description': description,
            'start_time': datetime.now().isoformat(),
            'output': '',
            'error': '',
            'steps': []
        }
        running_tasks[task_id] = task_data
        save_task_to_db(task_id, task_data)

        # Run the function
        result = func(*args, **kwargs)

        running_tasks[task_id]['status'] = 'completed'
        running_tasks[task_id]['output'] = str(result) if result else 'Completed successfully'
        running_tasks[task_id]['end_time'] = datetime.now().isoformat()
        save_task_to_db(task_id, running_tasks[task_id])

    except Exception as e:
        running_tasks[task_id]['status'] = 'failed'
        running_tasks[task_id]['error'] = str(e)
        running_tasks[task_id]['end_time'] = datetime.now().isoformat()
        save_task_to_db(task_id, running_tasks[task_id])
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)


@admin_bp.route('/trigger/pipeline', methods=['POST'])
def trigger_pipeline():
    """Trigger complete data pipeline."""
    task_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def run_pipeline():
        from src.services.data.pipeline_saga import PipelineSaga

        saga = PipelineSaga()
        result = saga.run_pipeline()
        return result

    thread = threading.Thread(
        target=run_function_async,
        args=(task_id, run_pipeline, 'Data Pipeline (4-step saga)')
    )
    thread.start()

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': 'Data pipeline started'
    })


@admin_bp.route('/trigger/all', methods=['POST'])
def trigger_all():
    """Trigger all processes in sequence."""
    base_task_id = f"all_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def run_all_tasks():
        """Run all tasks sequentially."""
        from src.services.data.pipeline_saga import PipelineSaga
        from src.models.database import get_database_manager

        overall_task_id = f"{base_task_id}_all"
        task_data = {
            'type': 'all',
            'status': 'running',
            'description': 'Data Pipeline',
            'start_time': datetime.now().isoformat(),
            'steps': [],
            'output': '',
            'error': ''
        }
        running_tasks[overall_task_id] = task_data
        save_task_to_db(overall_task_id, task_data)

        db_manager = get_database_manager()

        # Data Pipeline
        try:
            running_tasks[overall_task_id]['steps'].append({
                'name': 'pipeline',
                'description': 'Data Pipeline',
                'status': 'running',
                'start_time': datetime.now().isoformat()
            })
            save_task_to_db(overall_task_id, running_tasks[overall_task_id])

            saga = PipelineSaga()
            saga.run_pipeline()

            running_tasks[overall_task_id]['steps'][-1]['status'] = 'completed'
            running_tasks[overall_task_id]['steps'][-1]['end_time'] = datetime.now().isoformat()
            save_task_to_db(overall_task_id, running_tasks[overall_task_id])

        except Exception as e:
            running_tasks[overall_task_id]['steps'][-1]['status'] = 'failed'
            running_tasks[overall_task_id]['steps'][-1]['error'] = str(e)
            running_tasks[overall_task_id]['steps'][-1]['end_time'] = datetime.now().isoformat()
            running_tasks[overall_task_id]['error'] += f"\nPipeline failed: {str(e)}"
            save_task_to_db(overall_task_id, running_tasks[overall_task_id])
            logger.error(f"Pipeline failed: {e}", exc_info=True)

        failed_count = len([s for s in running_tasks[overall_task_id]['steps'] if s['status'] == 'failed'])
        running_tasks[overall_task_id]['status'] = 'completed' if failed_count == 0 else 'failed'
        running_tasks[overall_task_id]['end_time'] = datetime.now().isoformat()
        save_task_to_db(overall_task_id, running_tasks[overall_task_id])

    thread = threading.Thread(target=run_all_tasks)
    thread.start()

    return jsonify({
        'success': True,
        'task_id': f"{base_task_id}_all",
        'message': 'All tasks started sequentially'
    })


@admin_bp.route('/task/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    """Get status of a running task."""
    # Check in-memory first
    if task_id in running_tasks:
        return jsonify({
            'success': True,
            'task': running_tasks[task_id]
        })

    # Check database
    task_data = get_task_from_db(task_id)
    if task_data:
        # Add flags for UI
        task_data['failed'] = task_data['status'] == 'failed'
        task_data['completed'] = task_data['status'] == 'completed'
        if task_data['status'] == 'failed':
            task_data['failedSteps'] = [s for s in task_data.get('steps', []) if s.get('status') == 'failed']

        return jsonify({
            'success': True,
            'task': task_data
        })

    return jsonify({
        'success': False,
        'error': 'Task not found'
    }), 404


@admin_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """List all tasks."""
    # Get from database (includes completed/failed from last hour)
    db_tasks = get_active_tasks_from_db()

    # Merge with in-memory tasks
    all_tasks = {**db_tasks, **running_tasks}

    return jsonify({
        'success': True,
        'tasks': all_tasks
    })


@admin_bp.route('/tasks/active', methods=['GET'])
def get_active_tasks():
    """Get all active tasks (for page load)."""
    return list_tasks()


@admin_bp.route('/task/<task_id>/retry-failed', methods=['POST'])
def retry_failed_steps(task_id):
    """Retry only the failed steps of a task."""
    if task_id not in running_tasks:
        return jsonify({
            'success': False,
            'error': 'Task not found'
        }), 404

    task = running_tasks[task_id]

    # Get failed steps
    failed_steps = [step for step in task.get('steps', []) if step.get('status') == 'failed']

    if not failed_steps:
        return jsonify({
            'success': False,
            'error': 'No failed steps to retry'
        }), 400

    # Create a new task for retrying failed steps
    new_task_id = f"retry_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def retry_steps():
        """Retry failed steps only."""
        running_tasks[new_task_id] = {
            'status': 'running',
            'description': 'Retry Failed Steps',
            'start_time': datetime.now().isoformat(),
            'steps': [],
            'output': '',
            'error': ''
        }

        for step in failed_steps:
            step_name = step['name']
            command = None
            description = step['description']

            # Map step name to command
            if step_name == 'pipeline':
                command = ['python3', 'run_pipeline.py']
            elif step_name == 'csv_export':
                command = ['python3', '-c', 'from data_scheduler import export_daily_csv; export_daily_csv()']

            if not command:
                continue

            try:
                running_tasks[new_task_id]['steps'].append({
                    'name': step_name,
                    'description': description,
                    'status': 'running',
                    'start_time': datetime.now().isoformat()
                })

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )

                step_status = 'completed' if result.returncode == 0 else 'failed'
                running_tasks[new_task_id]['steps'][-1]['status'] = step_status
                running_tasks[new_task_id]['steps'][-1]['end_time'] = datetime.now().isoformat()
                running_tasks[new_task_id]['steps'][-1]['return_code'] = result.returncode

                if result.returncode != 0:
                    running_tasks[new_task_id]['error'] += f"\n{step_name} failed: {result.stderr}"

            except Exception as e:
                running_tasks[new_task_id]['steps'][-1]['status'] = 'error'
                running_tasks[new_task_id]['steps'][-1]['error'] = str(e)
                running_tasks[new_task_id]['error'] += f"\n{step_name} error: {str(e)}"

        running_tasks[new_task_id]['status'] = 'completed'
        running_tasks[new_task_id]['end_time'] = datetime.now().isoformat()

    thread = threading.Thread(target=retry_steps)
    thread.start()

    return jsonify({
        'success': True,
        'task_id': new_task_id,
        'message': f'Retrying {len(failed_steps)} failed steps',
        'failed_steps': [s['name'] for s in failed_steps]
    })


@admin_bp.route('/trigger/model/<model_name>', methods=['POST'])
def trigger_model_data_pull(model_name):
    """Trigger data pulls for a specific deployed model.

    The system is reduced to EXACTLY TWO OBSERVER-mode models (momentum_sp100,
    retest_sp500). Both use static CSV universes and the shared daily OHLCV
    pipeline — there are NO model-specific data_pull modules, so this manual
    trigger has nothing to run for them.
    """
    allowed = {}
    if model_name not in allowed:
        return jsonify({"success": False, "error": f"Unknown model: {model_name}"}), 400

    task_id = f"model_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    jobs = allowed[model_name]

    def run_model_jobs():
        import importlib
        for label, mod_name, func_name in jobs:
            try:
                mod = importlib.import_module(mod_name)
                getattr(mod, func_name)()
                logger.info(f"  ✅ {label}")
            except Exception as e:
                logger.error(f"  ❌ {label}: {e}", exc_info=True)

    thread = threading.Thread(
        target=run_function_async,
        args=(task_id, run_model_jobs, f"Model {model_name} data pull"),
    )
    thread.start()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": f"Data pull started for {model_name}",
        "jobs": [j[0] for j in jobs],
    })


@admin_bp.route('/system/models-status', methods=['GET'])
def models_status():
    """Per-model data sufficiency audit for the TWO OBSERVER-mode models.

    Validates trading days of data per symbol each model actually consumes,
    not generic row counts. Both models use static CSV universes, plain US
    tickers, data_source='yfinance'.

    momentum_sp100 (universe src/data/symbols/sp100.csv) and retest_sp500
    (universe src/data/symbols/nasdaq500.csv): for each universe symbol, count
    distinct trading-day bars in the last 300 calendar days; require >= 150
    trading days per symbol and >= 90% universe coverage, data <= 3d stale.
    """
    try:
        from src.models.database import get_database_manager
        from src.models.model_ledger_models import ModelSettings
        from sqlalchemy import text
        import json
        from pathlib import Path
        from datetime import date, timedelta

        today = date.today()
        db_manager = get_database_manager()

        # Runtime-derived 'wired' flag — data-driven, no hardcoding.
        # A model counts as WIRED only if BOTH:
        #   1. It has an entry in MODEL_PATHS (live_signal + executor route)
        #   2. model_settings.enabled = True (DB toggle; user controls via UI)
        # Disabled models or models with no MODEL_PATHS entry are UNWIRED.
        with db_manager.get_session() as _ws:
            enabled_map = {
                row.model_name: bool(row.enabled)
                for row in _ws.query(ModelSettings).all()
            }
        def _wired(name: str) -> bool:
            return (name in MODEL_PATHS) and bool(enabled_map.get(name, False))

        # Window for per-symbol trading-day coverage. The two observer models
        # need deep history (retest = 126d momentum + 20-EMA; momentum_sp100 =
        # 126d blend), so look back ~300 calendar days and require >= 150
        # trading days per symbol.
        window_calendar_days = 300
        min_trading_days = 150
        since = today - timedelta(days=window_calendar_days)

        # The system is reduced to EXACTLY TWO OBSERVER-mode models. Both use
        # static CSV universes, plain US tickers, data_source='yfinance'. Audit
        # each generically against its universe CSV.
        # (name, type, universe_csv) — universe CSV is repo-relative.
        OBSERVER_MODELS = [
            ("momentum_sp100", "equity", "src/data/symbols/sp100.csv"),
            ("retest_sp500", "equity", "src/data/symbols/nasdaq500.csv"),
        ]

        def _load_universe_csv(rel_path):
            """Read a (Symbol,Series) CSV → list of EQ symbols (plain tickers)."""
            import csv as _csv
            for base in ("/app", str(Path(__file__).resolve().parents[3])):
                fp = Path(base) / rel_path
                if fp.exists():
                    out = []
                    try:
                        with open(fp) as f:
                            for r in _csv.DictReader(f):
                                if (r.get("Series", "EQ") or "EQ").strip() == "EQ":
                                    out.append(r["Symbol"].strip())
                    except Exception:
                        return []
                    return out
            return []

        models = []
        with db_manager.get_session() as session:
            for name, mtype, uni_csv in OBSERVER_MODELS:
                uni = _load_universe_csv(uni_csv)
                per_sym_days = {}
                latest_per_sym = {}
                if uni:
                    rows = session.execute(text("""
                        SELECT symbol,
                               COUNT(DISTINCT date) AS days,
                               MAX(date) AS latest
                        FROM historical_data
                        WHERE symbol = ANY(:syms)
                          AND data_source = 'yfinance'
                          AND date >= :since
                        GROUP BY symbol
                    """), {"syms": uni, "since": since}).fetchall()
                    per_sym_days = {r.symbol: int(r.days) for r in rows}
                    latest_per_sym = {r.symbol: r.latest for r in rows}

                ok_syms = [s for s in uni if per_sym_days.get(s, 0) >= min_trading_days]
                under_syms = [s for s in uni if 0 < per_sym_days.get(s, 0) < min_trading_days]
                missing_syms = [s for s in uni if s not in per_sym_days]
                latest_dates = [d for d in latest_per_sym.values() if d]
                overall_latest = max(latest_dates) if latest_dates else None
                stale_days = (today - overall_latest).days if overall_latest else 999
                cov_pct = (len(ok_syms) / len(uni) * 100) if uni else 0
                data_ok = (len(uni) >= 50 and cov_pct >= 90 and stale_days <= 3)

                worst = sorted(per_sym_days.items(), key=lambda kv: kv[1])[:5]
                worst_str = ", ".join(f"{s}={d}" for s, d in worst) if worst else ""

                models.append({
                    "name": name,
                    "type": mtype,
                    "wired": _wired(name),
                    "data_sufficient": bool(data_ok),
                    "items": [
                        {"label": "Universe size",
                         "value": len(uni),
                         "required": ">= 50 syms",
                         "ok": len(uni) >= 50,
                         "extra": uni_csv},
                        {"label": f"Symbols w/ >= {min_trading_days} trading days "
                                  f"(last {window_calendar_days}d)",
                         "value": f"{len(ok_syms)} / {len(uni)}",
                         "required": ">= 90% coverage",
                         "ok": cov_pct >= 90,
                         "extra": f"{cov_pct:.1f}% coverage"},
                        {"label": "Symbols below threshold",
                         "value": len(under_syms),
                         "required": "0 (allow few)",
                         "ok": len(under_syms) <= 25,
                         "extra": worst_str},
                        {"label": "Symbols completely missing",
                         "value": len(missing_syms),
                         "required": "0",
                         "ok": len(missing_syms) == 0},
                        {"label": "Latest equity close",
                         "value": overall_latest.isoformat() if overall_latest else "—",
                         "required": "<= 3d old (holiday OK)",
                         "ok": stale_days <= 3,
                         "extra": f"{stale_days}d old"},
                    ],
                })

        return jsonify({"success": True, "models": models, "as_of": today.isoformat()})

    except Exception as e:
        logger.error(f"Models status error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/system/status', methods=['GET'])
def system_status():
    """Get system status."""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text

        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            # Get database stats. US deploy pulls eToro straight into
            # historical_data (the `stocks` master table is unused/empty), so the
            # tradeable-universe count = distinct symbols in historical_data.
            stocks_stats = session.execute(text("""
                SELECT
                    COUNT(DISTINCT symbol) as total_stocks,
                    COUNT(DISTINCT symbol) as with_price,
                    0 as with_market_cap,
                    MAX(date) as last_updated
                FROM historical_data
                WHERE data_source = 'yfinance'
            """)).fetchone()

            history_stats = session.execute(text("""
                SELECT
                    COUNT(DISTINCT symbol) as symbols,
                    COUNT(*) as records,
                    MAX(date) as latest_date
                FROM historical_data
            """)).fetchone()

            tech_stats = session.execute(text("""
                SELECT
                    COUNT(DISTINCT symbol) as symbols,
                    MAX(date) as latest_date
                FROM technical_indicators
            """)).fetchone()

            snapshot_stats = session.execute(text("""
                SELECT
                    COUNT(*) as total_snapshots,
                    COUNT(DISTINCT date) as unique_dates,
                    MAX(date) as latest_date
                FROM daily_suggested_stocks
            """)).fetchone()

            return jsonify({
                'success': True,
                'status': {
                    'stocks': {
                        'total': stocks_stats.total_stocks,
                        'with_price': stocks_stats.with_price,
                        'with_market_cap': stocks_stats.with_market_cap,
                        'last_updated': stocks_stats.last_updated.isoformat() if stocks_stats.last_updated else None
                    },
                    'historical_data': {
                        'symbols': history_stats.symbols,
                        'records': history_stats.records,
                        'latest_date': history_stats.latest_date.isoformat() if history_stats.latest_date else None
                    },
                    'technical_indicators': {
                        'symbols': tech_stats.symbols,
                        'latest_date': tech_stats.latest_date.isoformat() if tech_stats.latest_date else None
                    },
                    'daily_snapshots': {
                        'total': snapshot_stats.total_snapshots,
                        'unique_dates': snapshot_stats.unique_dates,
                        'latest_date': snapshot_stats.latest_date.isoformat() if snapshot_stats.latest_date else None
                    }
                }
            })

    except Exception as e:
        logger.error(f"System status error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Per-model capital ledger (multi-model portfolio tracking)
# =============================================================================

@admin_bp.route('/models/portfolio', methods=['GET'])
def get_model_portfolio():
    """Per-model + aggregate stats: allocated, NAV, cash, position, PnL,
    plus lifetime broker txn charges (BUY / SELL / TOTAL).

    Used by dashboard cards. Includes MTM if last close available.
    """
    try:
        from src.services.trading.model_ledger_service import (
            get_portfolio_stats, ensure_models_seeded,
        )
        from src.models.database import get_database_manager
        from sqlalchemy import text

        ensure_models_seeded()
        stats = get_portfolio_stats(price_lookup=_live_mtm_lookup_for_model(None))

        # Layer on per-model broker txn charges (lifetime sum of audit_orders.charges_inr)
        try:
            db = get_database_manager()
            with db.get_session() as s:
                rows = s.execute(text("""
                    SELECT COALESCE(model_name,'(unattributed)') AS m, side,
                           COALESCE(SUM(charges_inr),0) AS c
                    FROM audit_orders
                    WHERE status IN ('placed','filled','partial')
                    GROUP BY model_name, side
                """)).fetchall()
            ch_map = {}
            for r in rows:
                blk = ch_map.setdefault(r.m, {"buy": 0.0, "sell": 0.0})
                if r.side == "BUY":
                    blk["buy"] = float(r.c or 0)
                elif r.side == "SELL":
                    blk["sell"] = float(r.c or 0)
            for m in stats.get("models", []):
                blk = ch_map.get(m["model_name"], {"buy": 0.0, "sell": 0.0})
                m["buy_txn_charges"] = round(blk["buy"], 2)
                m["sell_txn_charges"] = round(blk["sell"], 2)
                m["total_txn_charges"] = round(blk["buy"] + blk["sell"], 2)
            total_buy = sum(m["buy_txn_charges"] for m in stats.get("models", []))
            total_sell = sum(m["sell_txn_charges"] for m in stats.get("models", []))
            if "total" in stats:
                stats["total"]["buy_txn_charges"] = round(total_buy, 2)
                stats["total"]["sell_txn_charges"] = round(total_sell, 2)
                stats["total"]["total_txn_charges"] = round(total_buy + total_sell, 2)
        except Exception as _e:
            logger.debug(f"charges enrich failed: {_e}")

        # Per-model BUY charges for the CURRENT open position only (latest
        # filled BUY matching open_symbol). Lets the dashboard reconcile
        # Allocated = Cost Basis + Open-Pos Charges + Idle Cash + Realized.
        try:
            db = get_database_manager()
            with db.get_session() as s:
                for m in stats.get("models", []):
                    m["entry_charges_open"] = 0.0
                    open_sym = m.get("open_symbol")
                    if not open_sym:
                        continue
                    bare = open_sym.upper().replace("NSE:", "").replace("-EQ", "")
                    r = s.execute(text("""
                        SELECT COALESCE(charges_inr, 0) AS c
                        FROM audit_orders
                        WHERE model_name = :m
                          AND side = 'BUY'
                          AND status IN ('placed','filled','partial')
                          AND (UPPER(symbol) = :bare OR UPPER(symbol) = :fyers)
                        ORDER BY placed_at DESC NULLS LAST, id DESC
                        LIMIT 1
                    """), {"m": m["model_name"], "bare": bare,
                           "fyers": f"NSE:{bare}-EQ"}).fetchone()
                    if r and r.c:
                        m["entry_charges_open"] = round(float(r.c), 2)
        except Exception as _e:
            logger.debug(f"open-pos charges enrich failed: {_e}")

        return jsonify({"success": True, **stats})
    except Exception as e:
        logger.error(f"models portfolio error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/settings', methods=['GET'])
def list_model_settings():
    try:
        from src.services.trading.model_ledger_service import (
            get_all_settings, ensure_models_seeded,
        )
        ensure_models_seeded()
        return jsonify({"success": True, "settings": get_all_settings()})
    except Exception as e:
        logger.error(f"models settings error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/deposit', methods=['POST'])
def deposit_to_model(model_name):
    """Add cash to a model (monthly top-up). Increases allocated + cash."""
    try:
        from src.services.trading.model_ledger_service import deposit
        data = request.get_json() or {}
        amt = float(data.get("amount", 0))
        result = deposit(model_name, amt)
        _tg_safe(
            f"💰 *Deposit* `{model_name}` ₹{amt:,.2f}\n"
            f"New cash: ₹{result.get('cash', 0):,.2f}"
        )
        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"deposit error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/withdraw', methods=['POST'])
def withdraw_from_model(model_name):
    """Pull cash out of a model. Decreases allocated + cash."""
    try:
        from src.services.trading.model_ledger_service import withdraw
        data = request.get_json() or {}
        amt = float(data.get("amount", 0))
        result = withdraw(model_name, amt)
        _tg_safe(
            f"💸 *Withdraw* `{model_name}` ₹{amt:,.2f}\n"
            f"Remaining cash: ₹{result.get('cash', 0):,.2f}"
        )
        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"withdraw error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/bootstrap', methods=['POST'])
def bootstrap_model(model_name):
    """Auto-migrate a legacy JSON ledger into model_ledger.

    Body: {cash_buffer: optional float}  — extra liquid cash beyond
    position cost (e.g. unused balance from last buy).

    The system is now OBSERVER-only (momentum_sp100, retest_sp500) — these
    models have no JSON ledgers and place no orders, so there is nothing to
    bootstrap. JSON_PATHS is intentionally empty.
    """
    JSON_PATHS = {
        # Observer-only models have no legacy JSON ledgers.
    }
    try:
        from src.services.trading.model_ledger_service import (
            auto_bootstrap_from_json_ledger,
        )
        path = JSON_PATHS.get(model_name)
        if not path:
            return jsonify({
                "success": False,
                "error": f"No legacy JSON ledger known for {model_name}"
            }), 400
        data = request.get_json() or {}
        cash_buffer = float(data.get("cash_buffer", 0))
        return jsonify({
            "success": True,
            **auto_bootstrap_from_json_ledger(path, model_name, cash_buffer),
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"bootstrap error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/reset', methods=['POST'])
def reset_model_route(model_name):
    """Hard reset model ledger to zero. Audit trail preserved."""
    try:
        from src.services.trading.model_ledger_service import reset_model
        result = reset_model(model_name)
        _tg_safe(
            f"⚠️ *Model RESET* `{model_name}`\n"
            f"Ledger zeroed. Audit trail preserved."
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        logger.error(f"reset model error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/enabled', methods=['POST'])
def toggle_model_enabled(model_name):
    try:
        from src.services.trading.model_ledger_service import set_enabled
        data = request.get_json() or {}
        new_state = bool(data.get("enabled"))
        settings = set_enabled(model_name, new_state)
        _tg_safe(
            f"{'✅' if new_state else '⏸️'} *Model "
            f"{'ENABLED' if new_state else 'DISABLED'}* `{model_name}`"
        )
        return jsonify({"success": True, "settings": settings})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"toggle enabled error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/seed-position', methods=['POST'])
def seed_model_position(model_name):
    """Bootstrap a model's open position (no Fyers order).

    Body: {symbol, qty, entry_px, entry_date}
    """
    try:
        from src.services.trading.model_ledger_service import seed_position
        data = request.get_json() or {}
        ledger = seed_position(
            model_name,
            symbol=data["symbol"],
            qty=int(data["qty"]),
            entry_px=float(data["entry_px"]),
            entry_date_str=data["entry_date"],
        )
        return jsonify({"success": True, "ledger": ledger})
    except (KeyError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"seed position error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/reset-position', methods=['POST'])
def reset_model_position(model_name):
    """Mark model as flat. Reconciliation tool — no Fyers order placed."""
    try:
        from src.services.trading.model_ledger_service import reset_position
        return jsonify({"success": True, "ledger": reset_position(model_name)})
    except Exception as e:
        logger.error(f"reset position error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/trades', methods=['GET'])
def model_trade_history(model_name):
    try:
        from src.services.trading.model_ledger_service import get_trades
        limit = int(request.args.get("limit", 50))
        return jsonify({
            "success": True,
            "trades": get_trades(model_name, limit=limit),
        })
    except Exception as e:
        logger.error(f"trade history error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/slippage-summary', methods=['GET'])
def slippage_summary():
    """Per-model fill-drift roll-up for the dashboard — computed from the SAME
    source as the per-trade History column (model_trades fill price vs the
    backtest daily-open reference), so card totals equal the sum of trade-level
    drifts.

    GAIN convention: mean_cost / cost_usd +ve = filled better than the backtest,
    -ve = slippage loss. worst_cost = the single worst (most negative) fill.
    """
    try:
        from src.services.trading.model_ledger_service import get_trades
        from src.models.model_ledger_models import ModelLedger
        from src.models.database import get_database_manager
        from tools.shared.intraday_fill import exec_raw_open

        db = get_database_manager()
        with db.get_session() as s:
            model_names = sorted({l.model_name for l in s.query(ModelLedger).all()
                                  if l.model_name})

        models, fills = [], []
        all_g, all_usd = [], 0.0
        for m in model_names:
            try:
                trades = get_trades(m, limit=5000)
            except Exception:
                trades = []
            gains, usd, last = [], 0.0, None
            for t in trades:
                side = (t.get("side") or "").upper()
                if side not in ("BUY", "SELL"):
                    continue
                sym = t.get("symbol") or ""
                px = float(t.get("price") or 0)
                ta = str(t.get("trade_at") or t.get("trade_date") or "")[:10]
                if not sym or px <= 0 or len(ta) != 10:
                    continue
                exp = exec_raw_open(sym, ta, m, side)
                if not exp or exp <= 0:
                    continue
                drift = (px / exp - 1) * 100
                gain = -drift if side == "BUY" else drift
                cusd = float(t.get("qty") or 0) * ((exp - px) if side == "BUY" else (px - exp))
                gains.append(gain)
                usd += cusd
                last = max(last, ta) if last else ta
                fills.append({"model": m, "date": ta, "side": side,
                              "symbol": sym.replace("NASDAQ:", "").replace("-EQ", ""),
                              "expected": round(exp, 2), "fill": round(px, 2),
                              "drift_pct": round(gain, 3), "cost_usd": round(cusd, 2)})
            if not gains:
                continue
            all_g += gains
            all_usd += usd
            recent = gains[-20:]
            models.append({
                "model": m, "n": len(gains),
                "mean_cost": round(sum(gains) / len(gains), 3),
                "recent_cost": round(sum(recent) / len(recent), 3),
                "worst_cost": round(min(gains), 3),
                "cost_usd": round(usd, 2),
                "last_date": last,
            })
        models.sort(key=lambda x: x["mean_cost"])  # worst (most loss) first
        overall = ({"n": len(all_g),
                    "mean_cost": round(sum(all_g) / len(all_g), 3),
                    "cost_usd": round(all_usd, 2),
                    "worst": round(min(all_g), 3)} if all_g
                   else {"n": 0, "mean_cost": None, "cost_usd": 0, "worst": None})
        fills.sort(key=lambda x: x["date"], reverse=True)
        return jsonify({"success": True, "overall": overall,
                        "models": models, "fills": fills[:200]})
    except Exception as e:
        logger.error(f"slippage-summary error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# Per-model Balance Sheet + Transactions (T11)
# =============================================================================
#
# Three endpoints power the per-model "Balance Sheet & Transactions" UI page:
#
#   GET /admin/<m>/balance-sheet   — structured invested / cash / P&L / NAV JSON
#   GET /admin/<m>/trade-history   — every BUY/SELL/DEPOSIT/WITHDRAW + summary
#   GET /admin/models/<m>/detail   — renders v2/model_detail.html
#
# All math is sourced from model_ledger_service (single source of truth).
# Live MTM uses the latest historical_data close — same lookup as the
# portfolio + triggers-status endpoints so numbers reconcile.

def _resolve_live_prices(symbols):
    """Batch-resolve LTP for the given symbols (any mix of 'HFCL' or
    'NSE:HFCL-EQ'). Tries real-time Fyers quotes first, falls back to
    historical_data latest close. Returns {bare_symbol: float} — caller
    should normalise lookups by stripping NSE:/-EQ.

    Pre-resolving up front (rather than per-row inside get_portfolio_stats)
    avoids scoped-session conflicts that detach ModelLedger rows.
    """
    from sqlalchemy import text
    from src.models.database import get_database_manager

    bare_set = sorted({(s or "").replace("NSE:", "").replace("-EQ", "")
                       for s in symbols if s})
    out: dict = {}
    if not bare_set:
        return out
    fyers_syms = [f"NSE:{b}-EQ" for b in bare_set]
    try:
        from src.services.brokers.ibkr import IBKRBrokerService
        svc = IBKRBrokerService()
        qr = svc.quotes_multiple(1, fyers_syms) or {}
        for fs, qd in (qr.get("data") or {}).items():
            b = fs.replace("NSE:", "").replace("-EQ", "")
            v = float((qd or {}).get("ltp") or 0)
            if v > 0:
                out[b] = v
    except Exception as e:
        logger.warning(f"Fyers quotes batch failed: {e}")
    missing = [b for b in bare_set if b not in out]
    if missing:
        try:
            db = get_database_manager()
            with db.get_session() as s:
                for b in missing:
                    fs = f"NSE:{b}-EQ"
                    r = s.execute(text(
                        "SELECT close FROM historical_data "
                        "WHERE symbol = :s OR symbol = :fs "
                        "ORDER BY date DESC LIMIT 1"
                    ), {"s": b, "fs": fs}).fetchone()
                    if r:
                        out[b] = float(r.close)
        except Exception as e:
            logger.warning(f"DB close fallback failed: {e}")
    return out


def _live_mtm_lookup_for_model(model_name):
    """Pre-resolve the given model's open-position MTM and return a closure
    suitable for get_portfolio_stats(price_lookup=...)."""
    from src.models.model_ledger_models import ModelLedger
    from src.models.database import get_database_manager
    db = get_database_manager()
    with db.get_session() as s:
        rows = s.query(ModelLedger).all()
        # Pre-extract open_symbols inside session — values are primitives,
        # safe to use after exit.
        open_syms = [l.open_symbol for l in rows if l.open_symbol]
    prices = _resolve_live_prices(open_syms)

    def _lookup(sym):
        return prices.get((sym or "").replace("NSE:", "").replace("-EQ", ""))

    return _lookup


@admin_bp.route('/<model_name>/balance-sheet', methods=['GET'])
def model_balance_sheet(model_name):
    """Per-model balance sheet (invested, cash, open position, P&L, NAV).

    Shape (kept stable for the UI):
      {
        model_name, as_of (ISO),
        enabled, label,
        invested_amount, cash,
        open_position: { symbol, qty, entry_px, entry_date,
                         current_px, position_value,
                         unrealized_pnl, unrealized_pct } | null,
        realized_pnl, unrealized_pnl, total_pnl, nav, return_pct,
        total_trades, wins, losses, win_rate_pct
      }
    """
    try:
        from src.services.trading.model_ledger_service import (
            ensure_models_seeded, get_portfolio_stats,
        )
        from src.models.database import get_database_manager
        from sqlalchemy import text

        ensure_models_seeded()
        stats = get_portfolio_stats(price_lookup=_live_mtm_lookup_for_model(model_name))

        per_model = next(
            (m for m in stats["models"] if m["model_name"] == model_name),
            None,
        )
        if per_model is None:
            return jsonify({
                "success": False,
                "error": f"Unknown model: {model_name}",
            }), 404

        invested = per_model.get("invested_amount", 0.0) or 0.0
        cash = per_model.get("cash", 0.0) or 0.0
        pos_value = per_model.get("position_value", 0.0) or 0.0
        realized = per_model.get("realized_pnl", 0.0) or 0.0
        nav = per_model.get("nav", 0.0) or 0.0
        # total_pnl == NAV - invested (consistent with portfolio totals)
        total_pnl = nav - invested
        # unrealized = open-position MTM less entry cost
        open_position = None
        entry_cost_open = 0.0
        entry_charges_open = 0.0
        unrealized_pnl = 0.0
        unrealized_pct = 0.0
        if per_model.get("open_symbol") and per_model.get("open_qty"):
            qty = per_model["open_qty"]
            entry_px = per_model.get("open_entry_px") or 0.0
            current_px = (
                per_model.get("open_mtm_price")
                or per_model.get("open_entry_px")
                or 0.0
            )
            entry_cost_open = float(qty) * float(entry_px)
            unrealized_pnl = float(pos_value) - entry_cost_open
            unrealized_pct = (
                (unrealized_pnl / entry_cost_open * 100.0)
                if entry_cost_open > 0 else 0.0
            )
            # BUY-side charges for the currently held position. Pulled from
            # audit_orders by matching the latest filled BUY for this model +
            # bare symbol (ledger stores NSE:XXX-EQ form; audit_orders also
            # stores Fyers form but be tolerant of either).
            try:
                from src.models.database import get_database_manager as _gdb
                _db = _gdb()
                bare = (per_model["open_symbol"] or "").upper()
                bare = bare.replace("NSE:", "").replace("-EQ", "")
                with _db.get_session() as _s:
                    row = _s.execute(text("""
                        SELECT COALESCE(charges_inr, 0) AS c
                        FROM audit_orders
                        WHERE model_name = :m
                          AND side = 'BUY'
                          AND status IN ('placed','filled','partial')
                          AND (
                              UPPER(symbol) = :sym_bare
                           OR UPPER(symbol) = :sym_fyers
                          )
                        ORDER BY placed_at DESC NULLS LAST, id DESC
                        LIMIT 1
                    """), {
                        "m": model_name,
                        "sym_bare": bare,
                        "sym_fyers": f"NSE:{bare}-EQ",
                    }).fetchone()
                if row and row.c:
                    entry_charges_open = float(row.c)
            except Exception as _e:
                logger.debug(f"open-pos charges lookup failed: {_e}")
            open_position = {
                "symbol": per_model["open_symbol"],
                "qty": qty,
                "entry_px": entry_px,
                "entry_date": per_model.get("open_entry_date"),
                "current_px": current_px,
                "entry_cost": round(entry_cost_open, 2),
                "entry_charges": round(entry_charges_open, 2),
                "position_value": pos_value,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pct": round(unrealized_pct, 2),
            }

        return_pct = (total_pnl / invested * 100.0) if invested > 0 else 0.0

        # Lookup pretty label if available in MODEL_PATHS
        label = MODEL_PATHS.get(model_name, {}).get("label", model_name)

        # Lifetime broker txn charges (audit_orders sum)
        buy_charges = sell_charges = 0.0
        try:
            from src.models.database import get_database_manager as _gdb
            _db = _gdb()
            with _db.get_session() as _s:
                _r = _s.execute(text("""
                    SELECT side, COALESCE(SUM(charges_inr),0) AS c
                    FROM audit_orders
                    WHERE model_name = :m AND status IN ('placed','filled','partial')
                    GROUP BY side
                """), {"m": model_name}).fetchall()
            for row in _r:
                if row.side == "BUY":
                    buy_charges = float(row.c or 0)
                elif row.side == "SELL":
                    sell_charges = float(row.c or 0)
        except Exception as _e:
            logger.debug(f"balance-sheet charges enrich failed: {_e}")

        # realized_pnl in DB is net of sell-side charges (record_sell subtracts
        # sell_chg from sale proceeds before computing pnl). Gross = pure price-
        # diff P&L of closed trades = realized_db + sell_chg_lifetime.
        # Surfacing both lets the UI build an identity that sums exactly to
        # allocated without double-counting sell charges:
        #   alloc = cash + cost_basis + buy_chg + sell_chg - realized_gross
        realized_gross = float(realized) + sell_charges

        return jsonify({
            "success": True,
            "model_name": model_name,
            "label": label,
            "enabled": bool(per_model.get("enabled")),
            "as_of": stats.get("as_of") or datetime.now().isoformat(),  # IST
            "invested_amount": round(float(invested), 2),
            "cash": round(float(cash), 2),
            "open_position": open_position,
            # Top-level mirror so UIs can render cost-basis + buy-charges rows
            # without drilling into open_position. Zero when flat.
            "entry_cost_open": round(float(entry_cost_open), 2),
            "entry_charges_open": round(float(entry_charges_open), 2),
            "realized_pnl": round(float(realized), 2),
            "realized_pnl_gross": round(realized_gross, 2),
            "unrealized_pnl": round(float(unrealized_pnl), 2),
            "total_pnl": round(float(total_pnl), 2),
            "nav": round(float(nav), 2),
            "return_pct": round(float(return_pct), 2),
            "total_trades": per_model.get("total_trades", 0) or 0,
            "wins": per_model.get("wins", 0) or 0,
            "losses": per_model.get("losses", 0) or 0,
            "win_rate_pct": per_model.get("win_rate_pct", 0) or 0,
            "buy_txn_charges": round(buy_charges, 2),
            "sell_txn_charges": round(sell_charges, 2),
            "total_txn_charges": round(buy_charges + sell_charges, 2),
        })
    except Exception as e:
        logger.error(f"balance-sheet error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/<model_name>/trade-history', methods=['GET'])
def model_trade_history_full(model_name):
    """Per-model transaction list + summary roll-up.

    Shape:
      {
        model_name,
        trades: [ {id, trade_at, side, symbol, qty, price, value,
                   pnl, reason, fyers_order_id, model_name}, ... ],
        summary: {
          total_buys, total_sells,
          total_deposits, total_withdrawals,
          total_buy_value, total_sell_value,
          total_pnl, wins, losses, win_rate_pct
        }
      }

    Note: returns ALL trades by default (no limit) so the UI table shows
    the complete history. Pass ?limit=N to truncate.
    """
    try:
        from src.services.trading.model_ledger_service import get_trades

        raw_limit = request.args.get("limit")
        # Default: large enough to show full history. Cap at 5000 for safety.
        limit = int(raw_limit) if raw_limit else 5000
        limit = max(1, min(limit, 5000))

        trades = get_trades(model_name, limit=limit)
        # Trades come newest-first from service; UI wants chronological too,
        # but newest-first is fine for transaction-list display.

        # PIT-shaped cap tag (large/mid/other) per trade — current-snapshot US.
        try:
            from tools.shared.cap_tag import cap_for
            for _t in trades:
                _t["cap"] = cap_for(_t.get("symbol", ""),
                                    _t.get("trade_at") or _t.get("trade_date"))
        except Exception as _ce:
            logger.debug(f"cap tag skipped: {_ce}")

        # Per-trade fill drift: each trade's own fill price vs the backtest
        # reference (daily open via exec_raw_open) for that (sym, date, side).
        # GAIN convention: +ve = filled better than backtest (green), -ve = loss
        # (red). drift_usd = qty x per-share edge.
        try:
            from tools.shared.intraday_fill import exec_raw_open
            for _t in trades:
                _t["drift_pct"] = None
                _t["drift_usd"] = None
                side = (_t.get("side") or "").upper()
                if side not in ("BUY", "SELL"):
                    continue
                sym = _t.get("symbol") or ""
                px = float(_t.get("price") or 0)
                ta = str(_t.get("trade_at") or _t.get("trade_date") or "")[:10]
                if not sym or px <= 0 or len(ta) != 10:
                    continue
                exp = exec_raw_open(sym, ta, model_name, side)
                if not exp or exp <= 0:
                    continue
                drift = (px / exp - 1) * 100
                gain = -drift if side == "BUY" else drift
                edge = (exp - px) if side == "BUY" else (px - exp)
                _t["drift_pct"] = round(gain, 3)
                _t["drift_usd"] = round(float(_t.get("qty") or 0) * edge, 2)
        except Exception as _de:
            logger.debug(f"drift compute skipped: {_de}")

        # Summary roll-up
        total_buys = 0
        total_sells = 0
        total_deposits = 0
        total_withdrawals = 0
        total_buy_value = 0.0
        total_sell_value = 0.0
        total_pnl = 0.0
        wins = 0
        losses = 0
        for t in trades:
            side = (t.get("side") or "").upper()
            val = float(t.get("value") or 0)
            pnl = t.get("pnl")
            if side == "BUY":
                total_buys += 1
                total_buy_value += val
            elif side == "SELL":
                total_sells += 1
                total_sell_value += val
                if pnl is not None:
                    pnl_f = float(pnl)
                    total_pnl += pnl_f
                    if pnl_f > 0:
                        wins += 1
                    elif pnl_f < 0:
                        losses += 1
            elif side == "DEPOSIT":
                total_deposits += 1
            elif side == "WITHDRAW":
                total_withdrawals += 1

        decided = wins + losses
        win_rate_pct = round(100.0 * wins / decided, 1) if decided else 0.0

        return jsonify({
            "success": True,
            "model_name": model_name,
            "trades": trades,
            "summary": {
                "total_buys": total_buys,
                "total_sells": total_sells,
                "total_deposits": total_deposits,
                "total_withdrawals": total_withdrawals,
                "total_buy_value": round(total_buy_value, 2),
                "total_sell_value": round(total_sell_value, 2),
                "total_pnl": round(total_pnl, 2),
                "wins": wins,
                "losses": losses,
                "win_rate_pct": win_rate_pct,
            },
        })
    except Exception as e:
        logger.error(f"trade-history error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/models/<model_name>/detail', methods=['GET'])
def model_detail_page(model_name):
    """Render the per-model "Balance Sheet & Transactions" UI page.

    Page itself is data-light — it fetches both endpoints client-side so the
    same JSON powers automation + humans.
    """
    label = MODEL_PATHS.get(model_name, {}).get("label", model_name)
    return render_template(
        "v2/model_detail.html",
        model_name=model_name,
        label=label,
    )


# =============================================================================
# Today's signals across all wired models (T10 dashboard widget)
# =============================================================================

# Map model_name -> list of (relative_filename_templates) under /app/logs.
# We probe each candidate path; first existing file wins. Templates support
# {date} placeholder (ISO yyyy-mm-dd).
_SIGNAL_PATHS = {
    # The two OBSERVER-mode models emit into the shared observer signals dir as
    # {date}_{model_name}.json (see tools/models/n40_largecap_weekly/cron.py).
    "momentum_sp100": [
        "/app/logs/observer/signals/{date}_momentum_sp100.json",
    ],
    "retest_sp500": [
        "/app/logs/observer/signals/{date}_retest_sp500.json",
    ],
}


@admin_bp.route('/signals/today', methods=['GET'])
def signals_today():
    """Aggregate today's emitted signals across all wired models.

    Reads each model's signals/{today}.json file. Returns array per model
    with metadata so the dashboard can render an "what fired today" widget.

    ?date=YYYY-MM-DD optionally overrides today (debugging / history view).
    """
    try:
        import json
        from pathlib import Path
        from datetime import date as _date

        date_str = request.args.get("date") or _date.today().isoformat()

        results = []
        for model_name, candidates in _SIGNAL_PATHS.items():
            found_path = None
            signals = []
            err = None
            for tmpl in candidates:
                p = Path(tmpl.format(date=date_str))
                if p.exists():
                    found_path = str(p)
                    try:
                        data = json.loads(p.read_text() or "[]")
                        if isinstance(data, list):
                            signals = data
                        elif isinstance(data, dict) and "signals" in data:
                            signals = data["signals"]
                    except Exception as e:
                        err = f"parse: {e}"
                    break

            results.append({
                "model_name": model_name,
                "date": date_str,
                "path": found_path,
                "count": len(signals),
                "signals": signals,
                "error": err,
                "has_file": found_path is not None,
            })

        total = sum(r["count"] for r in results)
        return jsonify({
            "success": True,
            "date": date_str,
            "total_signals": total,
            "models": results,
        })
    except Exception as e:
        logger.error(f"signals/today error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# T7 + T9 — Per-model Admin Triggers + Today's Picks
# =============================================================================

# Per-equity-model wiring: where each model writes signals/rankings, and how
# to invoke its live_signal.py. Kept here so future models = single-row diff.
# EXACTLY TWO OBSERVER-mode models (signal-only, NO executor). Both emit their
# target-holdings JSON into the shared observer signals dir.
MODEL_PATHS = {
    "momentum_sp100": {
        "signals_dir": "/app/logs/observer/signals",
        "ranking_dir": "/app/logs/observer/ranking",
        "live_signal": "tools/models/n40_largecap_weekly/live_signal.py",
        "extra_args": [
            "--universe-csv", "src/data/symbols/sp100.csv",
            "--lev", "1.0", "--top", "3", "--topadv", "50",
            "--signal", "blend", "--weights", "0.8,0.1,0.1",
        ],
        "label": "Momentum S&P 100 (n40 top-3 blend weights, OBSERVER)",
        "universe_path": "src/data/symbols/sp100.csv",
    },
    "retest_sp500": {
        "signals_dir": "/app/logs/observer/signals",
        "ranking_dir": "/app/logs/observer/ranking",
        "live_signal": "tools/models/india_ports_us/live_signal.py",
        "extra_args": [
            "--universe-csv", "src/data/symbols/nasdaq500.csv",
            "--membership-csv", "src/data/symbols/sp500_membership.csv",
            "--k", "2",
        ],
        "label": "Retest S&P 500 (India port top-2, OBSERVER)",
        "universe_path": "src/data/symbols/nasdaq500.csv",
    },
}


def _latest_signal_file(signals_dir: str):
    """Return (path, mtime_iso) of newest *.json signal file or (None, None)."""
    try:
        d = Path(signals_dir)
        if not d.exists():
            return None, None
        files = sorted(
            d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not files:
            return None, None
        f = files[0]
        return str(f), datetime.fromtimestamp(f.stat().st_mtime).isoformat()
    except Exception:
        return None, None


@admin_bp.route('/models/<model_name>/triggers/status', methods=['GET'])
def model_triggers_status(model_name):
    """Aggregate per-model status used by the Admin Triggers table row.

    Combines:
      - file-system newest signal file (mtime)
      - last execution row from model_trades table
      - current open position from model_ledger (via get_portfolio_stats)
      - settings: enabled flag, NAV, invested, win-rate, P&L %
    """
    try:
        from src.services.trading.model_ledger_service import (
            ensure_models_seeded, get_portfolio_stats,
        )
        from src.models.database import get_database_manager
        from sqlalchemy import text

        ensure_models_seeded()
        paths = MODEL_PATHS.get(model_name)
        if not paths:
            return jsonify({"success": False,
                            "error": f"Unknown model: {model_name}"}), 400

        # Newest signal file in this model's signals dir
        last_signal_file, last_signal_at = _latest_signal_file(
            paths["signals_dir"]
        )

        # Latest execution (BUY/SELL only) for this model from model_trades
        db = get_database_manager()
        last_execution_at = None
        last_order_id = None
        with db.get_session() as s:
            row = s.execute(text("""
                SELECT trade_at, fyers_order_id
                FROM model_trades
                WHERE model_name = :m
                  AND side IN ('BUY','SELL')
                ORDER BY trade_at DESC
                LIMIT 1
            """), {"m": model_name}).fetchone()
            if row:
                last_execution_at = (
                    row[0].isoformat() if row[0] else None
                )
                last_order_id = row[1]

            # Latest BUY trade reason — distinguishes model-pick vs manual
            # (e.g. LINK_FYERS_POSITION when a broker holding was synced to
            # the ledger, ISOLATION_RESET, manual SEED via UI).
            entry_reason = None
            entry_trade_at = None
            buy_row = s.execute(text("""
                SELECT trade_at, reason
                FROM model_trades
                WHERE model_name = :m AND side = 'BUY'
                ORDER BY trade_at DESC
                LIMIT 1
            """), {"m": model_name}).fetchone()
            if buy_row:
                entry_trade_at = buy_row[0].isoformat() if buy_row[0] else None
                entry_reason = buy_row[1]

        # Portfolio stats — pre-resolve live MTM outside any open session so
        # get_portfolio_stats's internal session doesn't conflict with the
        # one we used for the trade queries above.
        stats = get_portfolio_stats(price_lookup=_live_mtm_lookup_for_model(model_name))

        per_model = next(
            (m for m in stats["models"] if m["model_name"] == model_name), {}
        )

        current_position = None
        if per_model.get("open_symbol"):
            current_position = {
                "sym": per_model["open_symbol"],
                "qty": per_model["open_qty"],
                "entry_px": per_model["open_entry_px"],
                "entry_date": per_model.get("open_entry_date"),
                "entry_reason": entry_reason,
                "entry_trade_at": entry_trade_at,
                "mtm_price": per_model.get("open_mtm_price"),
                "position_value": per_model.get("position_value"),
            }

        return jsonify({
            "success": True,
            "model_name": model_name,
            "label": paths.get("label", model_name),
            "enabled": bool(per_model.get("enabled")),
            "last_signal_at": last_signal_at,
            "last_signal_file": last_signal_file,
            "last_execution_at": last_execution_at,
            "last_order_id": last_order_id,
            "current_position": current_position,
            "nav": per_model.get("nav", 0),
            "invested": per_model.get("invested_amount", 0),
            "cash": per_model.get("cash", 0),
            "pnl_total": per_model.get("pnl_total", 0),
            "pnl_pct": per_model.get("return_pct", 0),
            "realized_pnl": per_model.get("realized_pnl", 0),
            "total_trades": per_model.get("total_trades", 0),
            "win_rate_pct": per_model.get("win_rate_pct", 0),
        })
    except Exception as e:
        logger.error(f"triggers/status error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/<model_name>/run-signal', methods=['POST'])
def admin_run_signal(model_name):
    """Manually trigger live_signal.py for a model. Writes signal file to
    /tmp/manual_<model>_<ts>.json so it never overwrites scheduler output.
    Runs in background thread; returns task_id for polling.
    """
    paths = MODEL_PATHS.get(model_name)
    if not paths:
        return jsonify({"success": False,
                        "error": f"Unknown model: {model_name}"}), 400

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    signals_out = f"/tmp/manual_{model_name}_{ts}.json"
    task_id = f"signal_{model_name}_{ts}"

    project_root = '/app' if os.path.exists('/app/run_pipeline.py') else os.getcwd()
    cmd = [
        "python3", paths["live_signal"],
        *paths["extra_args"],
        "--signals-out", signals_out,
        "--force",
    ]

    def runner():
        run_command_async(task_id, cmd, f"Manual signal for {model_name}")
        # Stash output path on the task so the UI can pick it up for execute
        if task_id in running_tasks:
            running_tasks[task_id]["signals_out"] = signals_out

    threading.Thread(target=runner).start()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "signals_out": signals_out,
        "message": f"Signal run started for {model_name}",
        "cmd": " ".join(cmd),
    })


@admin_bp.route('/<model_name>/run-execute', methods=['POST'])
def admin_run_execute(model_name):
    """Manually trigger fyers_executor.py against the latest signals file.

    Body (optional): {signals_file: <path>, dry_run: true}
      - If signals_file omitted, uses newest file in the model's signals_dir.
      - dry_run defaults to True for safety; pass false to actually place.
    """
    paths = MODEL_PATHS.get(model_name)
    if not paths:
        return jsonify({"success": False,
                        "error": f"Unknown model: {model_name}"}), 400

    data = request.get_json(silent=True) or {}
    signals_file = data.get("signals_file")
    if not signals_file:
        signals_file, _ = _latest_signal_file(paths["signals_dir"])
    if not signals_file:
        return jsonify({
            "success": False,
            "error": f"No signal file found in {paths['signals_dir']}; "
                     f"run /admin/{model_name}/run-signal first",
        }), 400

    dry_run = bool(data.get("dry_run", True))
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    task_id = f"execute_{model_name}_{ts}"
    user_id = os.environ.get("USER_ID", "1")

    cmd = [
        "python3", "tools/live/fyers_executor.py",
        "--signals", signals_file,
        "--user-id", user_id,
        "--model-name", model_name,
    ]
    if dry_run:
        cmd.append("--dry-run")

    threading.Thread(
        target=run_command_async,
        args=(task_id, cmd,
              f"Manual {'DRY-RUN' if dry_run else 'LIVE'} execute for {model_name}"),
    ).start()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "signals_file": signals_file,
        "dry_run": dry_run,
        "message": f"Execute started for {model_name} (dry_run={dry_run})",
        "cmd": " ".join(cmd),
    })


@admin_bp.route('/<model_name>/toggle-enabled', methods=['POST'])
def admin_toggle_enabled(model_name):
    """Flip model_settings.enabled. Body optional: {enabled: bool}; if omitted
    we toggle the current value. Returns the new settings row.
    """
    try:
        from src.services.trading.model_ledger_service import (
            get_all_settings, set_enabled, ensure_models_seeded,
        )
        ensure_models_seeded()
        data = request.get_json(silent=True) or {}
        if "enabled" in data:
            new_val = bool(data["enabled"])
        else:
            current = next(
                (s for s in get_all_settings() if s["model_name"] == model_name),
                None,
            )
            if not current:
                return jsonify({"success": False,
                                "error": f"Unknown model: {model_name}"}), 400
            new_val = not bool(current.get("enabled"))
        return jsonify({
            "success": True,
            "settings": set_enabled(model_name, new_val),
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"toggle-enabled error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/data/backfill', methods=['POST'])
def admin_backfill_history():
    """Trigger 4-year (1500d) historical OHLCV backfill for N50+N500.

    Wraps tools/shared/prefetch_ohlcv.py. Idempotent (skip-frac=0.85).
    Same job that data_scheduler runs every Sunday at 03:00.

    Body (optional): {days: int = 1500, universe: str = "n50,n500"}
    """
    data = request.get_json(silent=True) or {}
    days = int(data.get("days", 1500))
    universe = data.get("universe", "all")

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    task_id = f"backfill_{ts}"

    cmd = [
        "python3", "tools/shared/prefetch_ohlcv.py",
        "--universe", universe,
        "--days", str(days),
        "--intervals", "D",
        "--sleep", "0.15",
        "--retry-passes", "2",
    ]

    threading.Thread(
        target=run_command_async,
        args=(task_id, cmd,
              f"Backfill {days}d OHLCV for {universe}"),
        daemon=True,
    ).start()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "days": days,
        "universe": universe,
        "message": (f"Backfill started for {universe} ({days}d). "
                    f"~30-60 min depending on cache state. "
                    f"Already-covered stocks are skipped."),
        "cmd": " ".join(cmd),
    })


@admin_bp.route('/data/coverage', methods=['GET'])
def admin_data_coverage():
    """Return per-stock historical_data coverage buckets.

    Used by UI to show data health: how many stocks have 4y, 3y, 1y, etc.
    """
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text("""
                SELECT bucket, COUNT(*) AS n FROM (
                    SELECT CASE
                        WHEN cnt >= 990 THEN '4y_full'
                        WHEN cnt >= 750 THEN '3y'
                        WHEN cnt >= 500 THEN '2y'
                        WHEN cnt >= 250 THEN '1y'
                        ELSE 'short'
                    END AS bucket
                    FROM (
                        SELECT symbol, COUNT(*) AS cnt
                        FROM historical_data
                        WHERE symbol LIKE 'NSE:%%-EQ'
                        GROUP BY symbol
                    ) t
                ) tt GROUP BY bucket
            """)).fetchall()
            buckets = {r[0]: r[1] for r in rows}
            stats = s.execute(text("""
                SELECT MIN(date), MAX(date),
                       COUNT(DISTINCT symbol) AS syms,
                       COUNT(*) AS total_rows
                FROM historical_data
                WHERE symbol LIKE 'NSE:%%-EQ'
            """)).fetchone()
        return jsonify({
            "success": True,
            "buckets": buckets,
            "earliest_date": str(stats[0]) if stats[0] else None,
            "latest_date": str(stats[1]) if stats[1] else None,
            "total_symbols": stats[2] if stats[2] else 0,
            "total_rows": stats[3] if stats[3] else 0,
        })
    except Exception as e:
        logger.error(f"data coverage error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# Per-model serialization lock — prevents concurrent rebalance clicks
# from each placing a fresh BUY before the prior one's record_buy reaches
# the ledger. Keyed by model_name. Threading.Lock is process-local; for
# multi-worker Gunicorn we ALSO reject 409 if a prior task is still in
# 'running' status in the DB (cross-worker safety).
_rebalance_locks: Dict[str, threading.Lock] = {}
_rebalance_locks_guard = threading.Lock()

def _get_rebalance_lock(model_name: str) -> threading.Lock:
    with _rebalance_locks_guard:
        lk = _rebalance_locks.get(model_name)
        if lk is None:
            lk = threading.Lock()
            _rebalance_locks[model_name] = lk
        return lk


@admin_bp.route('/<model_name>/rebalance', methods=['POST'])
def admin_model_rebalance(model_name):
    """Live per-model rebalance: signal then LIVE execute (real Fyers orders).

    Chains live_signal.py and fyers_executor.py (without --dry-run) for one model.
    If current position is in fresh top-N: no action. Otherwise: SELL old, BUY rank-1.
    Capital sized from this model's ledger cash only.

    Concurrency: rejects with HTTP 409 if a previous rebalance for the
    same model is still running (in this worker via threading.Lock OR in
    any worker via the model_tasks DB table). Prevents the "3 clicks =
    3 separate BUYs" bug we hit on n20 today.

    Body (optional): {dry_run: bool} — defaults False (LIVE).
    """
    paths = MODEL_PATHS.get(model_name)
    if not paths:
        return jsonify({"success": False,
                        "error": f"Unknown model: {model_name}"}), 400

    # Cross-worker check: any prior task still running for this model?
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text as _text
        _db = get_database_manager()
        with _db.get_session() as _s:
            row = _s.execute(_text("""
                SELECT task_id FROM admin_task_tracking
                WHERE task_id LIKE :prefix AND status IN ('pending','running')
                ORDER BY start_time DESC LIMIT 1
            """), {"prefix": f"rebal_%_{model_name}_%"}).fetchone()
        if row:
            return jsonify({
                "success": False,
                "error": (f"Rebalance already in progress for {model_name} "
                          f"(task {row[0]}). Wait for it to finish."),
            }), 409
    except Exception as e:
        logger.warning(f"rebalance concurrency check failed for {model_name}: {e}")

    # In-process lock (fast path for same-worker repeat clicks)
    lk = _get_rebalance_lock(model_name)
    if not lk.acquire(blocking=False):
        return jsonify({
            "success": False,
            "error": f"Rebalance already in progress for {model_name} (in-process).",
        }), 409
    # Release after the runner thread completes — handled in inner closure.

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", False))

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    signals_out = f"/tmp/rebalance_{model_name}_{ts}.json"
    signal_task = f"rebal_sig_{model_name}_{ts}"
    exec_task = f"rebal_exec_{model_name}_{ts}"
    user_id = os.environ.get("USER_ID", "1")

    signal_cmd = [
        "python3", paths["live_signal"],
        *paths["extra_args"],
        "--signals-out", signals_out,
        "--force",
    ]
    exec_cmd = [
        "python3", "tools/live/fyers_executor.py",
        "--signals", signals_out,
        "--user-id", user_id,
        "--model-name", model_name,
    ]
    if dry_run:
        exec_cmd.append("--dry-run")

    # Pre-register both tasks so the UI's polling never hits 'task not found'.
    # The runner thread will flip status as it progresses.
    for tid, desc in [
        (signal_task, f"Rebalance signal for {model_name}"),
        (exec_task, f"Rebalance {'DRY-RUN' if dry_run else 'LIVE'} execute for {model_name}"),
    ]:
        pre = {
            'type': 'command',
            'status': 'pending',
            'description': desc,
            'start_time': datetime.now().isoformat(),
            'output': '',
            'error': '',
            'steps': [],
        }
        running_tasks[tid] = pre
        try:
            save_task_to_db(tid, pre)
        except Exception as e:
            logger.warning(f"save_task_to_db pre-register {tid} failed: {e}")

    _tg_safe(
        f"🔄 *Rebalance triggered* `{model_name}` "
        f"({'DRY' if dry_run else 'LIVE'})\n"
        f"Signal → executor chain started."
    )

    def runner():
        try:
            run_command_async(signal_task, signal_cmd,
                              f"Rebalance signal for {model_name}")
            # Only execute if signal file actually exists AND signal completed OK
            sig_state = running_tasks.get(signal_task, {})
            if os.path.exists(signals_out) and sig_state.get('status') == 'completed':
                run_command_async(exec_task, exec_cmd,
                                  f"Rebalance {'DRY-RUN' if dry_run else 'LIVE'} "
                                  f"execute for {model_name}")
            else:
                # Mark execute as skipped so the UI doesn't poll forever.
                running_tasks[exec_task].update({
                    'status': 'failed',
                    'error': 'Skipped: signal step did not complete successfully '
                             f"(status={sig_state.get('status')!r})",
                    'end_time': datetime.now().isoformat(),
                })
                try:
                    save_task_to_db(exec_task, running_tasks[exec_task])
                except Exception:
                    pass
                _tg_safe(
                    f"❌ *Rebalance signal FAILED* `{model_name}`\n"
                    f"Status: `{sig_state.get('status')!r}`\n"
                    f"Executor skipped — no orders placed."
                )
        finally:
            try:
                lk.release()
            except Exception:
                pass

    threading.Thread(target=runner, daemon=True).start()

    return jsonify({
        "success": True,
        "signal_task_id": signal_task,
        "execute_task_id": exec_task,
        "signals_out": signals_out,
        "dry_run": dry_run,
        "message": (f"Rebalance started for {model_name} "
                    f"(dry_run={dry_run})"),
    })


@admin_bp.route('/<model_name>/ranking', methods=['GET'])
def admin_model_ranking(model_name):
    """Read the per-model ranking JSON written by live_signal.py.

    Query:
      ?top=N       (default 5; capped to the file's top_n)
      ?recalc=1    force a fresh live_signal.py run before reading

    Lifecycle:
      1. If today's ranking file exists and recalc != 1, return cached
         (still overlays live Fyers LTP on each row).
      2. Otherwise run live_signal.py synchronously, then read the file
         it wrote. Subsequent same-day requests hit the cache.

    Scheduler still runs live_signal nightly/morning; this on-demand
    rerun fills the gap when a user opens Today's Picks before the cron
    has fired.
    """
    paths = MODEL_PATHS.get(model_name)
    if not paths:
        return jsonify({"success": False,
                        "error": f"Unknown model: {model_name}"}), 400

    try:
        top = int(request.args.get("top", 5))
        recalc = request.args.get("recalc", "").lower() in ("1", "true", "yes")
        ranking_dir = Path(paths["ranking_dir"])
        today_file = ranking_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"

        # Auto-run live_signal if today's file is missing, empty, or has
        # no picks (top_n=[]). Earlier 32-byte size check missed the case
        # where the file existed with universe metadata but empty top_n —
        # which is exactly what midcap wrote on a no-breakout day, so the
        # card sat empty until the user clicked Re-calculate.
        need_run = recalc or (not today_file.exists())
        if not need_run and today_file.exists():
            try:
                import json as _jsoncheck
                _p = _jsoncheck.loads(today_file.read_text())
                if not (_p.get("top_n") or []):
                    need_run = True
            except Exception:
                need_run = True
        # Skip auto-run for the finnifty options model (no live_signal flow).
        ran_now = False
        if need_run and paths.get("live_signal"):
            ts = datetime.now().strftime("%Y%m%dT%H%M%S")
            # Write to the canonical signals dir so the NEXT scheduled
            # executor run (09:30 IST or manual rebalance) actually sees
            # the fresh signal. Previously this wrote to /tmp and the
            # cron executor missed it — model picked rank-1 but never
            # placed an order.
            sig_dir = Path(paths.get("signals_dir") or f"/tmp")
            sig_dir.mkdir(parents=True, exist_ok=True)
            today_iso = datetime.now().strftime("%Y-%m-%d")
            # Match each model's cron file-naming convention by checking
            # what cron.py writes; fall back to a model-suffixed default.
            existing = sorted(sig_dir.glob(f"{today_iso}*.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
            if existing:
                signals_out = str(existing[0])
            else:
                signals_out = str(sig_dir / f"{today_iso}_{model_name}.json")
            cmd = [
                "python3", paths["live_signal"],
                *paths["extra_args"],
                "--signals-out", signals_out,
            ]
            if recalc:
                cmd.append("--force")
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=180)
                if r.returncode == 0:
                    ran_now = True
                else:
                    logger.warning(
                        f"auto live_signal for {model_name} failed "
                        f"({r.returncode}): {r.stderr[-300:]}"
                    )
            except subprocess.TimeoutExpired:
                logger.warning(f"auto live_signal for {model_name} timed out")
            except Exception as e:
                logger.warning(f"auto live_signal for {model_name} crashed: {e}")

        import json as _json
        # OBSERVER models emit their target-holdings into signals_dir as
        # {date}_{model}.json (targets[]). Prefer that — it's the real output;
        # ranking_dir/top_n is legacy (executor models). Map targets -> the
        # ranking shape the Today's Picks page expects. Price comes from the
        # signal (eToro EOD) — no Fyers LTP overlay in the US observer build.
        sig_dir = Path(paths.get("signals_dir") or "")
        sig_files = (sorted(sig_dir.glob(f"*{model_name}.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
                     if sig_dir.exists() else [])
        if sig_files:
            payload = _json.loads(sig_files[0].read_text() or "{}")
            targets = payload.get("targets") or []
            ranking = [{
                "rank": t.get("rank", i + 1),
                "symbol": t.get("symbol"),
                # picks page reads `name`; observer signals carry no real company
                # name (company == ticker), so leave name blank when it'd just
                # duplicate the symbol — avoids a broken/"MU MU" display.
                "name": (t.get("company") if t.get("company") and t.get("company") != t.get("symbol") else ""),
                "company": t.get("company") or t.get("symbol"),
                "weight": t.get("weight"),
                "price": t.get("price"),
            } for i, t in enumerate(targets)][:top]
            note = payload.get("note")
            if not ranking:
                note = ("Regime OFF — model in cash, no holdings today."
                        if payload.get("regime_on") is False
                        else (note or "No targets in latest signal."))
            return jsonify({
                "success": True, "model": model_name,
                "label": paths.get("label", model_name),
                "date": payload.get("asof") or payload.get("date"),
                "universe_size": payload.get("universe_size"),
                "ranking": ranking,
                "note": note,
                "regime_on": payload.get("regime_on"),
                "source": str(sig_files[0]),
                "generated_at": datetime.fromtimestamp(
                    sig_files[0].stat().st_mtime).isoformat(),
                "ran_now": ran_now,
            })

        d = ranking_dir
        if not d.exists():
            return jsonify({
                "success": True,
                "model": model_name,
                "label": paths.get("label", model_name),
                "ranking": [],
                "ran_now": ran_now,
                "note": f"No ranking dir yet ({paths['ranking_dir']}) — "
                        "scheduler will create it on next live_signal run, "
                        "or hit /admin/<m>/run-signal.",
            })

        files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime,
                       reverse=True)
        if not files:
            return jsonify({
                "success": True, "model": model_name,
                "label": paths.get("label", model_name),
                "ranking": [],
                "ran_now": ran_now,
                "note": "No ranking files yet for this model.",
            })

        import json as _json
        payload = _json.loads(files[0].read_text())
        ranking = payload.get("top_n") or []
        ranking = ranking[:top]

        # Enrich each row with live Fyers LTP so the picks page shows today's
        # price instead of whatever EOD close live_signal.py wrote yesterday.
        if ranking:
            live = _resolve_live_prices([r.get("symbol") for r in ranking])
            for r in ranking:
                bare = (r.get("symbol") or "").replace("NSE:", "").replace("-EQ", "")
                v = live.get(bare)
                if v and v > 0:
                    r["price"] = round(float(v), 2)
                    r["live"] = True

        return jsonify({
            "success": True,
            "model": model_name,
            "label": paths.get("label", model_name),
            "date": payload.get("date"),
            "universe_size": payload.get("universe_size"),
            "ranking": ranking,
            "note": payload.get("note"),
            "qualifying_breakouts": payload.get("qualifying_breakouts"),
            "source": str(files[0]),
            "generated_at": datetime.fromtimestamp(
                files[0].stat().st_mtime).isoformat(),
            "ran_now": ran_now,
        })
    except Exception as e:
        logger.error(f"model ranking error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# Audit endpoints — read-only forensics over the 7 audit tables
# =============================================================================

@admin_bp.route('/audit/orders', methods=['GET'])
def audit_orders_list():
    """List recent Fyers orders. Query: ?model=&symbol=&limit=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        model = request.args.get("model")
        symbol = request.args.get("symbol")
        limit = min(int(request.args.get("limit", 200)), 1000)
        days = int(request.args.get("days", 30))
        days = max(1, min(int(days), 3650))   # 1..10y safety clamp
        q = f"""
            SELECT id, model_name, placed_at, fyers_order_id, symbol, side,
                   qty, ordered_price, fill_price, fill_qty, status,
                   slippage_inr, error_text
            FROM audit_orders
            WHERE placed_at >= NOW() - INTERVAL '{days} days'
        """
        params = {}
        if model:
            q += " AND model_name = :m"
            params["m"] = model
        if symbol:
            q += " AND symbol ILIKE :s"
            params["s"] = f"%{symbol}%"
        q += " ORDER BY placed_at DESC LIMIT :limit"
        params["limit"] = limit
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "model_name": r.model_name,
                "placed_at": r.placed_at.isoformat() if r.placed_at else None,
                "fyers_order_id": r.fyers_order_id,
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "ordered_price": float(r.ordered_price) if r.ordered_price else None,
                "fill_price": float(r.fill_price) if r.fill_price else None,
                "fill_qty": r.fill_qty,
                "status": r.status,
                "slippage_inr": float(r.slippage_inr) if r.slippage_inr else None,
                "error_text": r.error_text,
            })
        return jsonify({"success": True, "orders": out})
    except Exception as e:
        logger.error(f"audit_orders_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/rankings', methods=['GET'])
def audit_rankings_list():
    """Daily rankings per model. Query: ?model=&date=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        model = request.args.get("model")
        d = request.args.get("date")
        days = int(request.args.get("days", 7))
        q = "SELECT model_name, ranked_at, trading_date, universe_size, qualifying_count, rank, symbol, name, score, price, extra FROM audit_model_rankings WHERE 1=1"
        params = {}
        if model:
            q += " AND model_name = :m"
            params["m"] = model
        if d:
            q += " AND trading_date = :d"
            params["d"] = d
        else:
            q += f" AND trading_date >= CURRENT_DATE - INTERVAL '{days} days'"
        q += " ORDER BY trading_date DESC, model_name, rank LIMIT 500"
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = [{
            "model_name": r.model_name,
            "ranked_at": r.ranked_at.isoformat() if r.ranked_at else None,
            "trading_date": r.trading_date.isoformat() if r.trading_date else None,
            "universe_size": r.universe_size,
            "qualifying_count": r.qualifying_count,
            "rank": r.rank, "symbol": r.symbol, "name": r.name,
            "score": float(r.score) if r.score else None,
            "price": float(r.price) if r.price else None,
            "extra": r.extra,
        } for r in rows]
        return jsonify({"success": True, "rankings": out})
    except Exception as e:
        logger.error(f"audit_rankings_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/signals', methods=['GET'])
def audit_signals_list():
    """Emitted signals. Query: ?model=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        model = request.args.get("model")
        days = int(request.args.get("days", 30))
        q = "SELECT model_name, emitted_at, trading_date, signal_type, symbol, side, price, qty_planned, reason FROM audit_model_signals WHERE emitted_at >= NOW() - INTERVAL '%d days'" % days
        params = {}
        if model:
            q += " AND model_name = :m"
            params["m"] = model
        q += " ORDER BY emitted_at DESC LIMIT 500"
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = [{
            "model_name": r.model_name,
            "emitted_at": r.emitted_at.isoformat() if r.emitted_at else None,
            "trading_date": r.trading_date.isoformat() if r.trading_date else None,
            "signal_type": r.signal_type, "symbol": r.symbol, "side": r.side,
            "price": float(r.price) if r.price else None,
            "qty_planned": r.qty_planned, "reason": r.reason,
        } for r in rows]
        return jsonify({"success": True, "signals": out})
    except Exception as e:
        logger.error(f"audit_signals_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/decisions', methods=['GET'])
def audit_decisions_list():
    """Rebalance reasoning. Query: ?model=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        model = request.args.get("model")
        days = int(request.args.get("days", 30))
        q = "SELECT * FROM audit_rebalance_decisions WHERE decided_at >= NOW() - INTERVAL '%d days'" % days
        params = {}
        if model:
            q += " AND model_name = :m"
            params["m"] = model
        q += " ORDER BY decided_at DESC LIMIT 500"
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "model_name": r.model_name,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "trigger": r.trigger,
                "held_symbol": r.held_symbol, "held_qty": r.held_qty,
                "held_entry_px": float(r.held_entry_px) if r.held_entry_px else None,
                "held_mtm_px": float(r.held_mtm_px) if r.held_mtm_px else None,
                "rank1_symbol": r.rank1_symbol,
                "rank1_price": float(r.rank1_price) if r.rank1_price else None,
                "decision": r.decision, "reason": r.reason,
                "qty_sized": r.qty_sized, "qty_clamped": r.qty_clamped,
                "clamp_reason": r.clamp_reason,
            })
        return jsonify({"success": True, "decisions": out})
    except Exception as e:
        logger.error(f"audit_decisions_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/config-changes', methods=['GET'])
def audit_config_changes_list():
    """Settings/ledger field history. Query: ?model=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        model = request.args.get("model")
        days = int(request.args.get("days", 30))
        q = "SELECT * FROM audit_config_changes WHERE changed_at >= NOW() - INTERVAL '%d days'" % days
        params = {}
        if model:
            q += " AND model_name = :m"
            params["m"] = model
        q += " ORDER BY changed_at DESC LIMIT 500"
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = [{
            "id": r.id,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            "changed_by": r.changed_by,
            "model_name": r.model_name,
            "field": r.field,
            "old_value": r.old_value, "new_value": r.new_value,
            "reason": r.reason,
        } for r in rows]
        return jsonify({"success": True, "changes": out})
    except Exception as e:
        logger.error(f"audit_config_changes_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/data-quality', methods=['GET'])
def audit_data_quality_list():
    """Daily data-coverage snapshots. Query: ?model=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        model = request.args.get("model")
        days = int(request.args.get("days", 90))
        q = "SELECT * FROM audit_data_quality WHERE snapshot_at >= NOW() - INTERVAL '%d days'" % days
        params = {}
        if model:
            q += " AND model_name = :m"
            params["m"] = model
        q += " ORDER BY snapshot_at DESC LIMIT 500"
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = [{
            "id": r.id,
            "snapshot_at": r.snapshot_at.isoformat() if r.snapshot_at else None,
            "model_name": r.model_name,
            "universe_size": r.universe_size,
            "universe_age_days": r.universe_age_days,
            "coverage_pct": float(r.coverage_pct) if r.coverage_pct else None,
            "stale_days": r.stale_days,
            "data_sufficient": r.data_sufficient, "wired": r.wired,
        } for r in rows]
        return jsonify({"success": True, "snapshots": out})
    except Exception as e:
        logger.error(f"audit_data_quality_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/system-events', methods=['GET'])
def audit_system_events_list():
    """Boot/cron/token-refresh events. Query: ?event_type=&days="""
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        evtype = request.args.get("event_type")
        days = int(request.args.get("days", 7))
        q = "SELECT id, event_at, event_type, component, metadata FROM audit_system_events WHERE event_at >= NOW() - INTERVAL '%d days'" % days
        params = {}
        if evtype:
            q += " AND event_type = :t"
            params["t"] = evtype
        q += " ORDER BY event_at DESC LIMIT 500"
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(q), params).fetchall()
        out = [{
            "id": r.id,
            "event_at": r.event_at.isoformat() if r.event_at else None,
            "event_type": r.event_type, "component": r.component,
            "metadata": r.metadata,
        } for r in rows]
        return jsonify({"success": True, "events": out})
    except Exception as e:
        logger.error(f"audit_system_events_list error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit/charges-summary', methods=['GET'])
def audit_charges_summary():
    """Per-model broker-charge totals (BUY vs SELL) across all audit_orders.

    Returns rows: {model_name, buy_charges, sell_charges, buy_count, sell_count,
                   total_charges, lifetime_pnl, charges_pct_of_turnover}
    """
    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text
        days = int(request.args.get("days", 365))
        days = max(1, min(days, 3650))
        db = get_database_manager()
        with db.get_session() as s:
            rows = s.execute(text(f"""
                SELECT
                    COALESCE(model_name, '(unattributed)') AS model_name,
                    side,
                    COUNT(*) AS n_trades,
                    COALESCE(SUM(charges_inr), 0) AS total_charges,
                    COALESCE(SUM(COALESCE(fill_qty, qty) * COALESCE(fill_price, ordered_price)), 0) AS total_turnover
                FROM audit_orders
                WHERE placed_at >= NOW() - INTERVAL '{days} days'
                  AND status IN ('placed','filled','partial')
                GROUP BY model_name, side
                ORDER BY model_name, side
            """)).fetchall()

        per_model: Dict[str, Dict] = {}
        for r in rows:
            m = r.model_name or "(unattributed)"
            blk = per_model.setdefault(m, {
                "model_name": m,
                "buy_charges": 0.0, "sell_charges": 0.0,
                "buy_count": 0, "sell_count": 0,
                "buy_turnover": 0.0, "sell_turnover": 0.0,
                "total_charges": 0.0, "total_turnover": 0.0,
            })
            if r.side == "BUY":
                blk["buy_charges"] = float(r.total_charges or 0)
                blk["buy_count"] = int(r.n_trades or 0)
                blk["buy_turnover"] = float(r.total_turnover or 0)
            elif r.side == "SELL":
                blk["sell_charges"] = float(r.total_charges or 0)
                blk["sell_count"] = int(r.n_trades or 0)
                blk["sell_turnover"] = float(r.total_turnover or 0)

        out = []
        for m, blk in per_model.items():
            blk["total_charges"] = blk["buy_charges"] + blk["sell_charges"]
            blk["total_turnover"] = blk["buy_turnover"] + blk["sell_turnover"]
            blk["charges_pct_of_turnover"] = (
                round(blk["total_charges"] / blk["total_turnover"] * 100, 4)
                if blk["total_turnover"] > 0 else 0.0
            )
            out.append(blk)
        out.sort(key=lambda x: -x["total_charges"])
        # Grand total row
        gt = {"model_name": "__TOTAL__",
              "buy_charges": sum(x["buy_charges"] for x in out),
              "sell_charges": sum(x["sell_charges"] for x in out),
              "buy_count": sum(x["buy_count"] for x in out),
              "sell_count": sum(x["sell_count"] for x in out),
              "buy_turnover": sum(x["buy_turnover"] for x in out),
              "sell_turnover": sum(x["sell_turnover"] for x in out)}
        gt["total_charges"] = gt["buy_charges"] + gt["sell_charges"]
        gt["total_turnover"] = gt["buy_turnover"] + gt["sell_turnover"]
        gt["charges_pct_of_turnover"] = (
            round(gt["total_charges"] / gt["total_turnover"] * 100, 4)
            if gt["total_turnover"] > 0 else 0.0
        )
        return jsonify({"success": True, "by_model": out, "total": gt, "days": days})
    except Exception as e:
        logger.error(f"audit_charges_summary error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/audit', methods=['GET'])
def audit_dashboard():
    """Unified read-only audit dashboard."""
    return render_template('admin/audit_dashboard.html')
