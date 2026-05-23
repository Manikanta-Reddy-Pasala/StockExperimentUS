"""
Technical Indicators Service
Calculates comprehensive technical indicators using historical OHLCV data
Supports 20+ indicators for enhanced stock filtering and analysis
"""

import logging
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta, date
import time
from sqlalchemy import and_, desc, func

logger = logging.getLogger(__name__)

try:
    from ...models.database import get_database_manager
    from ...models.historical_models import HistoricalData, TechnicalIndicators
    from ...models.stock_models import Stock
except ImportError:
    from src.models.database import get_database_manager
    from src.models.historical_models import HistoricalData, TechnicalIndicators
    from src.models.stock_models import Stock


class TechnicalIndicatorsService:
    """Service to calculate and manage technical indicators from historical data."""

    def __init__(self):
        self.db_manager = get_database_manager()
        self.min_data_points = 200  # Minimum historical points for reliable indicators

    def calculate_indicators_bulk(self, symbols: List[str] = None, max_symbols: int = 100) -> Dict[str, Any]:
        """
        Calculate technical indicators for multiple symbols.

        Args:
            symbols: List of symbols to process (None = auto-select)
            max_symbols: Maximum number of symbols to process

        Returns:
            Dict with calculation results and statistics
        """
        start_time = time.time()

        try:
            if not symbols:
                symbols = self._get_symbols_needing_indicators(max_symbols)

            if not symbols:
                return {
                    'success': True,
                    'processed': 0,
                    'successful': 0,
                    'message': 'No symbols need indicator calculation'
                }

            logger.info(f"📊 Calculating indicators for {len(symbols)} symbols")

            results = {'processed': 0, 'successful': 0, 'failed': 0, 'errors': []}

            for symbol in symbols:
                try:
                    result = self.calculate_indicators_single(symbol)
                    results['processed'] += 1

                    if result.get('success'):
                        results['successful'] += 1
                        logger.info(f"✅ {symbol}: {result.get('indicators_calculated', 0)} indicators")
                    else:
                        results['failed'] += 1
                        results['errors'].append(f"{symbol}: {result.get('error', 'Unknown error')}")

                except Exception as e:
                    logger.error(f"Error calculating indicators for {symbol}: {e}")
                    results['processed'] += 1
                    results['failed'] += 1
                    results['errors'].append(f"{symbol}: {str(e)}")

            duration = time.time() - start_time

            return {
                'success': True,
                'processed': results['processed'],
                'successful': results['successful'],
                'failed': results['failed'],
                'duration_seconds': duration,
                'message': f"Processed {results['processed']} symbols with {results['successful']} successful calculations",
                'errors': results['errors'][:10]  # Limit error list
            }

        except Exception as e:
            logger.error(f"Error in bulk indicator calculation: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def calculate_indicators_single(self, symbol: str) -> Dict[str, Any]:
        """
        Calculate technical indicators for a single symbol.

        Args:
            symbol: Stock symbol to process

        Returns:
            Dict with calculation results
        """
        try:
            logger.info(f"📈 Calculating indicators for {symbol}")

            # Get historical data
            historical_data = self._get_historical_data(symbol)

            if historical_data is None or len(historical_data) < self.min_data_points:
                return {
                    'success': False,
                    'symbol': symbol,
                    'error': f'Insufficient data: {len(historical_data) if historical_data is not None else 0} points'
                }

            # Calculate all indicators
            indicators = self._calculate_all_indicators(historical_data)

            # Store in database
            records_stored = self._store_indicators(symbol, indicators)

            return {
                'success': True,
                'symbol': symbol,
                'data_points': len(historical_data),
                'indicators_calculated': len(indicators),
                'records_stored': records_stored
            }

        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            return {
                'success': False,
                'symbol': symbol,
                'error': str(e)
            }

    def _get_symbols_needing_indicators(self, max_symbols: int) -> List[str]:
        """Get symbols that need indicator calculation."""
        try:
            with self.db_manager.get_session() as session:
                # Get symbols with sufficient historical data but missing indicators
                subquery = session.query(HistoricalData.symbol).filter(
                    HistoricalData.date >= datetime.now().date() - timedelta(days=365)
                ).group_by(HistoricalData.symbol).having(
                    func.count(HistoricalData.id) >= self.min_data_points
                ).subquery()

                # Exclude symbols that already have recent indicators
                existing_indicators = session.query(TechnicalIndicators.symbol).filter(
                    TechnicalIndicators.date >= datetime.now().date() - timedelta(days=7)
                ).distinct().subquery()

                symbols = session.query(subquery.c.symbol).filter(
                    ~subquery.c.symbol.in_(existing_indicators)
                ).limit(max_symbols).all()

                return [symbol[0] for symbol in symbols]

        except Exception as e:
            logger.error(f"Error getting symbols needing indicators: {e}")
            return []

    def _get_historical_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get historical data for a symbol."""
        try:
            with self.db_manager.get_session() as session:
                # Get last 500 trading days (about 2 years)
                cutoff_date = datetime.now().date() - timedelta(days=700)

                data = session.query(HistoricalData).filter(
                    HistoricalData.symbol == symbol,
                    HistoricalData.date >= cutoff_date
                ).order_by(HistoricalData.date.asc()).all()

                if not data:
                    return None

                # Convert to DataFrame
                df = pd.DataFrame([{
                    'date': record.date,
                    'open': float(record.open),
                    'high': float(record.high),
                    'low': float(record.low),
                    'close': float(record.close),
                    'volume': int(record.volume)
                } for record in data])

                return df

        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return None

    def _calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate daily SMA 50/200 — used as the HTF gate for the EMA 200/400 1H strategy."""
        indicators = df.copy()
        indicators['sma_50'] = df['close'].rolling(window=50).mean()
        indicators['sma_200'] = df['close'].rolling(window=200).mean()
        indicators['data_points_used'] = len(df)
        return indicators

    def _store_indicators(self, symbol: str, indicators_df: pd.DataFrame) -> int:
        """Store calculated indicators in database."""
        try:
            records_stored = 0

            with self.db_manager.get_session() as session:
                # Only store the last 90 days of indicators
                recent_df = indicators_df.tail(90)

                for _, row in recent_df.iterrows():
                    try:
                        # Use merge to handle insert/update automatically
                        # First, check if record exists
                        existing = session.query(TechnicalIndicators).filter(
                            TechnicalIndicators.symbol == symbol,
                            TechnicalIndicators.date == row['date']
                        ).first()

                        if existing:
                            for column in ['sma_50', 'sma_200']:
                                if column in row and pd.notna(row[column]):
                                    setattr(existing, column, float(row[column]))
                            existing.data_points_used = int(row['data_points_used'])
                            existing.calculation_date = datetime.utcnow()
                            records_stored += 1
                        else:
                            try:
                                indicator_record = TechnicalIndicators(
                                    symbol=symbol,
                                    date=row['date'],
                                    sma_50=float(row['sma_50']) if 'sma_50' in row and pd.notna(row['sma_50']) else None,
                                    sma_200=float(row['sma_200']) if 'sma_200' in row and pd.notna(row['sma_200']) else None,
                                    data_points_used=int(row['data_points_used']),
                                    calculation_date=datetime.utcnow()
                                )
                                session.add(indicator_record)
                                session.flush()  # Flush to catch unique constraint violations early
                                records_stored += 1
                            except Exception as inner_e:
                                # If unique constraint violation, skip silently (race condition)
                                if 'duplicate key' in str(inner_e).lower() or 'unique constraint' in str(inner_e).lower():
                                    session.rollback()
                                    logger.debug(f"Record already exists for {symbol} on {row['date']} (race condition)")
                                else:
                                    raise

                    except Exception as e:
                        # Rollback the current transaction to recover from error
                        session.rollback()
                        logger.warning(f"Error storing indicator record for {symbol} on {row['date']}: {e}")
                        continue

                # Commit all changes at once
                try:
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.error(f"Error committing indicators for {symbol}: {e}")
                    return 0

            return records_stored

        except Exception as e:
            logger.error(f"Error storing indicators for {symbol}: {e}")
            return 0

    def get_latest_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the latest calculated indicators for a symbol."""
        try:
            with self.db_manager.get_session() as session:
                latest = session.query(TechnicalIndicators).filter(
                    TechnicalIndicators.symbol == symbol
                ).order_by(TechnicalIndicators.date.desc()).first()

                if not latest:
                    return None

                return {
                    'symbol': latest.symbol,
                    'date': latest.date,
                    'sma_50': latest.sma_50,
                    'sma_200': latest.sma_200,
                    'data_points_used': latest.data_points_used,
                    'calculation_date': latest.calculation_date,
                }

        except Exception as e:
            logger.error(f"Error getting latest indicators for {symbol}: {e}")
            return None