"""
Historical Data Service
Fetches and stores comprehensive historical OHLCV data for enhanced technical analysis
Supports 1+ years of data for accurate indicator calculations
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta, date
from enum import Enum
import time
from sqlalchemy import and_, desc, func

logger = logging.getLogger(__name__)


class APIResponseType(Enum):
    """API response classification for intelligent handling."""
    SUCCESS_WITH_DATA = "success_with_data"
    SUCCESS_NO_DATA_MARKET_CLOSED = "success_no_data_market_closed"
    ERROR_INVALID_SYMBOL = "error_invalid_symbol"
    ERROR_RATE_LIMIT = "error_rate_limit"
    ERROR_TIMEOUT = "error_timeout"
    ERROR_SERVER = "error_server"
    ERROR_UNKNOWN = "error_unknown"

try:
    from ..core.unified_broker_service import get_unified_broker_service
    from ...models.database import get_database_manager
    from ...models.historical_models import HistoricalData, MarketBenchmarks, DataQualityMetrics
    from ...models.stock_models import Stock
except ImportError:
    from src.services.core.unified_broker_service import get_unified_broker_service
    from src.models.database import get_database_manager
    from src.models.historical_models import HistoricalData, MarketBenchmarks, DataQualityMetrics
    from src.models.stock_models import Stock


class HistoricalDataService:
    """Service to fetch and manage historical OHLCV data for enhanced technical analysis."""

    def __init__(self):
        self.broker_service = get_unified_broker_service()
        self.db_manager = get_database_manager()
        import os
        self.rate_limit_delay = float(os.getenv('SCREENING_QUOTES_RATE_LIMIT_DELAY', '0.3'))
        self.batch_size = 10  # Process stocks in small batches
        self.max_retries = 3  # Retry failed API calls up to 3 times
        self.retry_delays = [2, 5, 10]  # Exponential backoff: 2s, 5s, 10s

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

    def fetch_historical_data_bulk(self, user_id: int = 1, days: int = 365,
                                   max_stocks: int = 100) -> Dict[str, Any]:
        """
        Fetch historical data for multiple stocks efficiently.

        Args:
            user_id: User ID for API access
            days: Number of historical days to fetch (365 = 1 year, Fyers API max for daily resolution)
            max_stocks: Maximum number of stocks to process

        Returns:
            Dict with success status and statistics
        """
        start_time = time.time()

        try:
            logger.info(f"🔄 Starting bulk historical data fetch for {days} days")

            # Get stocks that need historical data
            stocks_to_process = self._get_stocks_needing_data(max_stocks)
            logger.info(f"📊 Found {len(stocks_to_process)} stocks needing historical data")

            if not stocks_to_process:
                return {
                    'success': True,
                    'message': 'No stocks need historical data updates',
                    'processed': 0,
                    'duration': 0
                }

            # Process in batches
            total_processed = 0
            total_success = 0
            total_failed = 0

            for i in range(0, len(stocks_to_process), self.batch_size):
                batch = stocks_to_process[i:i + self.batch_size]
                batch_num = i // self.batch_size + 1
                total_batches = (len(stocks_to_process) + self.batch_size - 1) // self.batch_size

                logger.info(f"⚡ Processing batch {batch_num}/{total_batches} ({len(batch)} stocks)")

                batch_results = self._process_batch(user_id, batch, days)
                total_processed += batch_results['processed']
                total_success += batch_results['success']
                total_failed += batch_results['failed']

                # Rate limiting between batches
                if i + self.batch_size < len(stocks_to_process):
                    time.sleep(self.rate_limit_delay)

            # Update data quality metrics
            self._update_data_quality_metrics(stocks_to_process)

            duration = time.time() - start_time
            logger.info(f"✅ Bulk historical data fetch completed in {duration:.2f}s")
            logger.info(f"📈 Results: {total_success} success, {total_failed} failed, {total_processed} total")

            return {
                'success': True,
                'processed': total_processed,
                'successful': total_success,
                'failed': total_failed,
                'duration_seconds': duration,
                'message': f'Processed {total_processed} stocks with {total_success} successful fetches'
            }

        except Exception as e:
            logger.error(f"Error in bulk historical data fetch: {e}")
            return {
                'success': False,
                'error': str(e),
                'processed': 0
            }

    def fetch_single_stock_history(self, user_id: int, symbol: str, days: int = 365) -> Dict[str, Any]:
        """
        Fetch historical data for a single stock incrementally.

        Args:
            user_id: User ID for API access
            symbol: Stock symbol (e.g., 'NSE:RELIANCE-EQ')
            days: Number of historical days to fetch

        Returns:
            Dict with success status and data info
        """
        try:
            logger.info(f"📊 Fetching historical data for {symbol} (incremental update)")

            # Get existing data range for this symbol
            existing_data_range = self._get_existing_data_range(symbol)

            if existing_data_range:
                # We have some data, fetch only missing recent data
                latest_date = existing_data_range['latest_date']
                days_gap = (datetime.now().date() - latest_date).days

                if days_gap <= 1:
                    logger.info(f"✅ {symbol} historical data is up to date (latest: {latest_date})")
                    return {
                        'success': True,
                        'symbol': symbol,
                        'message': 'Data is current',
                        'records_added': 0
                    }

                # Fetch only missing days (plus a few extra for safety)
                start_date = latest_date + timedelta(days=1)
                end_date = datetime.now().date()

                logger.info(f"📈 Fetching missing data for {symbol}: {start_date} to {end_date} ({days_gap} days)")

            else:
                # No existing data, fetch full range
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=days)
                logger.info(f"📊 Fetching complete historical data for {symbol}: {start_date} to {end_date} ({days} days)")

            # Check if we need to fetch (avoid unnecessary API calls)
            if existing_data_range and (datetime.now().date() - existing_data_range['latest_date']).days <= 1:
                logger.info(f"✅ {symbol} already has current historical data")
                return {
                    'success': True,
                    'symbol': symbol,
                    'message': 'Data already current',
                    'records_added': 0
                }

            # Fetch from API
            historical_data = self._fetch_from_api(user_id, symbol, start_date, end_date)

            if historical_data is None or (hasattr(historical_data, 'empty') and historical_data.empty):
                # Check if this is expected (weekend/holiday) or an error
                last_trading_day = self._get_last_trading_day()

                if end_date >= last_trading_day:
                    # Requesting current/recent data but market might be closed
                    # No need to create placeholder - just log and return success
                    logger.info(f"ℹ️ No data for {symbol} up to {last_trading_day} (market likely closed/holiday)")
                    return {
                        'success': True,
                        'symbol': symbol,
                        'records_added': 0,
                        'message': 'Market closed - no new data available'
                    }
                else:
                    # Requesting historical data that should exist - genuine error
                    logger.warning(f"❌ No historical data received for {symbol} from {start_date} to {end_date}")
                    return {
                        'success': False,
                        'symbol': symbol,
                        'error': 'No data received from API'
                    }

            # Store in database
            records_added = self._store_historical_data(symbol, historical_data)

            logger.info(f"✅ Stored {records_added} records for {symbol}")
            return {
                'success': True,
                'symbol': symbol,
                'records_added': records_added,
                'data_range': f"{start_date} to {end_date}"
            }

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return {
                'success': False,
                'symbol': symbol,
                'error': str(e)
            }

    def fetch_market_benchmarks(self, user_id: int = 1, days: int = 365) -> Dict[str, Any]:
        """
        Fetch historical data for market benchmarks (NIFTY, SENSEX).
        Essential for beta calculations and relative performance analysis.
        """
        try:
            logger.info(f"📈 Fetching market benchmark data for {days} days")

            benchmarks = ['NSE:NIFTY50-INDEX', 'BSE:SENSEX-INDEX']
            results = {}

            for benchmark in benchmarks:
                try:
                    result = self._fetch_benchmark_data(user_id, benchmark, days)
                    results[benchmark] = result

                    # Rate limiting
                    time.sleep(self.rate_limit_delay)

                except Exception as e:
                    logger.error(f"Error fetching {benchmark}: {e}")
                    results[benchmark] = {'success': False, 'error': str(e)}

            successful = sum(1 for r in results.values() if r.get('success'))

            return {
                'success': successful > 0,
                'benchmarks_processed': len(benchmarks),
                'successful': successful,
                'details': results
            }

        except Exception as e:
            logger.error(f"Error fetching market benchmarks: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _get_stocks_needing_data(self, max_stocks: int) -> List[str]:
        """Get list of stock symbols that need historical data based on last trading day."""
        try:
            with self.db_manager.get_session() as session:
                # Get the last expected trading day (accounts for weekends and market hours)
                last_trading_day = self._get_last_trading_day()
                today = datetime.now().date()

                logger.info(f"📅 Last expected trading day: {last_trading_day}, Today: {today}")

                # Get active stocks with current prices (indicates they're being tracked)
                base_query = session.query(Stock.symbol).filter(
                    Stock.is_active == True,
                    Stock.current_price.isnot(None),
                    Stock.volume.isnot(None)
                )

                # Find stocks that need historical data updates:
                # 1. Stocks with no historical data at all
                # 2. Stocks missing data for the last trading day

                # Get last historical data date for each stock
                latest_data_subquery = session.query(
                    HistoricalData.symbol,
                    func.max(HistoricalData.date).label('latest_date')
                ).group_by(HistoricalData.symbol).subquery()

                # Join with stocks to find those needing updates
                # Only update if we don't have data for the last trading day
                stocks_with_data = session.query(Stock.symbol).join(
                    latest_data_subquery,
                    Stock.symbol == latest_data_subquery.c.symbol
                ).filter(
                    # Missing data from last trading day
                    latest_data_subquery.c.latest_date < last_trading_day
                )

                # Stocks with no historical data at all
                stocks_without_data = base_query.filter(
                    ~Stock.symbol.in_(
                        session.query(HistoricalData.symbol).distinct()
                    )
                )

                # Combine both queries and prioritize by volume (higher volume first)
                stocks_needing_data = stocks_with_data.union(stocks_without_data).order_by(desc(Stock.volume)).limit(max_stocks).all()

                if not stocks_needing_data:
                    # Fallback: get stocks without data at all
                    stocks_needing_data = stocks_without_data.order_by(desc(Stock.volume)).limit(max_stocks).all()

                symbols = [stock.symbol for stock in stocks_needing_data]
                logger.info(f"📊 Found {len(symbols)} stocks needing data up to {last_trading_day}")

                return symbols

        except Exception as e:
            logger.error(f"Error getting stocks needing data: {e}")
            # Fallback: get any active stocks
            try:
                with self.db_manager.get_session() as session:
                    stocks = session.query(Stock.symbol).filter(
                        Stock.is_active == True,
                        Stock.current_price.isnot(None)
                    ).order_by(desc(Stock.volume)).limit(max_stocks).all()
                    return [stock.symbol for stock in stocks]
            except:
                return []

    def _process_batch(self, user_id: int, symbols: List[str], days: int) -> Dict[str, int]:
        """Process a batch of symbols for historical data."""
        results = {'processed': 0, 'success': 0, 'failed': 0}

        for symbol in symbols:
            try:
                result = self.fetch_single_stock_history(user_id, symbol, days)
                results['processed'] += 1

                if result.get('success'):
                    results['success'] += 1
                else:
                    results['failed'] += 1

                # Rate limiting between individual stocks
                time.sleep(self.rate_limit_delay)

            except Exception as e:
                logger.error(f"Error processing {symbol} in batch: {e}")
                results['processed'] += 1
                results['failed'] += 1

        return results

    def _classify_api_response(self, result: Dict, symbol: str) -> Tuple[APIResponseType, Optional[Any]]:
        """Classify API response for intelligent handling."""
        # Check for invalid symbol (delisted or not available on broker)
        if (result.get('status') == 'error' and
            ('invalid symbol' in str(result.get('message', '')).lower() or
             result.get('error_code') == -300)):
            return APIResponseType.ERROR_INVALID_SYMBOL, None

        # Check for rate limit error
        if 'rate limit' in str(result.get('error', '')).lower() or result.get('status_code') == 429:
            return APIResponseType.ERROR_RATE_LIMIT, None

        # Check for timeout
        if 'timeout' in str(result.get('error', '')).lower():
            return APIResponseType.ERROR_TIMEOUT, None

        # Check for server errors
        if result.get('status_code') in [500, 502, 503]:
            return APIResponseType.ERROR_SERVER, None

        # Success with data
        if (result.get('success') or result.get('status') == 'success') and result.get('data'):
            return APIResponseType.SUCCESS_WITH_DATA, result['data']

        # Success but no data (could be market closed/holiday)
        if (result.get('success') or result.get('status') == 'success') and not result.get('data'):
            return APIResponseType.SUCCESS_NO_DATA_MARKET_CLOSED, None

        # Unknown error - log details for debugging
        logger.debug(f"Unknown error for {symbol}: success={result.get('success')}, status={result.get('status')}, message={result.get('message')}, error={result.get('error')}, error_code={result.get('error_code')}, status_code={result.get('status_code')}")
        return APIResponseType.ERROR_UNKNOWN, None

    def _fetch_from_api(self, user_id: int, symbol: str, start_date: date, end_date: date) -> Optional[pd.DataFrame]:
        """Fetch historical data from broker API with intelligent retry logic."""

        # Calculate number of days for the period parameter
        days_diff = (end_date - start_date).days
        period = f"{days_diff}d"

        for attempt in range(self.max_retries + 1):  # +1 for initial attempt
            try:
                if attempt > 0:
                    delay = self.retry_delays[attempt - 1]
                    logger.info(f"🔄 Retry attempt {attempt}/{self.max_retries} for {symbol} (waiting {delay}s)")
                    time.sleep(delay)

                # Use broker service to get historical data
                result = self.broker_service.get_historical_data(
                    user_id=user_id,
                    symbol=symbol,
                    resolution='1D',
                    period=period
                )

                # Classify response
                response_type, data = self._classify_api_response(result, symbol)

                # Handle based on response type
                if response_type == APIResponseType.SUCCESS_WITH_DATA:
                    # Success - proceed with data
                    break
                elif response_type == APIResponseType.SUCCESS_NO_DATA_MARKET_CLOSED:
                    # Market closed/holiday - don't retry, return None gracefully
                    logger.info(f"ℹ️ No data for {symbol} (market likely closed)")
                    return None
                elif response_type == APIResponseType.ERROR_INVALID_SYMBOL:
                    # Invalid symbol (delisted/not available) - don't retry
                    logger.warning(f"⚠️ Invalid symbol {symbol} - skipping (delisted or not available on broker)")
                    return None
                elif response_type in [APIResponseType.ERROR_RATE_LIMIT, APIResponseType.ERROR_TIMEOUT]:
                    # Retryable errors - continue loop
                    if attempt < self.max_retries:
                        logger.warning(f"⚠️ {response_type.value} for {symbol} (attempt {attempt + 1})")
                        continue
                    else:
                        logger.error(f"❌ {response_type.value} for {symbol} after {self.max_retries} retries")
                        return None
                else:
                    # Other errors - retry but with less confidence
                    if attempt < self.max_retries:
                        logger.warning(f"⚠️ {response_type.value} for {symbol} (attempt {attempt + 1})")
                        continue
                    else:
                        logger.error(f"❌ {response_type.value} for {symbol} after {self.max_retries} retries")
                        return None

            except Exception as e:
                if attempt < self.max_retries:
                    logger.warning(f"⚠️ Exception for {symbol} (attempt {attempt + 1}): {e}")
                    continue
                else:
                    logger.error(f"❌ Exception for {symbol} after {self.max_retries} retries: {e}")
                    return None

        # Convert to DataFrame (only reached after successful API call)
        try:
            data = result['data']

            # Handle different data formats from API
            if isinstance(data, dict) and 'candles' in data:
                # Fyers API format: data.candles is array of OHLCV arrays
                candles = data['candles']
                if isinstance(candles, list) and len(candles) > 0:
                    # Convert each candle array to dict
                    processed_data = []
                    for candle in candles:
                        if isinstance(candle, dict):
                            processed_data.append(candle)
                        elif isinstance(candle, list) and len(candle) >= 6:
                            # Handle array format [timestamp, open, high, low, close, volume]
                            processed_data.append({
                                'timestamp': candle[0],
                                'open': candle[1],
                                'high': candle[2],
                                'low': candle[3],
                                'close': candle[4],
                                'volume': candle[5]
                            })
                    data = processed_data
                else:
                    logger.warning(f"No candles data for {symbol}")
                    return None
            elif isinstance(data, list) and len(data) > 0:
                # Direct list format
                pass
            else:
                logger.warning(f"Unexpected data format for {symbol}: {type(data)}")
                return None

            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data)

                # Standardize column names (excluding timestamp - handle separately)
                column_mapping = {
                    'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume',
                    'open_price': 'open', 'high_price': 'high', 'low_price': 'low',
                    'close_price': 'close'
                }

                df = df.rename(columns=column_mapping)

                # Ensure required columns exist (adjusted for timestamp before conversion)
                if 'timestamp' in df.columns:
                    required_cols = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
                else:
                    required_cols = ['open', 'high', 'low', 'close', 'volume', 'date']

                if not all(col in df.columns for col in required_cols):
                    logger.warning(f"Missing required columns for {symbol}: {df.columns.tolist()}")
                    return None

                # Convert timestamp/date
                if 'timestamp' in df.columns:
                    # Convert string timestamps to integers first
                    timestamps_int = [int(ts) for ts in df['timestamp'].tolist()]
                    # Convert to datetime using manual conversion to avoid pandas issues
                    from datetime import datetime
                    dates = [datetime.fromtimestamp(ts).date() for ts in timestamps_int]
                    df['date'] = dates
                    df = df.drop('timestamp', axis=1)
                elif 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date']).dt.date

                return df

            return None

        except Exception as e:
            logger.error(f"Error processing API response for {symbol}: {e}")
            return None

    def _store_historical_data(self, symbol: str, df: pd.DataFrame) -> int:
        """Store historical data in database."""
        try:
            records_added = 0

            with self.db_manager.get_session() as session:
                # Get all existing dates for this symbol in one query (more efficient)
                existing_dates = set(
                    date for (date,) in session.query(HistoricalData.date).filter(
                        HistoricalData.symbol == symbol
                    ).all()
                )

                for _, row in df.iterrows():
                    try:
                        # Skip if record already exists
                        if row['date'] in existing_dates:
                            continue

                        # Create new record with ALL Fyers fields + calculated fields
                        open_price = float(row['open'])
                        high_price = float(row['high'])
                        low_price = float(row['low'])
                        close_price = float(row['close'])
                        volume_val = int(row['volume'])

                        # Calculate additional fields for enhanced analysis
                        price_change = close_price - open_price
                        price_change_pct = (price_change / open_price * 100) if open_price > 0 else 0
                        high_low_range = high_price - low_price
                        high_low_pct = (high_low_range / close_price * 100) if close_price > 0 and high_low_range > 0 else 0
                        body_pct = (abs(close_price - open_price) / high_low_range * 100) if high_low_range > 0 else 0
                        upper_shadow_pct = ((high_price - max(open_price, close_price)) / high_low_range * 100) if high_low_range > 0 else 0
                        lower_shadow_pct = ((min(open_price, close_price) - low_price) / high_low_range * 100) if high_low_range > 0 else 0
                        turnover_inr = close_price * volume_val / 10000000 if close_price and volume_val else 0  # in crores

                        historical_record = HistoricalData(
                            symbol=symbol,
                            date=row['date'],
                            timestamp=int(row.get('timestamp', 0)),  # Store original Unix timestamp

                            # Core OHLCV from Fyers (ALL 6 fields)
                            open=open_price,
                            high=high_price,
                            low=low_price,
                            close=close_price,
                            volume=volume_val,

                            # Calculated fields for enhanced analysis
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
                            data_quality_score=1.0,  # Full data available
                            is_adjusted=False
                        )

                        session.add(historical_record)
                        records_added += 1
                        # Add to existing_dates set to prevent duplicates within same batch
                        existing_dates.add(row['date'])

                    except Exception as e:
                        logger.warning(f"Error storing record for {symbol} on {row['date']}: {e}")
                        session.rollback()  # Rollback failed transaction
                        continue

                # Commit all successfully added records
                try:
                    session.commit()
                except Exception as e:
                    logger.warning(f"Error committing records for {symbol}: {e}")
                    session.rollback()

                return records_added

        except Exception as e:
            logger.error(f"Error storing historical data for {symbol}: {e}")
            return 0

    def _fetch_benchmark_data(self, user_id: int, benchmark: str, days: int) -> Dict[str, Any]:
        """Fetch and store benchmark data."""
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            # Fetch data
            df = self._fetch_from_api(user_id, benchmark, start_date, end_date)

            if df is None or len(df) == 0:
                return {'success': False, 'error': 'No data received'}

            # Store benchmark data
            records_added = 0
            benchmark_name = benchmark.split(':')[1].replace('-INDEX', '').replace('-EQ', '')

            with self.db_manager.get_session() as session:
                for _, row in df.iterrows():
                    try:
                        existing = session.query(MarketBenchmarks).filter(
                            MarketBenchmarks.benchmark == benchmark_name,
                            MarketBenchmarks.date == row['date']
                        ).first()

                        if existing:
                            continue

                        benchmark_record = MarketBenchmarks(
                            benchmark=benchmark_name,
                            date=row['date'],
                            open=float(row['open']),
                            high=float(row['high']),
                            low=float(row['low']),
                            close=float(row['close']),
                            volume=int(row['volume']) if row['volume'] else None
                        )

                        session.add(benchmark_record)
                        records_added += 1

                    except Exception as e:
                        logger.warning(f"Error storing benchmark record: {e}")
                        continue

                session.commit()

            return {
                'success': True,
                'benchmark': benchmark_name,
                'records_added': records_added
            }

        except Exception as e:
            logger.error(f"Error fetching benchmark {benchmark}: {e}")
            return {'success': False, 'error': str(e)}

    def _get_existing_data_range(self, symbol: str) -> Optional[Dict[str, date]]:
        """Get the date range of existing historical data for a symbol."""
        try:
            with self.db_manager.get_session() as session:
                result = session.query(
                    func.min(HistoricalData.date).label('earliest'),
                    func.max(HistoricalData.date).label('latest')
                ).filter(HistoricalData.symbol == symbol).first()

                if result and result.earliest and result.latest:
                    return {'earliest_date': result.earliest, 'latest_date': result.latest}
                return None

        except Exception as e:
            logger.error(f"Error getting existing data range for {symbol}: {e}")
            return None

    def _is_data_sufficient(self, existing_range: Dict[str, date],
                           required_start: date, required_end: date) -> bool:
        """Check if existing data covers the required range sufficiently."""
        earliest = existing_range['earliest_date']
        latest = existing_range['latest_date']

        # Check if we have data covering at least 80% of the required range
        required_days = (required_end - required_start).days
        available_days = (latest - earliest).days

        # Also check if data is recent enough (within last 7 days)
        is_recent = (datetime.now().date() - latest).days <= 7

        coverage_ratio = available_days / max(required_days, 1)

        return coverage_ratio >= 0.8 and is_recent

    def _update_data_quality_metrics(self, symbols: List[str]) -> None:
        """Update data quality metrics for processed symbols."""
        try:
            with self.db_manager.get_session() as session:
                for symbol in symbols:
                    try:
                        # Calculate metrics
                        metrics = self._calculate_data_quality(session, symbol)

                        if not metrics:
                            continue

                        # Update or create quality record
                        quality_record = session.query(DataQualityMetrics).filter(
                            DataQualityMetrics.symbol == symbol
                        ).first()

                        if quality_record:
                            # Update existing
                            for key, value in metrics.items():
                                setattr(quality_record, key, value)
                            quality_record.last_quality_check = datetime.utcnow()
                        else:
                            # Create new
                            quality_record = DataQualityMetrics(
                                symbol=symbol,
                                **metrics,
                                last_quality_check=datetime.utcnow()
                            )
                            session.add(quality_record)

                    except Exception as e:
                        logger.warning(f"Error updating quality metrics for {symbol}: {e}")
                        continue

                session.commit()

        except Exception as e:
            logger.error(f"Error updating data quality metrics: {e}")


    def _calculate_data_quality(self, session, symbol: str) -> Optional[Dict]:
        """Calculate data quality metrics for a symbol."""
        try:
            # Get all historical data for symbol
            data = session.query(HistoricalData).filter(
                HistoricalData.symbol == symbol
            ).order_by(HistoricalData.date).all()

            if len(data) < 10:  # Minimum data points
                return None

            # Calculate metrics
            earliest_date = data[0].date
            latest_date = data[-1].date
            total_days = (latest_date - earliest_date).days + 1
            actual_records = len(data)

            # Estimate expected trading days (excluding weekends, rough estimate)
            expected_trading_days = total_days * 5 / 7  # Rough estimate
            data_completeness = min(100, (actual_records / max(expected_trading_days, 1)) * 100)

            # Check for 200-day and 1-year history
            days_of_data = (datetime.now().date() - earliest_date).days
            has_200_day = days_of_data >= 200
            has_1_year = days_of_data >= 365

            # Price consistency check (no unrealistic gaps)
            price_gaps = []
            for i in range(1, len(data)):
                prev_close = data[i-1].close
                curr_open = data[i].open
                if prev_close and curr_open:
                    gap_pct = abs(curr_open - prev_close) / prev_close * 100
                    price_gaps.append(gap_pct)

            # Score based on reasonable price gaps (< 20% daily moves)
            unrealistic_gaps = sum(1 for gap in price_gaps if gap > 20)
            price_consistency = max(0, 100 - (unrealistic_gaps / max(len(price_gaps), 1)) * 100)

            # Volume consistency (volumes should be > 0 and reasonable)
            valid_volumes = sum(1 for d in data if d.volume and d.volume > 0)
            volume_consistency = (valid_volumes / len(data)) * 100

            # Overall quality score
            overall_score = (data_completeness * 0.4 + price_consistency * 0.3 + volume_consistency * 0.3)

            return {
                'earliest_date': earliest_date,
                'latest_date': latest_date,
                'total_days': actual_records,
                'missing_days': max(0, int(expected_trading_days) - actual_records),
                'data_completeness': round(data_completeness, 2),
                'price_consistency_score': round(price_consistency, 2),
                'volume_consistency_score': round(volume_consistency, 2),
                'overall_quality_score': round(overall_score, 2),
                'has_200_day_history': has_200_day,
                'has_1_year_history': has_1_year,
                'meets_min_quality': overall_score >= 70,
                'last_data_update': datetime.utcnow()
            }

        except Exception as e:
            logger.error(f"Error calculating data quality for {symbol}: {e}")
            return None


# Singleton instance
_historical_data_service = None

def get_historical_data_service() -> HistoricalDataService:
    """Get singleton instance of HistoricalDataService."""
    global _historical_data_service
    if _historical_data_service is None:
        _historical_data_service = HistoricalDataService()
    return _historical_data_service