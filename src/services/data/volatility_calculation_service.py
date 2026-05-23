"""
Volatility Calculation Service

This service calculates volatility metrics (ATR, Beta, Historical Volatility)
for stocks using FYERS historical data and updates them as part of daily sync.
"""

import logging
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

try:
    from ..core.unified_broker_service import get_unified_broker_service
    from src.models.database import get_database_manager
    from src.models.stock_models import Stock
except ImportError:
    from src.services.core.unified_broker_service import get_unified_broker_service
    from src.models.database import get_database_manager
    from src.models.stock_models import Stock


class VolatilityCalculationService:
    """Service to calculate and update volatility metrics for stocks."""

    def __init__(self):
        self.unified_broker_service = get_unified_broker_service()
        self.db_manager = get_database_manager()
        import os
        self.max_workers = int(os.getenv('VOLATILITY_MAX_WORKERS', '3'))
        self.rate_limit_delay = float(os.getenv('VOLATILITY_RATE_LIMIT_DELAY', '0.3'))

    def calculate_volatility_for_stocks(self, user_id: int, stock_symbols: List[str]) -> Dict:
        """
        Calculate volatility metrics for a list of stocks.

        Args:
            user_id: User ID for FYERS API
            stock_symbols: List of stock symbols to process

        Returns:
            Dict with results and statistics
        """
        logger.info(f"Starting volatility calculation for {len(stock_symbols)} stocks")

        results = {
            'processed': 0,
            'updated': 0,
            'failed': 0,
            'start_time': datetime.now(),
            'errors': []
        }

        try:
            # First, get NIFTY 50 data for Beta calculations
            nifty_data = self._fetch_market_data(user_id, 'NSE:NIFTY50-INDEX', days=365)
            if nifty_data is None:
                logger.warning("Could not fetch NIFTY data, Beta calculations will be skipped")

            # Process stocks in batches to avoid overwhelming the API
            batch_size = 20  # Smaller batches for volatility calculations
            batches = [stock_symbols[i:i + batch_size] for i in range(0, len(stock_symbols), batch_size)]

            with self.db_manager.get_session() as session:
                for batch_num, batch in enumerate(batches, 1):
                    logger.info(f"Processing volatility batch {batch_num}/{len(batches)} ({len(batch)} stocks)")

                    batch_results = self._process_volatility_batch(
                        user_id, batch, nifty_data, session
                    )

                    results['processed'] += batch_results['processed']
                    results['updated'] += batch_results['updated']
                    results['failed'] += batch_results['failed']
                    results['errors'].extend(batch_results['errors'])

                    # Rate limiting between batches
                    if batch_num < len(batches):
                        time.sleep(2)

                # Commit all volatility updates
                session.commit()

        except Exception as e:
            logger.error(f"Error in volatility calculation service: {e}")
            results['errors'].append(f"Service error: {str(e)}")

        results['end_time'] = datetime.now()
        results['duration'] = (results['end_time'] - results['start_time']).total_seconds()

        logger.info(f"Volatility calculation completed: {results['updated']}/{results['processed']} stocks updated")
        return results

    def _process_volatility_batch(self, user_id: int, batch_symbols: List[str],
                                 nifty_data: Optional[pd.DataFrame], session) -> Dict:
        """Process a batch of stocks for volatility calculations."""
        batch_results = {
            'processed': 0,
            'updated': 0,
            'failed': 0,
            'errors': []
        }

        for symbol in batch_symbols:
            try:
                batch_results['processed'] += 1

                # Fetch historical data for this stock
                stock_data = self._fetch_market_data(user_id, symbol, days=365)

                if stock_data is None or len(stock_data) < 50:
                    batch_results['failed'] += 1
                    batch_results['errors'].append(f"{symbol}: Insufficient historical data")
                    continue

                # Calculate volatility metrics
                volatility_metrics = self._calculate_all_volatility_metrics(stock_data, nifty_data)

                # Get stock from database
                stock = session.query(Stock).filter_by(symbol=symbol).first()
                if not stock:
                    batch_results['errors'].append(f"{symbol}: Stock not found in database")
                    batch_results['failed'] += 1
                    continue

                # Check if we got valid metrics
                has_valid_metrics = volatility_metrics and any([
                    volatility_metrics.get('atr_14'),
                    volatility_metrics.get('atr_percentage'),
                    volatility_metrics.get('historical_volatility_1y')
                ])

                if has_valid_metrics:
                    # Update with valid data
                    self._update_stock_volatility(stock, volatility_metrics)
                    batch_results['updated'] += 1
                    logger.debug(f"Updated volatility for {symbol}: ATR={volatility_metrics.get('atr_percentage', 'N/A'):.2f}%")
                else:
                    # No valid metrics but update timestamp to mark we checked today
                    # This prevents re-checking on weekends/holidays
                    stock.volatility_last_updated = datetime.now()
                    batch_results['updated'] += 1
                    logger.debug(f"Marked volatility check for {symbol} (no trading data available)")


                # Rate limiting between stocks
                time.sleep(self.rate_limit_delay)

            except Exception as e:
                batch_results['failed'] += 1
                batch_results['errors'].append(f"{symbol}: {str(e)}")
                logger.error(f"Error processing {symbol}: {e}")

        return batch_results

    def _fetch_market_data(self, user_id: int, symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
        """Fetch historical market data for a symbol from stored historical data."""
        try:
            # Import here to avoid circular imports
            from ...models.historical_models import HistoricalData

            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            with self.db_manager.get_session() as session:
                # Query historical data from database
                historical_records = session.query(HistoricalData).filter(
                    HistoricalData.symbol == symbol,
                    HistoricalData.date >= start_date,
                    HistoricalData.date <= end_date
                ).order_by(HistoricalData.date).all()

                if not historical_records:
                    logger.warning(f"No historical data found for {symbol} in database")
                    return None

                # Convert to DataFrame
                data = []
                for record in historical_records:
                    data.append({
                        'date': record.date,
                        'open': float(record.open),
                        'high': float(record.high),
                        'low': float(record.low),
                        'close': float(record.close),
                        'volume': int(record.volume)
                    })

                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')

                # Validate data quality
                if len(df) < 30:  # Need at least 30 days for meaningful volatility calculation
                    logger.warning(f"Insufficient historical data for {symbol}: only {len(df)} records")
                    return None

                logger.info(f"📊 Retrieved {len(df)} days of historical data for {symbol} from database")
                return df

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol} from database: {e}")
            return None

    def _calculate_all_volatility_metrics(self, stock_data: pd.DataFrame,
                                        nifty_data: Optional[pd.DataFrame] = None) -> Dict:
        """Calculate all volatility metrics for a stock."""
        metrics = {
            'atr_14': None,
            'atr_percentage': None,
            'beta': None,
            'historical_volatility_1y': None,
            'bid_ask_spread': None,
            'avg_daily_volume_20d': None,
            'avg_daily_turnover': None,
            'trades_per_day': None
        }

        try:
            # Calculate ATR
            metrics['atr_14'] = self._calculate_atr(stock_data.copy(), 14)
            metrics['atr_percentage'] = self._calculate_atr_percentage(stock_data.copy(), 14)

            # Calculate Historical Volatility
            metrics['historical_volatility_1y'] = self._calculate_historical_volatility(stock_data.copy(), 252)

            # Calculate average volume (20-day)
            if len(stock_data) >= 20:
                metrics['avg_daily_volume_20d'] = stock_data['volume'].tail(20).mean()

            # Calculate average daily turnover (volume * price)
            if len(stock_data) >= 20:
                turnover = stock_data['volume'] * stock_data['close']
                metrics['avg_daily_turnover'] = turnover.tail(20).mean() / 10000000  # Convert to crores

            # Estimate trades per day (simplified based on volume)
            if len(stock_data) >= 20:
                avg_volume = stock_data['volume'].tail(20).mean()
                # Rough estimate: assume average trade size is 100 shares
                metrics['trades_per_day'] = int(avg_volume / 100) if avg_volume > 0 else None

            # Calculate Beta (if NIFTY data is available)
            if nifty_data is not None and len(nifty_data) > 50:
                metrics['beta'] = self._calculate_beta(
                    stock_data['close'],
                    nifty_data['close'],
                    min(252, len(stock_data), len(nifty_data))
                )

            # Bid-ask spread calculation would require level 2 data (not available from historical)
            # For now, we'll estimate it based on price volatility
            metrics['bid_ask_spread'] = self._estimate_bid_ask_spread(stock_data.copy())

        except Exception as e:
            logger.error(f"Error calculating volatility metrics: {e}")

        return metrics

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Average True Range (ATR)."""
        if len(df) < period + 1:
            return None

        try:
            # Calculate True Range
            df['high_low'] = df['high'] - df['low']
            df['high_close_prev'] = abs(df['high'] - df['close'].shift(1))
            df['low_close_prev'] = abs(df['low'] - df['close'].shift(1))

            df['true_range'] = df[['high_low', 'high_close_prev', 'low_close_prev']].max(axis=1)

            # Calculate ATR
            atr = df['true_range'].rolling(window=period).mean().iloc[-1]
            return float(atr) if not pd.isna(atr) else None

        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None

    def _calculate_atr_percentage(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate ATR as percentage of current price."""
        atr = self._calculate_atr(df, period)
        if atr is None or len(df) == 0:
            return None

        try:
            current_price = df['close'].iloc[-1]
            if current_price > 0:
                return (atr / current_price) * 100
        except Exception as e:
            logger.error(f"Error calculating ATR percentage: {e}")

        return None

    def _calculate_beta(self, stock_prices: pd.Series, market_prices: pd.Series, period: int = 252) -> Optional[float]:
        """Calculate Beta using correlation with market (NIFTY 50)."""
        if len(stock_prices) < period or len(market_prices) < period:
            return None

        try:
            # Calculate returns
            stock_returns = stock_prices.pct_change().dropna()
            market_returns = market_prices.pct_change().dropna()

            # Align data
            min_len = min(len(stock_returns), len(market_returns))
            if min_len < 50:  # Need at least 50 data points
                return None

            stock_returns = stock_returns.tail(min_len)
            market_returns = market_returns.tail(min_len)

            # Calculate beta
            covariance = np.cov(stock_returns, market_returns)[0][1]
            market_variance = np.var(market_returns)

            if market_variance > 0:
                beta = covariance / market_variance
                return float(beta)
        except Exception as e:
            logger.error(f"Error calculating Beta: {e}")

        return None

    def _calculate_historical_volatility(self, df: pd.DataFrame, period: int = 252) -> Optional[float]:
        """Calculate annualized historical volatility."""
        if len(df) < 30:  # Need at least 30 data points for basic calculation
            return None

        try:
            # Calculate daily returns
            returns = df['close'].pct_change().dropna()

            if len(returns) < 30:  # Need at least 30 data points for volatility
                return None

            # Use available data up to the period limit
            actual_period = min(len(returns), period)
            if actual_period > 30:
                returns = returns.tail(actual_period)

            # Calculate volatility (annualized)
            volatility = returns.std() * np.sqrt(252) * 100  # Convert to percentage
            return float(volatility) if not pd.isna(volatility) else None

        except Exception as e:
            logger.error(f"Error calculating historical volatility: {e}")
            return None

    def _estimate_bid_ask_spread(self, df: pd.DataFrame) -> Optional[float]:
        """Estimate bid-ask spread based on price volatility."""
        if len(df) < 20:
            return None

        try:
            # Simple estimation: use intraday range as proxy for spread
            recent_data = df.tail(20)
            avg_range = (recent_data['high'] - recent_data['low']).mean()
            avg_price = recent_data['close'].mean()

            if avg_price > 0:
                estimated_spread = (avg_range / avg_price) * 100 * 0.3  # Conservative estimate
                return float(estimated_spread)
        except Exception as e:
            logger.error(f"Error estimating bid-ask spread: {e}")

        return None

    def _update_stock_volatility(self, stock: Stock, metrics: Dict):
        """Update stock object with volatility metrics."""
        try:
            stock.atr_14 = metrics.get('atr_14')
            stock.atr_percentage = metrics.get('atr_percentage')
            stock.beta = metrics.get('beta')
            stock.historical_volatility_1y = metrics.get('historical_volatility_1y')
            stock.bid_ask_spread = metrics.get('bid_ask_spread')
            stock.avg_daily_volume_20d = metrics.get('avg_daily_volume_20d')
            stock.avg_daily_turnover = metrics.get('avg_daily_turnover')
            stock.trades_per_day = metrics.get('trades_per_day')

            # Update the volatility_last_updated timestamp for volatility tracking
            stock.volatility_last_updated = datetime.now()

        except Exception as e:
            logger.error(f"Error updating stock volatility: {e}")
            raise


def get_volatility_calculation_service():
    """Get singleton instance of VolatilityCalculationService."""
    if not hasattr(get_volatility_calculation_service, '_instance'):
        get_volatility_calculation_service._instance = VolatilityCalculationService()
    return get_volatility_calculation_service._instance