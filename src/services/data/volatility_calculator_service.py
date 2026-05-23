"""
FYERS v3 API Volatility Calculator Service

Calculates real volatility metrics using FYERS v3 Historical and Quotes APIs:
- ATR (Average True Range) and ATR%
- Beta vs market index
- Historical volatility (standard deviation of returns)
- Volume and liquidity metrics
"""

import logging
import math
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from ..brokers.fyers_service import get_fyers_service

logger = logging.getLogger(__name__)


class VolatilityCalculatorService:
    """Service to calculate real volatility metrics from FYERS v3 API data."""

    def __init__(self):
        self.fyers_service = get_fyers_service()

    def calculate_stock_volatility_metrics(self, user_id: int, symbol: str,
                                         days_lookback: int = 252) -> Dict[str, Any]:
        """
        Calculate comprehensive volatility metrics for a single stock.

        Args:
            user_id: User ID for FYERS API
            symbol: Stock symbol (e.g., 'NSE:RELIANCE-EQ')
            days_lookback: Number of trading days to analyze (default: 252 = 1 year)

        Returns:
            Dict with calculated metrics or None if data unavailable
        """
        try:
            # Get historical data from FYERS v3 History API
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_lookback + 30)  # Extra buffer for holidays

            historical_data = self._get_historical_data(
                user_id, symbol, start_date, end_date
            )

            if not historical_data or len(historical_data) < 30:  # Need minimum data
                logger.warning(f"Insufficient historical data for {symbol}: {len(historical_data) if historical_data else 0} days")
                return None

            # Calculate all volatility metrics
            metrics = {}

            # 1. ATR and ATR%
            atr_metrics = self._calculate_atr(historical_data)
            if atr_metrics:
                metrics.update(atr_metrics)

            # 2. Historical Volatility (annualized)
            hist_vol = self._calculate_historical_volatility(historical_data)
            if hist_vol:
                metrics['historical_volatility_1y'] = hist_vol

            # 3. Beta vs NIFTY50
            beta = self._calculate_beta_vs_nifty(user_id, symbol, historical_data, days_lookback)
            if beta:
                metrics['beta'] = beta

            # 4. Volume metrics
            volume_metrics = self._calculate_volume_metrics(historical_data)
            if volume_metrics:
                metrics.update(volume_metrics)

            # 5. Current price and liquidity from Quotes API
            current_metrics = self._get_current_liquidity_metrics(user_id, symbol)
            if current_metrics:
                metrics.update(current_metrics)

            logger.info(f"✅ Calculated volatility metrics for {symbol}: {list(metrics.keys())}")
            return metrics

        except Exception as e:
            logger.error(f"Error calculating volatility metrics for {symbol}: {e}")
            return None

    def calculate_batch_volatility_metrics(self, user_id: int, symbols: List[str],
                                         max_symbols: int = 20) -> Dict[str, Dict[str, Any]]:
        """
        Calculate volatility metrics for multiple stocks in batch.

        Args:
            user_id: User ID for FYERS API
            symbols: List of stock symbols
            max_symbols: Maximum symbols to process (API rate limiting)

        Returns:
            Dict mapping symbol to metrics dict
        """
        results = {}
        processed = 0

        logger.info(f"📊 Starting batch volatility calculation for {len(symbols)} symbols (max: {max_symbols})")

        for symbol in symbols:
            if processed >= max_symbols:
                logger.info(f"⏹️ Reached max symbols limit ({max_symbols}), stopping batch processing")
                break

            try:
                metrics = self.calculate_stock_volatility_metrics(user_id, symbol)
                if metrics:
                    results[symbol] = metrics
                    processed += 1

                    if processed % 5 == 0:  # Progress logging
                        logger.info(f"📈 Processed {processed}/{min(len(symbols), max_symbols)} symbols")

                # Fyers API limit: 10 req/s, using 0.2s for safe margin (5 req/s)
                import time
                time.sleep(0.2)

            except Exception as e:
                logger.warning(f"Failed to process {symbol}: {e}")
                continue

        logger.info(f"✅ Batch processing complete: {len(results)} symbols with metrics")
        return results

    def _get_historical_data(self, user_id: int, symbol: str,
                           start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get historical OHLCV data from FYERS History API."""
        try:
            # Use FYERS service to get historical data
            response = self.fyers_service.get_historical_data(
                user_id=user_id,
                symbol=symbol,
                resolution='D',  # Daily resolution
                range_from=start_date.strftime('%Y-%m-%d'),
                range_to=end_date.strftime('%Y-%m-%d')
            )

            if not response.get('success') or not response.get('data'):
                logger.warning(f"No historical data returned for {symbol}")
                return []

            candles = response['data'].get('candles', [])

            # Convert to standard format: [timestamp, open, high, low, close, volume]
            historical_data = []
            for candle in candles:
                if len(candle) >= 6:  # Ensure we have OHLCV data
                    historical_data.append({
                        'timestamp': candle[0],
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': int(candle[5]) if candle[5] else 0
                    })

            logger.debug(f"Retrieved {len(historical_data)} historical data points for {symbol}")
            return historical_data

        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return []

    def _calculate_atr(self, historical_data: List[Dict], period: int = 14) -> Optional[Dict[str, float]]:
        """Calculate Average True Range (ATR) and ATR%."""
        try:
            if len(historical_data) < period + 1:
                return None

            true_ranges = []

            for i in range(1, len(historical_data)):
                current = historical_data[i]
                previous = historical_data[i-1]

                # True Range = max(high-low, |high-prev_close|, |low-prev_close|)
                tr1 = current['high'] - current['low']
                tr2 = abs(current['high'] - previous['close'])
                tr3 = abs(current['low'] - previous['close'])

                true_range = max(tr1, tr2, tr3)
                true_ranges.append(true_range)

            if len(true_ranges) < period:
                return None

            # Calculate ATR as simple moving average of True Ranges
            atr_values = []
            for i in range(period-1, len(true_ranges)):
                atr = sum(true_ranges[i-period+1:i+1]) / period
                atr_values.append(atr)

            if not atr_values:
                return None

            # Use latest ATR value
            latest_atr = atr_values[-1]
            latest_close = historical_data[-1]['close']

            # Calculate ATR as percentage of price
            atr_percentage = (latest_atr / latest_close) * 100

            return {
                'atr_14': round(latest_atr, 4),
                'atr_percentage': round(atr_percentage, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None

    def _calculate_historical_volatility(self, historical_data: List[Dict]) -> Optional[float]:
        """Calculate annualized historical volatility (standard deviation of returns)."""
        try:
            if len(historical_data) < 30:  # Need minimum data
                return None

            # Calculate daily returns
            daily_returns = []
            for i in range(1, len(historical_data)):
                prev_close = historical_data[i-1]['close']
                curr_close = historical_data[i]['close']

                if prev_close > 0:
                    daily_return = (curr_close - prev_close) / prev_close
                    daily_returns.append(daily_return)

            if len(daily_returns) < 30:
                return None

            # Calculate standard deviation
            daily_volatility = statistics.stdev(daily_returns)

            # Annualize volatility (assuming 252 trading days per year)
            annualized_volatility = daily_volatility * math.sqrt(252) * 100  # Convert to percentage

            return round(annualized_volatility, 2)

        except Exception as e:
            logger.error(f"Error calculating historical volatility: {e}")
            return None

    def _calculate_beta_vs_nifty(self, user_id: int, symbol: str,
                               stock_data: List[Dict], days_lookback: int) -> Optional[float]:
        """Calculate Beta coefficient vs NIFTY50 index."""
        try:
            # Get NIFTY50 historical data for the same period
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_lookback + 30)

            # NIFTY50 symbol in FYERS format
            nifty_symbol = "NSE:NIFTY50-INDEX"

            nifty_data = self._get_historical_data(user_id, nifty_symbol, start_date, end_date)

            if not nifty_data or len(nifty_data) < 30:
                logger.warning(f"Insufficient NIFTY data for beta calculation: {len(nifty_data) if nifty_data else 0} days")
                return None

            # Align dates and calculate returns
            stock_returns, nifty_returns = self._align_and_calculate_returns(stock_data, nifty_data)

            if len(stock_returns) < 30 or len(nifty_returns) < 30:
                return None

            # Calculate beta using covariance/variance formula
            # Beta = Cov(stock, market) / Var(market)

            if len(stock_returns) != len(nifty_returns):
                min_len = min(len(stock_returns), len(nifty_returns))
                stock_returns = stock_returns[-min_len:]
                nifty_returns = nifty_returns[-min_len:]

            # Calculate covariance and variance
            stock_mean = statistics.mean(stock_returns)
            nifty_mean = statistics.mean(nifty_returns)

            covariance = sum((s - stock_mean) * (n - nifty_mean)
                           for s, n in zip(stock_returns, nifty_returns)) / len(stock_returns)

            nifty_variance = statistics.variance(nifty_returns)

            if nifty_variance == 0:
                return None

            beta = covariance / nifty_variance

            return round(beta, 3)

        except Exception as e:
            logger.error(f"Error calculating beta for {symbol}: {e}")
            return None

    def _align_and_calculate_returns(self, stock_data: List[Dict],
                                   index_data: List[Dict]) -> Tuple[List[float], List[float]]:
        """Align stock and index data by date and calculate returns."""
        # Create date-indexed dictionaries
        stock_by_date = {data['timestamp']: data['close'] for data in stock_data}
        index_by_date = {data['timestamp']: data['close'] for data in index_data}

        # Find common dates
        common_dates = sorted(set(stock_by_date.keys()) & set(index_by_date.keys()))

        if len(common_dates) < 2:
            return [], []

        # Calculate aligned returns
        stock_returns = []
        index_returns = []

        for i in range(1, len(common_dates)):
            prev_date = common_dates[i-1]
            curr_date = common_dates[i]

            # Stock return
            stock_prev = stock_by_date[prev_date]
            stock_curr = stock_by_date[curr_date]
            if stock_prev > 0:
                stock_return = (stock_curr - stock_prev) / stock_prev
                stock_returns.append(stock_return)

                # Index return
                index_prev = index_by_date[prev_date]
                index_curr = index_by_date[curr_date]
                if index_prev > 0:
                    index_return = (index_curr - index_prev) / index_prev
                    index_returns.append(index_return)
                else:
                    # Remove the corresponding stock return if index data is invalid
                    stock_returns.pop()

        return stock_returns, index_returns

    def _calculate_volume_metrics(self, historical_data: List[Dict]) -> Dict[str, float]:
        """Calculate volume-based liquidity metrics."""
        try:
            if len(historical_data) < 20:
                return {}

            # Calculate 20-day average volume
            recent_volumes = [data['volume'] for data in historical_data[-20:] if data['volume'] > 0]

            if not recent_volumes:
                return {}

            avg_volume_20d = sum(recent_volumes) / len(recent_volumes)

            # Calculate average daily turnover (price * volume) in crores
            recent_turnovers = []
            for data in historical_data[-20:]:
                if data['volume'] > 0 and data['close'] > 0:
                    turnover_crores = (data['close'] * data['volume']) / 10000000  # Convert to crores
                    recent_turnovers.append(turnover_crores)

            avg_turnover = sum(recent_turnovers) / len(recent_turnovers) if recent_turnovers else 0

            return {
                'avg_daily_volume_20d': int(avg_volume_20d),
                'avg_daily_turnover': round(avg_turnover, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating volume metrics: {e}")
            return {}

    def _get_current_liquidity_metrics(self, user_id: int, symbol: str) -> Dict[str, Any]:
        """Get current price and liquidity metrics from FYERS Quotes API."""
        try:
            # Get current quote
            quotes_response = self.fyers_service.quotes(user_id, [symbol])

            if not quotes_response.get('success') or not quotes_response.get('data'):
                return {}

            quote_data = quotes_response['data'].get(symbol)
            if not quote_data or not quote_data.get('v'):
                return {}

            quote = quote_data['v']

            # Get market depth for bid-ask spread
            depth_response = self.fyers_service.get_market_depth(user_id, symbol)

            metrics = {
                'current_price': float(quote.get('lp', 0)),  # Last traded price
                'current_volume': int(quote.get('volume', 0)),
                'current_change_percent': float(quote.get('chp', 0))
            }

            # Calculate bid-ask spread if depth data available
            if depth_response.get('success') and depth_response.get('data'):
                depth_data = depth_response['data'].get(symbol)
                if depth_data:
                    bids = depth_data.get('bids', [])
                    asks = depth_data.get('asks', [])

                    if bids and asks:
                        best_bid = float(bids[0].get('price', 0))
                        best_ask = float(asks[0].get('price', 0))

                        if best_bid > 0 and best_ask > 0:
                            spread_percent = ((best_ask - best_bid) / best_bid) * 100
                            metrics['bid_ask_spread'] = round(spread_percent, 3)

            return metrics

        except Exception as e:
            logger.error(f"Error getting current liquidity metrics for {symbol}: {e}")
            return {}


# Singleton service
_volatility_calculator_service = None

def get_volatility_calculator_service() -> VolatilityCalculatorService:
    """Get singleton instance of VolatilityCalculatorService."""
    global _volatility_calculator_service
    if _volatility_calculator_service is None:
        _volatility_calculator_service = VolatilityCalculatorService()
    return _volatility_calculator_service