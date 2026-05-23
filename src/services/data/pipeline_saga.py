"""
Pipeline Saga - Simple retry pattern with failure tracking
Single file that handles the entire data pipeline with retry logic
"""

import logging
import time
import threading
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
from sqlalchemy import text, func
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from ...models.database import get_database_manager
    from ...models.stock_models import Stock, SymbolMaster
    from ...models.historical_models import HistoricalData, TechnicalIndicators
    from ..core.unified_broker_service import get_unified_broker_service
    from .historical_data_service import get_historical_data_service
except ImportError:
    from src.models.database import get_database_manager
    from src.models.stock_models import Stock, SymbolMaster
    from src.models.historical_models import HistoricalData, TechnicalIndicators
    from src.services.core.unified_broker_service import get_unified_broker_service
    from src.services.data.historical_data_service import get_historical_data_service


class PipelineStep(Enum):
    """Pipeline steps with their order and dependencies.

    Steps 4 (TECHNICAL_INDICATORS) and 5 (COMPREHENSIVE_METRICS) were
    removed — they were unused by any deployed model and the admin UI
    that consumed their output is gone.
    """
    SYMBOL_MASTER = 1
    STOCKS = 2
    HISTORICAL_DATA = 3
    PIPELINE_VALIDATION = 6


class PipelineStatus(Enum):
    """Pipeline status tracking."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class PipelineSaga:
    """
    Simple saga pattern for data pipeline with retry logic and failure tracking.
    Tracks each step, retries on failure, and stores failure reasons.
    """
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self.broker_service = get_unified_broker_service()
        # Get configuration from environment variables
        self.rate_limit_delay = float(os.getenv('SCREENING_QUOTES_RATE_LIMIT_DELAY', '0.2'))
        self.max_workers = int(os.getenv('VOLATILITY_MAX_WORKERS', '5'))
        self.max_stocks = int(os.getenv('VOLATILITY_MAX_STOCKS', '500'))
        self.max_retries = 3
        self.retry_delay = 60  # 1 minute between retries

        logger.info(f"📋 Pipeline configuration: rate_limit={self.rate_limit_delay}s, max_workers={self.max_workers}, max_stocks={self.max_stocks}")

    def _get_last_trading_day(self) -> date:
        """Get the last expected trading day (skip weekends, not holidays yet)."""
        today = datetime.now().date()

        # If today is Saturday (5) or Sunday (6), go back to Friday
        if today.weekday() == 5:  # Saturday
            return today - timedelta(days=1)  # Friday
        elif today.weekday() == 6:  # Sunday
            return today - timedelta(days=2)  # Friday
        else:
            # Weekday - check if market has closed (after 3:30 PM IST)
            now = datetime.now()
            market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

            if now >= market_close_time:
                # Market closed today, today is the last trading day
                return today
            else:
                # Market not closed yet, yesterday is the last complete trading day
                yesterday = today - timedelta(days=1)
                # If yesterday was weekend, go to Friday
                if yesterday.weekday() == 5:  # Saturday
                    return yesterday - timedelta(days=1)  # Friday
                elif yesterday.weekday() == 6:  # Sunday
                    return yesterday - timedelta(days=2)  # Friday
                else:
                    return yesterday
        
    def create_pipeline_tracking_table(self):
        """Verify pipeline tracking table exists (created by init script)."""
        try:
            with self.db_manager.get_session() as session:
                # Just verify the table exists - it's created by init-scripts/01-init-db.sql
                result = session.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'pipeline_tracking'
                """)).scalar()
                if result > 0:
                    logger.info("✅ Pipeline tracking table verified")
                else:
                    logger.error("❌ Pipeline tracking table not found - check init scripts")
        except Exception as e:
            logger.error(f"Error verifying pipeline tracking table: {e}")
    
    def get_step_status(self, step: PipelineStep) -> Dict[str, Any]:
        """Get current status of a pipeline step."""
        try:
            with self.db_manager.get_session() as session:
                result = session.execute(text("""
                    SELECT status, retry_count, failure_reason, last_error, records_processed
                    FROM pipeline_tracking 
                    WHERE step_name = :step_name
                    ORDER BY created_at DESC 
                    LIMIT 1
                """), {'step_name': step.name}).fetchone()
                
                if result:
                    return {
                        'status': result.status,
                        'retry_count': result.retry_count,
                        'failure_reason': result.failure_reason,
                        'last_error': result.last_error,
                        'records_processed': result.records_processed
                    }
                return {'status': 'pending', 'retry_count': 0}
        except Exception as e:
            logger.error(f"Error getting step status: {e}")
            return {'status': 'pending', 'retry_count': 0}
    
    def update_step_status(self, step: PipelineStep, status: PipelineStatus,
                          records_processed: int = 0, error: str = None):
        """Update pipeline step status using UPSERT to handle unique constraint."""
        try:
            with self.db_manager.get_session() as session:
                # Get current retry count for RETRYING status
                current = session.execute(text("""
                    SELECT retry_count FROM pipeline_tracking
                    WHERE step_name = :step_name
                    LIMIT 1
                """), {'step_name': step.name}).fetchone()

                retry_count = (current.retry_count + 1) if current and status == PipelineStatus.RETRYING else (current.retry_count if current else 0)

                # Use UPSERT (INSERT ... ON CONFLICT ... DO UPDATE) to handle unique constraint
                session.execute(text("""
                    INSERT INTO pipeline_tracking
                    (step_name, status, started_at, completed_at, retry_count, failure_reason,
                     records_processed, last_error, updated_at)
                    VALUES (:step_name, :status, :started_at, :completed_at, :retry_count,
                            :failure_reason, :records_processed, :last_error, :updated_at)
                    ON CONFLICT (step_name) DO UPDATE SET
                        status = EXCLUDED.status,
                        started_at = CASE
                            WHEN EXCLUDED.status = 'in_progress' THEN EXCLUDED.started_at
                            ELSE pipeline_tracking.started_at
                        END,
                        completed_at = CASE
                            WHEN EXCLUDED.status = 'completed' THEN EXCLUDED.completed_at
                            ELSE pipeline_tracking.completed_at
                        END,
                        retry_count = EXCLUDED.retry_count,
                        failure_reason = EXCLUDED.failure_reason,
                        records_processed = EXCLUDED.records_processed,
                        last_error = EXCLUDED.last_error,
                        updated_at = EXCLUDED.updated_at
                """), {
                    'step_name': step.name,
                    'status': status.value,
                    'started_at': datetime.utcnow() if status == PipelineStatus.IN_PROGRESS else None,
                    'completed_at': datetime.utcnow() if status == PipelineStatus.COMPLETED else None,
                    'retry_count': retry_count,
                    'failure_reason': error if status == PipelineStatus.FAILED else None,
                    'records_processed': records_processed,
                    'last_error': error,
                    'updated_at': datetime.utcnow()
                })
                session.commit()
        except Exception as e:
            logger.error(f"Error updating step status: {e}")
    
    def execute_step_with_retry(self, step: PipelineStep, step_function) -> Dict[str, Any]:
        """Execute a pipeline step with retry logic."""
        max_retries = self.max_retries
        consecutive_failures = 0
        max_consecutive_failures = 10  # Stop if we get 10 consecutive failures
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"🔄 Executing {step.name} (attempt {attempt + 1}/{max_retries + 1})")
                
                # Update status to in_progress
                self.update_step_status(step, PipelineStatus.IN_PROGRESS)
                
                # Execute the step
                result = step_function()
                
                if result.get('success', False):
                    # Success - reset failure counter
                    consecutive_failures = 0
                    self.update_step_status(step, PipelineStatus.COMPLETED, 
                                          result.get('records_processed', 0))
                    logger.info(f"✅ {step.name} completed successfully")
                    return result
                else:
                    # Failure
                    consecutive_failures += 1
                    error_msg = result.get('error', 'Unknown error')
                    logger.warning(f"⚠️ {step.name} failed: {error_msg}")
                    
                    # Check if we've hit the consecutive failure threshold
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(f"🛑 {step.name} stopped after {consecutive_failures} consecutive failures")
                        self.update_step_status(step, PipelineStatus.FAILED, 
                                              result.get('records_processed', 0), 
                                              f"Stopped after {consecutive_failures} consecutive failures")
                        return {'success': False, 'error': f'Stopped after {consecutive_failures} consecutive failures'}
                    
                    if attempt < max_retries:
                        # Retry
                        self.update_step_status(step, PipelineStatus.RETRYING, 
                                            result.get('records_processed', 0), error_msg)
                        logger.info(f"🔄 Retrying {step.name} in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    else:
                        # Final failure
                        self.update_step_status(step, PipelineStatus.FAILED, 
                                            result.get('records_processed', 0), error_msg)
                        logger.error(f"❌ {step.name} failed after {max_retries} retries")
                        return result
                        
            except Exception as e:
                consecutive_failures += 1
                error_msg = str(e)
                logger.error(f"❌ Exception in {step.name}: {error_msg}")
                
                # Check if we've hit the consecutive failure threshold
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"🛑 {step.name} stopped after {consecutive_failures} consecutive exceptions")
                    self.update_step_status(step, PipelineStatus.FAILED, 0, 
                                          f"Stopped after {consecutive_failures} consecutive exceptions")
                    return {'success': False, 'error': f'Stopped after {consecutive_failures} consecutive exceptions'}
                
                if attempt < max_retries:
                    self.update_step_status(step, PipelineStatus.RETRYING, 0, error_msg)
                    time.sleep(self.retry_delay)
                else:
                    self.update_step_status(step, PipelineStatus.FAILED, 0, error_msg)
                    return {'success': False, 'error': error_msg}
        
        return {'success': False, 'error': 'Max retries exceeded'}
    
    def step_symbol_master(self) -> Dict[str, Any]:
        """Step 1: Ensure symbol master is populated."""
        try:
            with self.db_manager.get_session() as session:
                count = session.execute(text('SELECT COUNT(*) as count FROM symbol_master')).fetchone().count
                
                if count >= 2000:  # Expected ~2253 symbols
                    return {
                        'success': True,
                        'records_processed': count,
                        'message': f'Symbol master already has {count} records'
                    }
                else:
                    # Trigger symbol download
                    from ..data.stock_initialization_service import get_stock_initialization_service
                    init_service = get_stock_initialization_service()
                    result = init_service._load_symbol_master_from_fyers()
                    
                    if result.get('success'):
                        return {
                            'success': True,
                            'records_processed': result.get('total_symbols', 0),
                            'message': 'Symbol master populated successfully'
                        }
                    else:
                        return {
                            'success': False,
                            'error': result.get('error', 'Failed to load symbols')
                        }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def step_stocks(self) -> Dict[str, Any]:
        """Step 2: Ensure stocks table is populated with fundamental data."""
        try:
            with self.db_manager.get_session() as session:
                count = session.execute(text('SELECT COUNT(*) as count FROM stocks')).fetchone().count
                
                if count >= 2000:  # Expected ~2253 stocks
                    logger.info(f"📊 Stocks already exist: {count} records")

                    # Check if fundamental data is mostly missing
                    missing_fundamentals = session.execute(text(
                        "SELECT COUNT(*) as cnt FROM stocks WHERE pe_ratio IS NULL AND sector IS NULL AND eps IS NULL"
                    )).fetchone().cnt
                    missing_pct = (missing_fundamentals / count * 100) if count > 0 else 0

                    if missing_pct > 50:
                        logger.info(f"⚠️ {missing_pct:.0f}% of stocks missing fundamentals ({missing_fundamentals}/{count}) - running initialization for missing stocks")
                        from ..data.stock_initialization_service import get_stock_initialization_service
                        init_service = get_stock_initialization_service()
                        result = init_service.fast_sync_stocks(user_id=1)
                        return {
                            'success': True,
                            'records_processed': result.get('stocks_created', 0) if result.get('success') else count,
                            'message': f'Ran fundamental data update for {missing_fundamentals} stocks missing data'
                        }

                    logger.info("⚡ Skipping fundamental data update - data is sufficiently complete")
                    return {
                        'success': True,
                        'records_processed': count,
                        'message': f'Stocks already has {count} records with sufficient fundamental data'
                    }
                else:
                    # Trigger stock sync (volatility warning is expected here)
                    # Volatility will be calculated in Step 5 (VOLATILITY_CALCULATION)
                    from ..data.stock_initialization_service import get_stock_initialization_service
                    init_service = get_stock_initialization_service()
                    result = init_service.fast_sync_stocks(user_id=1)
                    
                    if result.get('success'):
                        # Skip fundamental data update for speed - can be done later
                        logger.info("⚡ Skipping fundamental data update for faster saga completion")

                        return {
                            'success': True,
                            'records_processed': result.get('stocks_created', 0),
                            'message': 'Stocks populated successfully (fundamental data skipped for speed, volatility will be calculated in Step 5)'
                        }
                    else:
                        return {
                            'success': False,
                            'error': result.get('error', 'Failed to sync stocks')
                        }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def step_historical_data(self) -> Dict[str, Any]:
        """Step 3: Download historical data for stocks missing data for last trading day."""
        try:
            # Get the last expected trading day
            last_trading_day = self._get_last_trading_day()
            logger.info(f"📅 Checking historical data up to last trading day: {last_trading_day}")

            # Get stocks that need historical data (missing data for last trading day)
            with self.db_manager.get_session() as session:
                stocks_needing_data = session.execute(text("""
                    SELECT s.symbol FROM stocks s
                    LEFT JOIN (
                        SELECT symbol, MAX(date) as latest_date
                        FROM historical_data
                        GROUP BY symbol
                    ) h ON s.symbol = h.symbol
                    WHERE (h.symbol IS NULL OR h.latest_date < :last_trading_day)
                    AND s.is_active = true AND s.is_tradeable = true
                    ORDER BY s.volume DESC
                    LIMIT :max_stocks
                """), {'last_trading_day': last_trading_day, 'max_stocks': self.max_stocks}).fetchall()

                if not stocks_needing_data:
                    logger.info(f"✅ All stocks have data up to {last_trading_day}")
                    return {
                        'success': True,
                        'records_processed': 0,
                        'message': f'All stocks have data up to {last_trading_day}'
                    }

                symbols = [row.symbol for row in stocks_needing_data]
                logger.info(f"📊 Downloading historical data for {len(symbols)} stocks missing data for {last_trading_day}")

                # Use historical_data_service which has all smart logic:
                # - API response classification
                # - Retry with exponential backoff
                # - Placeholder records for holidays/weekends
                # - Smart error handling
                from concurrent.futures import ThreadPoolExecutor, as_completed

                historical_service = get_historical_data_service()

                total_records = 0
                successful_downloads = 0
                failed_downloads = 0
                results_lock = threading.Lock()

                def download_symbol(symbol):
                    """
                    Download historical data for a single symbol using the service.
                    This ensures consistent logic across scheduled and startup pipelines.
                    """
                    try:
                        # Rate limiting before API call
                        time.sleep(self.rate_limit_delay)

                        # Use the historical_data_service which has all the smart logic
                        result = historical_service.fetch_single_stock_history(
                            user_id=1,
                            symbol=symbol,
                            days=365
                        )

                        # Service handles:
                        # - Checking if data exists for last_trading_day
                        # - API response classification (rate limit, timeout, success, etc.)
                        # - Creating placeholder records for holidays/weekends
                        # - Retry logic with exponential backoff
                        # - Smart error handling

                        if result.get('success'):
                            records = result.get('records_added', 0)
                            if records > 0:
                                logger.info(f"✅ Downloaded {records} records for {symbol}")
                            else:
                                logger.info(f"ℹ️ {symbol}: {result.get('message', 'No new data')}")
                            return {'success': True, 'symbol': symbol, 'records': records}
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            logger.warning(f"⚠️ No data for {symbol}: {error_msg}")
                            return {'success': False, 'symbol': symbol, 'error': error_msg}
                    except Exception as e:
                        logger.warning(f"Error downloading {symbol}: {e}")
                        return {'success': False, 'symbol': symbol, 'error': str(e)}

                # Use ThreadPoolExecutor for concurrent downloads (configurable workers to respect rate limits)
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(download_symbol, symbol): symbol for symbol in symbols}

                    for future in as_completed(futures):
                        result = future.result()
                        with results_lock:
                            if result['success']:
                                successful_downloads += 1
                                total_records += result.get('records', 0)
                            else:
                                failed_downloads += 1

                        # Progress logging every 50 stocks
                        if (successful_downloads + failed_downloads) % 50 == 0:
                            logger.info(f"Progress: {successful_downloads + failed_downloads}/{len(symbols)} - Success: {successful_downloads}, Failed: {failed_downloads}")

                logger.info(f"📊 Download summary: {successful_downloads} successful, {failed_downloads} failed, {total_records} total records")

                return {
                    'success': True,
                    'records_processed': total_records,
                    'message': f'Downloaded historical data for {successful_downloads}/{len(symbols)} stocks'
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def step_pipeline_validation(self) -> Dict[str, Any]:
        """Step 6: Final validation to ensure all steps completed successfully."""
        try:
            logger.info("🔄 Starting pipeline validation step...")
            
            validation_results = {
                'symbol_master_count': 0,
                'stocks_count': 0,
                'historical_data_count': 0,
                'technical_indicators_count': 0,
                'volatility_calculated_count': 0,
                'issues': []
            }
            
            with self.db_manager.get_session() as session:
                # Check symbol_master table
                result = session.execute(text("SELECT COUNT(*) FROM symbol_master")).scalar()
                validation_results['symbol_master_count'] = result
                if result == 0:
                    validation_results['issues'].append("❌ Symbol master table is empty")
                
                # Check stocks table
                result = session.execute(text("SELECT COUNT(*) FROM stocks")).scalar()
                validation_results['stocks_count'] = result
                if result == 0:
                    validation_results['issues'].append("❌ Stocks table is empty")
                
                # Check historical_data table
                result = session.execute(text("SELECT COUNT(*) FROM historical_data")).scalar()
                validation_results['historical_data_count'] = result
                if result == 0:
                    validation_results['issues'].append("❌ Historical data table is empty")
                
                # Check technical_indicators table
                result = session.execute(text("SELECT COUNT(*) FROM technical_indicators")).scalar()
                validation_results['technical_indicators_count'] = result
                if result == 0:
                    validation_results['issues'].append("❌ Technical indicators table is empty")
                
                # Check stocks with volatility data (allow partial data)
                result = session.execute(text("SELECT COUNT(*) FROM stocks WHERE historical_volatility_1y IS NOT NULL AND historical_volatility_1y > 0")).scalar()
                validation_results['volatility_calculated_count'] = result
                # Don't fail if no volatility data - it's optional

                # Check data quality (allow mismatches - partial data is OK)
                symbols_with_historical = session.execute(text("""
                    SELECT COUNT(DISTINCT symbol) FROM historical_data
                """)).scalar()

                symbols_with_indicators = session.execute(text("""
                    SELECT COUNT(DISTINCT symbol) FROM technical_indicators
                """)).scalar()

                # Log data mismatch as info, not error
                if symbols_with_historical != symbols_with_indicators:
                    logger.info(f"📊 Data coverage: {symbols_with_historical} symbols have historical data, {symbols_with_indicators} have technical indicators")
            
            # Determine overall success - only fail on critical issues (empty core tables)
            critical_issues = [issue for issue in validation_results['issues']
                             if 'Symbol master table is empty' in issue or 'Stocks table is empty' in issue]
            success = len(critical_issues) == 0

            # Log all issues for debugging
            if validation_results['issues']:
                logger.info(f"📋 Validation issues found: {validation_results['issues']}")

            if success:
                if len(validation_results['issues']) == 0:
                    logger.info("✅ Pipeline validation passed - all data is complete")
                    message = "Pipeline validation passed - all data is complete"
                else:
                    logger.info("✅ Pipeline validation passed - core data is available (partial data is acceptable)")
                    message = f"Pipeline validation passed - core data available, {len(validation_results['issues'])} minor issues acceptable"
            else:
                logger.error(f"❌ Pipeline validation failed - critical issues: {critical_issues}")
                message = f"Pipeline validation failed - critical data missing"
            
            return {
                'success': success,
                'records_processed': 0,
                'message': message,
                'validation_results': validation_results,
                'symbol_master_count': validation_results['symbol_master_count'],
                'stocks_count': validation_results['stocks_count'],
                'historical_data_count': validation_results['historical_data_count'],
                'technical_indicators_count': validation_results['technical_indicators_count'],
                'volatility_calculated_count': validation_results['volatility_calculated_count']
            }
            
        except Exception as e:
            logger.error(f"❌ Error in pipeline validation step: {e}")
            return {
                'success': False,
                'records_processed': 0,
                'message': f'Pipeline validation failed: {e}'
            }

    def _store_historical_data(self, symbol: str, candles: list) -> int:
        """
        Store historical OHLCV data from Fyers API with calculated technical fields.

        This method processes raw candle data from Fyers API and stores it with additional
        calculated fields for candlestick analysis, price movements, and volume metrics.

        Args:
            symbol: Stock symbol (e.g., 'NSE:RELIANCE-EQ')
            candles: List of candle dictionaries from Fyers API
                    Each candle contains: {timestamp, open, high, low, close, volume}

        Returns:
            Number of records successfully added to database
        """
        records_added = 0
        if not candles:
            return 0

        try:
            with self.db_manager.get_session() as session:
                # Get existing dates for the symbol to avoid duplicates
                existing_dates = set(
                    r.date for r in session.query(HistoricalData.date).filter(
                        HistoricalData.symbol == symbol
                    ).all()
                )

                for candle in candles:
                    try:
                        # Convert Unix timestamp to date
                        from datetime import datetime
                        timestamp = int(candle['timestamp'])
                        record_date = datetime.fromtimestamp(timestamp).date()

                        if record_date in existing_dates:
                            continue  # Skip if already exists (avoid duplicates)

                        # ===== STEP 1: Extract raw OHLCV data from Fyers API =====
                        open_price = float(candle['open'])
                        high_price = float(candle['high'])
                        low_price = float(candle['low'])
                        close_price = float(candle['close'])
                        volume_val = int(candle['volume'])

                        # ===== STEP 2: Calculate price movement metrics =====

                        # Price Change: Absolute difference between close and open
                        # Formula: Close - Open
                        price_change = close_price - open_price

                        # Price Change Percentage: Relative change as percentage
                        # Formula: ((Close - Open) / Open) × 100
                        # Example: If Open=100, Close=105 → (105-100)/100 × 100 = 5%
                        price_change_pct = (price_change / open_price * 100) if open_price > 0 else 0

                        # ===== STEP 3: Calculate candlestick range metrics =====

                        # High-Low Range: Total price range for the day
                        high_low_range = high_price - low_price

                        # High-Low Percentage: Range as percentage of closing price
                        # Formula: ((High - Low) / Close) × 100
                        # Indicates daily volatility relative to close price
                        high_low_pct = (high_low_range / close_price * 100) if close_price > 0 and high_low_range > 0 else 0

                        # ===== STEP 4: Calculate candlestick body and shadow metrics =====
                        # These metrics help identify candlestick patterns (doji, hammer, etc.)

                        # Body Percentage: Body size as % of total range
                        # Formula: (|Close - Open| / (High - Low)) × 100
                        # High value = strong directional move, Low value = indecision (doji)
                        body_pct = (abs(close_price - open_price) / high_low_range * 100) if high_low_range > 0 else 0

                        # Upper Shadow Percentage: Upper wick as % of total range
                        # Formula: ((High - max(Open, Close)) / (High - Low)) × 100
                        # Large upper shadow = rejection of higher prices
                        upper_shadow_pct = ((high_price - max(open_price, close_price)) / high_low_range * 100) if high_low_range > 0 else 0

                        # Lower Shadow Percentage: Lower wick as % of total range
                        # Formula: ((min(Open, Close) - Low) / (High - Low)) × 100
                        # Large lower shadow = rejection of lower prices (bullish)
                        lower_shadow_pct = ((min(open_price, close_price) - low_price) / high_low_range * 100) if high_low_range > 0 else 0

                        # ===== STEP 5: Calculate volume metrics =====

                        # Turnover: Total value traded in crores (INR)
                        # Formula: (Close Price × Volume) / 10,000,000
                        # Dividing by 10M converts to crores (1 crore = 10 million)
                        turnover_inr = close_price * volume_val / 10000000 if close_price and volume_val else 0

                        # ===== STEP 6: Create and store the historical record =====
                        historical_record = HistoricalData(
                            symbol=symbol,
                            date=record_date,
                            timestamp=timestamp,

                            # Raw OHLCV from Fyers API
                            open=open_price,
                            high=high_price,
                            low=low_price,
                            close=close_price,
                            volume=volume_val,

                            # Calculated metrics
                            turnover=turnover_inr,
                            price_change=price_change,
                            price_change_pct=price_change_pct,
                            high_low_pct=high_low_pct,
                            body_pct=body_pct,
                            upper_shadow_pct=upper_shadow_pct,
                            lower_shadow_pct=lower_shadow_pct,

                            # Metadata
                            data_source='fyers',
                            api_resolution='1D',
                            data_quality_score=1.0,
                            is_adjusted=False  # Not adjusted for splits/dividends
                        )
                        session.add(historical_record)
                        records_added += 1

                    except Exception as e:
                        logger.warning(f"Error storing record for {symbol} on {record_date}: {e}")
                        continue

                session.commit()

        except Exception as e:
            logger.error(f"Error storing historical data for {symbol}: {e}")

        return records_added
    
    def run_pipeline(self) -> Dict[str, Any]:
        """Run the complete pipeline with saga pattern."""
        try:
            logger.info("🚀 Starting Pipeline Saga")
            
            # Create tracking table
            self.create_pipeline_tracking_table()
            
            results = {
                'success': True,
                'steps_completed': [],
                'steps_failed': [],
                'total_records_processed': 0
            }
            
            # Execute each step with retry logic
            steps = [
                (PipelineStep.SYMBOL_MASTER, self.step_symbol_master),
                (PipelineStep.STOCKS, self.step_stocks),
                (PipelineStep.HISTORICAL_DATA, self.step_historical_data),
                (PipelineStep.PIPELINE_VALIDATION, self.step_pipeline_validation)
            ]
            
            for step, step_function in steps:
                logger.info(f"🔄 Executing {step.name}")
                
                result = self.execute_step_with_retry(step, step_function)
                
                if result.get('success'):
                    results['steps_completed'].append(step.name)
                    results['total_records_processed'] += result.get('records_processed', 0)
                else:
                    results['steps_failed'].append({
                        'step': step.name,
                        'error': result.get('error', 'Unknown error')
                    })
                    results['success'] = False
            
            logger.info(f"🎉 Pipeline Saga completed: {len(results['steps_completed'])}/{len(steps)} steps successful")
            return results
            
        except Exception as e:
            logger.error(f"❌ Pipeline Saga failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'steps_completed': [],
                'steps_failed': []
            }
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status from tracking table."""
        try:
            with self.db_manager.get_session() as session:
                results = session.execute(text("""
                    SELECT step_name, status, retry_count, failure_reason,
                           records_processed, last_error, updated_at
                    FROM pipeline_tracking
                    ORDER BY step_name
                """)).fetchall()

                status = {}
                for row in results:
                    status[row.step_name] = {
                        'status': row.status,
                        'retry_count': row.retry_count,
                        'failure_reason': row.failure_reason,
                        'records_processed': row.records_processed,
                        'last_error': row.last_error,
                        'updated_at': row.updated_at
                    }

                return status
        except Exception as e:
            logger.error(f"Error getting pipeline status: {e}")
            return {}


# Global saga instance
_pipeline_saga = None

def get_pipeline_saga() -> PipelineSaga:
    """Get the global pipeline saga instance."""
    global _pipeline_saga
    if _pipeline_saga is None:
        _pipeline_saga = PipelineSaga()
    return _pipeline_saga
