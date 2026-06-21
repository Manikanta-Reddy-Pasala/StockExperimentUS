#!/usr/bin/env python3
"""
Data Pipeline Scheduler
Runs data updates, CSV pulls, stock history fetches, and calculations at scheduled times.
"""

import sys
import logging
import schedule
import time
from pathlib import Path
from datetime import datetime, timedelta
import subprocess

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging with rotation (max 50MB per file, keep 5 backups)
import os
from logging.handlers import RotatingFileHandler

_log_handlers = [logging.StreamHandler()]
try:
    os.makedirs('logs', exist_ok=True)
    _log_handlers.append(
        RotatingFileHandler('logs/data_scheduler.log', maxBytes=50*1024*1024, backupCount=5)
    )
except (PermissionError, OSError) as _log_err:
    print(f"WARNING: Cannot write to logs/data_scheduler.log ({_log_err}). Logging to stdout only.")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=_log_handlers
)
logger = logging.getLogger(__name__)


def _tg_alert(text: str):
    """Best-effort Telegram alert. Never raises."""
    try:
        from tools.live.telegram_notify import send
        send(text, parse_mode="Markdown")
    except Exception as e:
        logger.debug(f"tg alert skipped: {e}")


def _run_subprocess_with_retry(cmd: list, label: str, timeout: int = 3600,
                                max_retries: int = 2, alert_on_fail: bool = True):
    """Run a subprocess with retry logic. TG alert on final failure."""
    last_err = ""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Running {label} (attempt {attempt}/{max_retries})...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode == 0:
                logger.info(f"  {label} completed successfully")
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 20:
                        logger.info(f"  Output (last 20 lines):\n{''.join(lines[-20:])}")
                    else:
                        logger.info(f"  Output:\n{result.stdout}")
                return True
            else:
                last_err = (result.stderr or "")[-500:]
                logger.error(f"  {label} failed (return code {result.returncode})")
                if last_err:
                    logger.error(f"  Error:\n{last_err}")
                if attempt < max_retries:
                    import time as _time
                    wait = 30 * attempt
                    logger.info(f"  Retrying in {wait}s...")
                    _time.sleep(wait)

        except subprocess.TimeoutExpired:
            last_err = f"timeout after {timeout}s"
            logger.error(f"  {label} {last_err}")
        except Exception as e:
            last_err = str(e)
            logger.error(f"  {label} error: {e}", exc_info=True)

    logger.error(f"  {label} failed after {max_retries} attempts")
    if alert_on_fail:
        _tg_alert(
            f"🛑 *Data pipeline failure*\n"
            f"Job: `{label}`\n"
            f"After {max_retries} attempts\n"
            f"Last error: ```{last_err[:300]}```"
        )
    return False


def refresh_fyers_token_job():
    """No-op: IBKR auth is managed by TWS/Gateway (no TOTP token refresh)."""
    logger.debug("IBKR uses TWS/Gateway auth; token refresh job skipped")
    return


def daily_universe_csv_check():
    """Daily 06:00 IST check: any universe CSV >7d stale → refresh now.

    Saturday-only refresh schedule means a Saturday miss = 7d gap. This
    daily check catches that. Idempotent — refresh_universe_csvs() exits
    fast when nothing to do.
    """
    import datetime as _dt
    cache_dir = "/app/src/data/symbols"
    stale = _dt.timedelta(days=7)
    now = _dt.datetime.now()
    files = ["nifty100.csv", "nifty500.csv",
             "nifty_midcap150.csv", "nifty_smallcap250.csv"]
    needs_refresh = False
    stale_list = []
    for fname in files:
        fp = os.path.join(cache_dir, fname)
        if not os.path.exists(fp):
            logger.warning(f"daily_universe_csv_check: {fname} MISSING")
            stale_list.append(f"{fname}=MISSING")
            needs_refresh = True
            continue
        age = now - _dt.datetime.fromtimestamp(os.path.getmtime(fp))
        if age > stale:
            logger.warning(f"daily_universe_csv_check: {fname} is {age.days}d old (>7d)")
            stale_list.append(f"{fname}={age.days}d")
            needs_refresh = True
    if needs_refresh:
        _tg_alert(
            f"⚠️ *Universe CSVs stale, refreshing*\n"
            + "\n".join(f"- {s}" for s in stale_list)
        )
        refresh_universe_csvs()
    else:
        logger.info("daily_universe_csv_check: all universe CSVs fresh (<7d)")


def pre_market_data_quality_gate():
    """Pre-market 09:00 IST data quality gate.

    Block rebalancing if today's data ingest is incomplete. Looks at
    historical_data coverage for yesterday (most recent close). If less
    than MIN_SYMBOLS have a row for that date, write a marker file that
    fyers_executor reads on startup to abort with an alert.

    MIN_SYMBOLS=400 chosen because active models (n50+n500 union) is ~504;
    a 20% gap is too risky to trade on.
    """
    MIN_SYMBOLS = 400
    try:
        from sqlalchemy import text
        from tools.shared.ohlcv_cache import _get_engine
        import datetime as _dt
        eng = _get_engine()
        if eng is None:
            logger.error("data_quality_gate: no DB engine")
            return
        # Most-recent trading day = max(date) in historical_data
        with eng.connect() as c:
            r = c.execute(text(
                "SELECT MAX(date) AS d FROM historical_data"
            )).first()
            latest = r.d if r else None
            if latest is None:
                logger.error("data_quality_gate: historical_data is EMPTY")
                _write_gate_marker(False, "historical_data is empty")
                return
            r = c.execute(text(
                "SELECT COUNT(DISTINCT symbol) AS n FROM historical_data WHERE date = :d"
            ), {"d": latest}).first()
            n_syms = int(r.n) if r else 0
        ok = n_syms >= MIN_SYMBOLS
        msg = f"latest={latest} syms={n_syms} (need>={MIN_SYMBOLS})"
        if ok:
            logger.info(f"data_quality_gate: PASS {msg}")
        else:
            logger.error(f"data_quality_gate: FAIL {msg}")
            _tg_alert(
                f"🛑 *Data quality gate FAIL*\n"
                f"{msg}\n"
                f"Trading will be BLOCKED until coverage recovers.\n"
                f"Investigate: data_scheduler logs + Fyers token validity."
            )
        _write_gate_marker(ok, msg)
    except Exception as e:
        logger.error(f"data_quality_gate failed: {e}", exc_info=True)
        _tg_alert(f"🛑 *Data quality gate ERROR*\n```{str(e)[:300]}```")


def _write_gate_marker(ok: bool, msg: str):
    """Write marker file consumed by fyers_executor pre-flight check."""
    try:
        import json as _json
        import datetime as _dt
        os.makedirs("/app/logs", exist_ok=True)
        with open("/app/logs/data_quality_gate.json", "w") as f:
            _json.dump({
                "ok": ok, "msg": msg,
                "ts": _dt.datetime.now().isoformat(),
            }, f)
    except Exception as e:
        logger.warning(f"gate marker write failed: {e}")


def run_data_pipeline():
    """Run complete data pipeline (Daily at 9:00 PM after market close)."""
    logger.info("=" * 80)
    logger.info("Starting Data Pipeline (4-Step Saga)")
    logger.info("=" * 80)
    _run_subprocess_with_retry(['python3', 'run_pipeline.py'], 'Data Pipeline', timeout=3600, max_retries=2)


def pull_us_etoro_daily():
    """Daily incremental eToro OHLCV pull for the US universe.

    This is the REAL US data-freshness job. The legacy saga (run_data_pipeline)
    keys off the `stocks` table which is empty in the US deployment, so it pulls
    nothing — historical_data only stays fresh via this direct eToro pull over
    the combined US universe CSV (843 syms: S&P100/500 + Nasdaq100/500). Pulls a
    rolling 45-day window so the latest closes append without re-fetching 4y.
    """
    from datetime import date, timedelta
    start = (date.today() - timedelta(days=45)).isoformat()
    end = date.today().isoformat()
    logger.info("=" * 80)
    logger.info(f"eToro US daily pull — combined universe, {start} → {end}")
    logger.info("=" * 80)
    _run_subprocess_with_retry(
        ['python3', 'tools/pull_etoro_history.py',
         '--universe', 'src/data/symbols/combined_us_universe.csv',
         '--start', start, '--end', end],
        'etoro_us_daily', timeout=3600, max_retries=2,
    )


def backfill_full_history():
    """Ensure ALL NSE-EQ stocks have 4 years (1500d) of daily OHLCV.

    Uses existing tools/shared/prefetch_ohlcv.py --universe all (every
    NSE:...-EQ symbol from the stocks master table) with --skip-frac=0.85.
    Idempotent — re-running on a complete cache is cheap (per-symbol
    coverage check is a single SELECT COUNT(*)).

    Daily-only by design. No live trading model uses hourly (1h) bars.
    Backfilling 1h for 2400+ symbols would 25x the Fyers API calls for
    zero trading benefit.

    Runs weekly (Sunday 03:00 IST — before any market activity) and
    once on scheduler startup if env BACKFILL_ON_BOOT=true.

    Daily incremental pulls (per-model data_pull at 20:45) keep the
    latest 2 days fresh. This job only fills HISTORICAL gaps.
    """
    logger.info("=" * 80)
    logger.info("Full History Backfill — 4 years (1500d) Daily for ALL NSE-EQ")
    logger.info("=" * 80)
    _run_subprocess_with_retry(
        ['python3', 'tools/shared/prefetch_ohlcv.py',
         '--universe', 'all',
         '--days', '1500',
         '--intervals', 'D',
         '--sleep', '0.15',
         '--retry-passes', '2'],
        'backfill_4y_history',
        timeout=21600,  # 6 hours — ~2400 syms, mostly cached after first run
        max_retries=1,
    )



def export_daily_csv():
    """
    Export daily data to CSV (Daily at 10:00 PM).
    Creates CSV files with latest stock data for backup/analysis.
    """
    logger.info("=" * 80)
    logger.info("Exporting Daily CSV Files")
    logger.info("=" * 80)
    
    try:
        from src.models.database import get_database_manager
        import pandas as pd
        import os
        
        export_dir = Path('exports')
        export_dir.mkdir(exist_ok=True)
        try:
            os.chmod(export_dir, 0o777)
        except (PermissionError, OSError):
            pass
        if not os.access(export_dir, os.W_OK):
            export_dir = Path('/app/logs/exports')
            export_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"exports/ not writable, falling back to {export_dir}")
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            # Export stocks data
            logger.info("Exporting stocks data...")
            stocks_query = """
                SELECT symbol, name, current_price, market_cap, pe_ratio, pb_ratio, roe, 
                       eps, book_value, beta, peg_ratio, roa, debt_to_equity,
                       current_ratio, quick_ratio, revenue_growth, earnings_growth,
                       operating_margin, net_margin, profit_margin, dividend_yield,
                       volume, sector, market_cap_category, last_updated
                FROM stocks
                WHERE current_price IS NOT NULL
                ORDER BY market_cap DESC NULLS LAST
            """
            stocks_df = pd.read_sql(stocks_query, session.connection())
            stocks_file = export_dir / f'stocks_{today}.csv'
            stocks_df.to_csv(stocks_file, index=False)
            logger.info(f"  ✅ Exported {len(stocks_df)} stocks to {stocks_file}")
            
            # Export historical data (last 30 days)
            logger.info("Exporting recent historical data (30 days)...")
            history_query = """
                SELECT symbol, date, open, high, low, close, adj_close, volume,
                       data_source, price_change_pct
                FROM historical_data
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY symbol, date DESC
            """
            history_df = pd.read_sql(history_query, session.connection())
            history_file = export_dir / f'historical_30d_{today}.csv'
            history_df.to_csv(history_file, index=False)
            logger.info(f"  ✅ Exported {len(history_df)} historical records to {history_file}")
            
            # Export technical indicators (latest)
            logger.info("Exporting latest technical indicators...")
            tech_query = """
                SELECT DISTINCT ON (symbol)
                    symbol, date, sma_50, sma_200
                FROM technical_indicators
                ORDER BY symbol, date DESC
            """
            tech_df = pd.read_sql(tech_query, session.connection())
            tech_file = export_dir / f'technical_indicators_{today}.csv'
            tech_df.to_csv(tech_file, index=False)
            logger.info(f"  ✅ Exported {len(tech_df)} technical indicators to {tech_file}")
            
            # Export suggested stocks (today)
            logger.info("Exporting today's suggested stocks...")
            suggested_query = """
                SELECT date, symbol, stock_name, current_price, market_cap,
                       strategy, selection_score, rank,
                       rsi_14, macd, sma_50, sma_200,
                       pe_ratio, pb_ratio, roe, eps, beta,
                       revenue_growth, earnings_growth, operating_margin,
                       target_price, stop_loss, recommendation, reason,
                       sector, market_cap_category
                FROM daily_suggested_stocks
                WHERE date = CURRENT_DATE
                ORDER BY rank
            """
            suggested_df = pd.read_sql(suggested_query, session.connection())
            if len(suggested_df) > 0:
                suggested_file = export_dir / f'suggested_stocks_{today}.csv'
                suggested_df.to_csv(suggested_file, index=False)
                logger.info(f"  ✅ Exported {len(suggested_df)} suggested stocks to {suggested_file}")
            else:
                logger.warning("  ⚠️  No suggested stocks found for today")
        
        logger.info("✅ CSV export completed successfully at 10:00 PM")
        
        # Cleanup old CSV files (keep last 90 days for extended testing)
        logger.info("Cleaning up old CSV files (>90 days)...")
        cleanup_old_csv_files(export_dir, keep_days=90)
        
    except Exception as e:
        logger.error(f"❌ CSV export failed: {e}", exc_info=True)


def cleanup_old_csv_files(export_dir: Path, keep_days: int = 30):
    """Delete CSV files older than keep_days."""
    try:
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        deleted_count = 0
        for csv_file in export_dir.glob('*.csv'):
            # Get file modification time
            mtime = datetime.fromtimestamp(csv_file.stat().st_mtime)
            if mtime < cutoff_date:
                csv_file.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"  ✅ Deleted {deleted_count} old CSV files (>{keep_days} days)")
        else:
            logger.info(f"  ℹ️  No old CSV files to delete")
            
    except Exception as e:
        logger.error(f"  ❌ CSV cleanup failed: {e}")


def refresh_universe_csvs():
    """
    Refresh all 4 Nifty universe CSVs (nifty100, nifty500, midcap150, smallcap250)
    from NSE archives. NSE reconstitutes indices in March + September each year;
    midcap150/smallcap250 also see periodic reshuffles. Run weekly to catch
    additions/removals (e.g., FY25 IPOs entering Nifty 500).

    Files written:
      - src/data/symbols/nifty100.csv
      - src/data/symbols/nifty500.csv
      - src/data/symbols/nifty_midcap150.csv
      - src/data/symbols/nifty_smallcap250.csv
    """
    logger.info("=" * 80)
    logger.info("Refreshing Nifty universe CSVs from NSE")
    logger.info("=" * 80)
    scripts = [
        "tools/refresh_nifty100.py",
        "tools/refresh_nifty500.py",
        "tools/refresh_nifty_midcap150.py",
        "tools/refresh_nifty_smallcap250.py",
    ]
    import subprocess
    for s in scripts:
        try:
            r = subprocess.run(["python3", s], capture_output=True,
                               text=True, timeout=60, cwd="/app")
            if r.returncode == 0:
                logger.info(f"  ✅ {s}: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'ok'}")
            else:
                logger.error(f"  ❌ {s} failed (rc={r.returncode}): {r.stderr.strip()[-200:]}")
        except Exception as e:
            logger.error(f"  ❌ {s} exception: {e}")


def update_symbol_master():
    """
    Update symbol master CSV from NSE (Weekly on Monday at 6:00 AM).
    Refreshes the complete list of tradeable NSE symbols.
    """
    logger.info("=" * 80)
    logger.info("Updating Symbol Master from NSE")
    logger.info("=" * 80)
    
    try:
        from src.services.data.symbol_master_service import SymbolMasterService
        from src.models.database import get_database_manager
        
        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            symbol_service = SymbolMasterService()
            
            # Refresh symbol master
            logger.info("US uses static CSV universes; symbol-master refresh is a no-op")
            result = symbol_service.refresh_all_symbols(sync_to_database=True)

            logger.info(f"Symbol master updated successfully")
            logger.info(f"  Result: {result}")
            
    except Exception as e:
        logger.error(f"❌ Symbol master update failed: {e}", exc_info=True)


def validate_data_quality():
    """
    Validate data quality and generate report (Daily at 10:30 PM).
    Checks for missing data, anomalies, and data consistency.
    """
    logger.info("=" * 80)
    logger.info("Validating Data Quality")
    logger.info("=" * 80)

    try:
        from src.models.database import get_database_manager
        from sqlalchemy import text

        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            # Check stocks table
            stocks_stats = session.execute(text("""
                SELECT
                    COUNT(*) as total_stocks,
                    COUNT(current_price) as with_price,
                    COUNT(market_cap) as with_market_cap,
                    COUNT(pe_ratio) as with_pe,
                    COUNT(eps) as with_eps,
                    COUNT(sector) as with_sector
                FROM stocks
            """)).fetchone()

            total_stocks = stocks_stats.total_stocks if stocks_stats else 0

            logger.info("Stocks Table:")
            logger.info(f"  Total stocks: {total_stocks}")
            if total_stocks > 0:
                logger.info(f"  With price: {stocks_stats.with_price} ({stocks_stats.with_price/total_stocks*100:.1f}%)")
                logger.info(f"  With market cap: {stocks_stats.with_market_cap} ({stocks_stats.with_market_cap/total_stocks*100:.1f}%)")
                logger.info(f"  With PE ratio: {stocks_stats.with_pe} ({stocks_stats.with_pe/total_stocks*100:.1f}%)")
                logger.info(f"  With EPS: {stocks_stats.with_eps} ({stocks_stats.with_eps/total_stocks*100:.1f}%)")
                logger.info(f"  With sector: {stocks_stats.with_sector} ({stocks_stats.with_sector/total_stocks*100:.1f}%)")
            else:
                logger.warning("  ⚠️ No stocks data available")

            # Check historical data
            history_stats = session.execute(text("""
                SELECT
                    COUNT(DISTINCT symbol) as symbols_with_history,
                    COUNT(*) as total_records,
                    MAX(date) as latest_date,
                    MIN(date) as earliest_date
                FROM historical_data
            """)).fetchone()

            logger.info("\nHistorical Data:")
            logger.info(f"  Symbols with history: {history_stats.symbols_with_history}")
            logger.info(f"  Total records: {history_stats.total_records:,}")
            logger.info(f"  Date range: {history_stats.earliest_date} to {history_stats.latest_date}")

            # Check technical indicators
            tech_stats = session.execute(text("""
                SELECT
                    COUNT(DISTINCT symbol) as symbols_with_tech,
                    COUNT(*) as total_records,
                    COUNT(sma_50) as with_sma50,
                    COUNT(sma_200) as with_sma200
                FROM technical_indicators
            """)).fetchone()

            logger.info("\nTechnical Indicators:")
            logger.info(f"  Symbols with indicators: {tech_stats.symbols_with_tech}")
            logger.info(f"  Total records: {tech_stats.total_records:,}")
            logger.info(f"  With SMA-50: {tech_stats.with_sma50:,}")
            logger.info(f"  With SMA-200: {tech_stats.with_sma200:,}")

            logger.info("\n✅ Data quality validation completed at 10:30 PM")

    except Exception as e:
        logger.error(f"❌ Data quality validation failed: {e}", exc_info=True)


def snapshot_data_quality_audit():
    """Daily 22:05 IST — hit /admin/system/models-status and persist into
    audit_data_quality so coverage trends are SQL-queryable."""
    logger.info("Snapshotting data quality audit")
    try:
        import urllib.request
        import json as _j
        with urllib.request.urlopen("http://trading_system:5001/admin/system/models-status", timeout=30) as r:
            payload = _j.loads(r.read().decode())
        if not payload.get("success"):
            logger.warning(f"models-status failed: {payload.get('error')}")
            return
        from src.services.audit_service import write_data_quality
        write_data_quality(payload.get("models") or [])
        logger.info(f"Wrote data-quality audit for {len(payload.get('models') or [])} models")
    except Exception as e:
        logger.error(f"snapshot_data_quality_audit error: {e}", exc_info=True)


def refresh_sp500_job():
    """Weekly S&P 500 constituent refresh (Saturday 07:00).

    The S&P 500 reconstitutes throughout the year; this keeps sp500.csv (current
    list) and sp500_membership.csv (PIT membership) fresh so the observer models'
    universe gating tracks real index changes. refresh_sp500.py is idempotent and
    leaves the existing files untouched on any fetch failure.
    """
    logger.info("=" * 80)
    logger.info("Refreshing S&P 500 constituent list (current + PIT membership)")
    logger.info("=" * 80)
    _run_subprocess_with_retry(
        ['python3', 'tools/refresh_sp500.py'],
        'refresh_sp500', timeout=300, max_retries=2,
    )


def generate_us_book_signal():
    """Generate today's US book (MOM/TQQQ/BRK) IBKR rebalance plan — DRY-RUN, logs only."""
    logger.info("=" * 80)
    logger.info("US book signal — IBKR rebalance plan (dry-run)")
    logger.info("=" * 80)
    _run_subprocess_with_retry(
        ['python3', 'tools/live/us_executor.py', '--model', 'book'],
        'us_book_signal', timeout=300, max_retries=2, alert_on_fail=False,
    )


def run_scheduler():
    """Main scheduler loop."""
    logger.info("=" * 80)
    logger.info("Data Pipeline Scheduler Started")
    logger.info("=" * 80)
    # Audit: record scheduler boot
    try:
        from src.services.audit_service import write_system_event
        write_system_event("BOOT", "data_scheduler",
                           metadata={"pid": os.getpid()})
    except Exception as _e:
        logger.debug(f"audit BOOT failed: {_e}")
    logger.info("Scheduled Tasks (US / eToro observer):")
    logger.info("  - eToro US daily pull:     Daily at 09:00 PM (combined US universe ~843 syms)")
    logger.info("  - Data coverage gate:      Daily at 09:00 AM")
    logger.info("  - CSV Export + validate:   Daily at 10:00 PM")
    logger.info("  - S&P 500 list refresh:    Weekly Saturday 07:00")
    logger.info("  - Boot catch-up:           eToro pull if historical_data >2d stale")
    logger.info("=" * 80)

    # ---- US eToro data jobs (observer deployment) ----
    # Daily incremental eToro pull = the REAL data-freshness job (eToro is the
    # sole source; the legacy stocks-table saga is empty in US → pulls nothing).
    # US market closes 16:00 ET; 21:00 container-local runs after close.
    schedule.every().day.at("21:00").do(pull_us_etoro_daily)

    # Data-coverage marker + CSV export/validation (read historical_data only —
    # harmless health/backup jobs; the gate just records today's symbol count).
    schedule.every().day.at("09:00").do(pre_market_data_quality_gate)
    schedule.every().day.at("22:00").do(export_daily_csv)
    schedule.every().day.at("22:00").do(validate_data_quality)
    schedule.every().day.at("22:05").do(snapshot_data_quality_audit)

    # Weekly S&P 500 constituent refresh (Saturday 07:00) — keeps the observer
    # models' universe (sp500.csv + sp500_membership.csv) tracking index changes.
    schedule.every().saturday.at("07:00").do(refresh_sp500_job)

    # Observer models' per-model data jobs = no-op (static US CSV universes).
    from tools.models.n40_largecap_weekly.cron import (
        register_data_jobs as register_observer_data,
    )
    register_observer_data(schedule)

    # Boot catch-up: if historical_data is >2 days stale, pull eToro now so a
    # container restart self-heals stale data.
    try:
        from sqlalchemy import text as _text
        from src.models.database import get_database_manager as _gdm
        with _gdm().get_session() as _s:
            _maxd = _s.execute(_text(
                "SELECT MAX(date) FROM historical_data WHERE data_source='yfinance'"
            )).scalar()
        import datetime as _dt
        if _maxd is None or (_dt.date.today() - _maxd).days > 2:
            logger.info(f"Boot catch-up: historical_data max={_maxd} stale → eToro pull now")
            pull_us_etoro_daily()
        else:
            logger.info(f"Boot catch-up: historical_data fresh (max={_maxd}), no pull needed")
    except Exception as _e:
        logger.warning(f"Boot data catch-up failed: {_e}")
    
    # Keep scheduler running
    logger.info("Data scheduler is now running. Press Ctrl+C to stop.")
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Data scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            time.sleep(60)


if __name__ == '__main__':
    run_scheduler()
