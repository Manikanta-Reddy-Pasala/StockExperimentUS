"""
Enhanced FYERS Dashboard Provider Implementation

Uses the official FYERS API library for full feature implementation.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from ..interfaces.dashboard_interface import IDashboardProvider, DashboardMetrics, MarketIndex
from ..brokers.fyers_service import get_fyers_service

logger = logging.getLogger(__name__)


class FyersDashboardProvider(IDashboardProvider):
    """Enhanced FYERS implementation of dashboard provider with full API integration."""
    
    def __init__(self):
        self.fyers_service = get_fyers_service()
        self.broker_name = 'fyers'
    
    def get_market_overview(self, user_id: int) -> Dict[str, Any]:
        """Get market overview data using real Fyers API data or fallback to DB data."""
        try:
            # Try to get real positions data
            positions_response = self.fyers_service.positions(user_id)
            market_indices = []

            # Check if API authentication failed
            if positions_response.get('status') == 'error' and positions_response.get('error_code') == -16:
                # Fallback: Show top suggested stocks from database as market overview
                return self._get_market_overview_from_db(user_id)

            if positions_response.get('status') == 'success':
                net_positions = positions_response.get('data', [])

                # Use real data from positions - show actual holdings as market overview
                for position in net_positions:
                    symbol = position.get('symbol', '')
                    ltp = position.get('ltp', 0)
                    # Calculate change based on buy price vs current price
                    buy_avg = position.get('buyAvg', ltp)
                    change = ltp - buy_avg
                    change_percent = (change / buy_avg * 100) if buy_avg > 0 else 0

                    index = MarketIndex(
                        symbol=symbol,
                        name=symbol.replace('NSE:', '').replace('-EQ', ''),
                        price=float(ltp),
                        change=float(change),
                        change_percent=float(change_percent)
                    )
                    market_indices.append(index.to_dict())

            # If no positions, try to get holdings data
            if not market_indices:
                holdings_response = self.fyers_service.holdings(user_id)
                if holdings_response.get('status') == 'success':
                    holdings = holdings_response.get('data', [])

                    for holding in holdings:
                        symbol = holding.get('symbol', '')
                        ltp = holding.get('ltp', 0)
                        costPrice = holding.get('costPrice', ltp)
                        change = ltp - costPrice
                        change_percent = (change / costPrice * 100) if costPrice > 0 else 0

                        index = MarketIndex(
                            symbol=symbol,
                            name=symbol.replace('NSE:', '').replace('-EQ', ''),
                            price=float(ltp),
                            change=float(change),
                            change_percent=float(change_percent)
                        )
                        market_indices.append(index.to_dict())

            # If still no data, return empty with appropriate message
            if not market_indices:
                return {
                    'success': True,
                    'data': [],
                    'message': 'No market data available. Please add some positions or holdings to view market overview.',
                    'last_updated': datetime.now().isoformat()
                }

            return {
                'success': True,
                'data': market_indices,
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching market overview for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'last_updated': datetime.now().isoformat()
            }

    def _get_market_overview_from_db(self, user_id: int) -> Dict[str, Any]:
        """Fallback method to get market overview from suggested stocks in database."""
        try:
            from ...models.database import get_database_manager
            from sqlalchemy import text

            db_manager = get_database_manager()
            market_indices = []

            with db_manager.get_session() as session:
                # Get top 5 suggested stocks from latest date using raw SQL
                query = text("""
                    SELECT symbol, stock_name, current_price, selection_score
                    FROM daily_suggested_stocks
                    WHERE date = (SELECT MAX(date) FROM daily_suggested_stocks)
                    AND current_price IS NOT NULL
                    ORDER BY selection_score DESC
                    LIMIT 5
                """)
                result = session.execute(query)
                latest_stocks = result.fetchall()

                for stock in latest_stocks:
                    symbol, stock_name, current_price, selection_score = stock
                    # No historical data available - show current price only
                    market_indices.append({
                        'symbol': symbol,
                        'name': stock_name or symbol.replace('NSE:', '').replace('-EQ', ''),
                        'price': float(current_price or 0),
                        'change': 0.0,
                        'change_percent': 0.0
                    })

            return {
                'success': True,
                'data': market_indices,
                'message': 'Showing top suggested stocks (Fyers API not authenticated)',
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching market overview from DB: {str(e)}")
            return {
                'success': True,
                'data': [],
                'message': 'No market data available. Please configure Fyers API credentials.',
                'last_updated': datetime.now().isoformat()
            }

    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        """Get portfolio summary metrics using real FYERS API data or fallback."""
        try:
            # Get real data from multiple API endpoints
            funds_response = self.fyers_service.funds(user_id)

            # Check if API authentication failed
            if funds_response.get('status') == 'error' and funds_response.get('error_code') == -16:
                # Return empty portfolio with message
                return {
                    'success': True,
                    'data': {
                        'total_value': 0.0,
                        'available_cash': 0.0,
                        'invested_amount': 0.0,
                        'total_pnl': 0.0,
                        'total_pnl_percent': 0.0,
                        'day_pnl': 0.0,
                        'day_pnl_percent': 0.0,
                        'positions_count': 0,
                        'holdings_count': 0
                    },
                    'message': 'Portfolio data unavailable. Please configure Fyers API credentials in .env file.',
                    'last_updated': datetime.now().isoformat()
                }

            positions_response = self.fyers_service.positions(user_id)
            holdings_response = self.fyers_service.holdings(user_id)

            metrics = DashboardMetrics()

            # Get funds data
            if funds_response.get('status') == 'success':
                fund_data = funds_response.get('data', {})

                # Extract funds from standardized format
                if isinstance(fund_data, dict):
                    metrics.available_cash = float(fund_data.get('available_cash', 0))
                    total_balance = float(fund_data.get('total_margin', 0))
                else:
                    # Fallback for list format
                    for fund in fund_data:
                        if fund.get('title') == 'Available Balance':
                            metrics.available_cash = fund.get('equityAmount', 0)
                        elif fund.get('title') == 'Total Balance':
                            total_balance = fund.get('equityAmount', 0)

            # Get positions data
            total_positions_value = 0
            total_positions_pnl = 0
            if positions_response.get('status') == 'success':
                net_positions = positions_response.get('data', [])
                # Note: overall data is not available in standardized format, calculate manually
                overall_pnl = sum(float(pos.get('pnl', 0)) for pos in net_positions)

                metrics.positions_count = len(net_positions)
                total_positions_pnl = overall_pnl

                # Calculate total positions value using standardized field names
                for position in net_positions:
                    ltp = float(position.get('last_price', 0))
                    qty = float(position.get('quantity', 0))
                    total_positions_value += ltp * qty

            # Get holdings data
            total_holdings_value = 0
            total_holdings_pnl = 0
            if holdings_response.get('status') == 'success':
                holdings = holdings_response.get('data', [])
                # Calculate holdings metrics manually
                total_holdings_pnl = sum(float(h.get('pnl', 0)) for h in holdings)

                metrics.holdings_count = len(holdings)

                # Calculate total holdings value
                for holding in holdings:
                    market_val = holding.get('marketVal', 0)
                    total_holdings_value += float(market_val) if market_val else 0

            # Calculate summary metrics
            metrics.total_portfolio_value = total_positions_value + total_holdings_value
            metrics.total_pnl = total_positions_pnl + total_holdings_pnl
            metrics.daily_pnl = total_positions_pnl  # Using positions PnL as daily PnL

            # Calculate percentage values
            if metrics.total_portfolio_value > 0:
                metrics.total_pnl_percent = (metrics.total_pnl / metrics.total_portfolio_value) * 100
                metrics.daily_pnl_percent = (metrics.daily_pnl / metrics.total_portfolio_value) * 100

            return {
                'success': True,
                'data': metrics.to_dict(),
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching portfolio summary for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': DashboardMetrics().to_dict(),
                'last_updated': datetime.now().isoformat()
            }
    
    def get_top_holdings(self, user_id: int, limit: int = 5) -> Dict[str, Any]:
        """Get top holdings by value using FYERS API."""
        try:
            holdings_response = self.fyers_service.holdings(user_id)
            
            if holdings_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': holdings_response.get('message', 'Failed to fetch holdings'),
                    'data': [],
                    'last_updated': datetime.now().isoformat()
                }
            
            holdings = holdings_response.get('data', [])[:limit]
            
            # Format for dashboard display
            top_holdings = []
            for holding in holdings:
                top_holdings.append({
                    'symbol': holding.get('symbol', ''),
                    'symbol_name': holding.get('symbol_name', ''),
                    'quantity': holding.get('quantity', 0),
                    'current_value': holding.get('market_value', 0),
                    'pnl': holding.get('pnl', 0),
                    'pnl_percent': holding.get('pnl_percent', 0),
                    'current_price': holding.get('current_price', 0)
                })
            
            return {
                'success': True,
                'data': top_holdings,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching top holdings for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'last_updated': datetime.now().isoformat()
            }
    
    def get_recent_activity(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Get recent trading activity using FYERS API."""
        try:
            # Get recent orders and trades
            orderbook_response = self.fyers_service.orderbook(user_id)
            tradebook_response = self.fyers_service.tradebook(user_id)
            
            activities = []
            
            # Add recent orders
            if orderbook_response.get('status') == 'success':
                orders = orderbook_response.get('data', [])[:limit//2]
# Debug print removed for clean console output
                for order in orders:
                    activities.append({
                        'type': 'order',
                        'id': order.get('orderid', ''),
                        'symbol': order.get('symbol', ''),
                        'symbol_name': order.get('symbol', '').replace('NSE:', '').replace('-EQ', ''),
                        'side': order.get('action', ''),
                        'status': order.get('status', ''),
                        'quantity': order.get('quantity', 0),
                        'price': order.get('price', 0),
                        'timestamp': order.get('timestamp', ''),
                        'order_type': order.get('pricetype', '')
                    })
        
            
            # Sort all activities by timestamp
            activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return {
                'success': True,
                'data': activities[:limit],
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching recent activity for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'last_updated': datetime.now().isoformat()
            }
    
    def get_account_balance(self, user_id: int) -> Dict[str, Any]:
        """Get account balance and available funds using FYERS API."""
        try:
            funds_response = self.fyers_service.funds(user_id)

            # Handle case where API returns a string error instead of dict
            if isinstance(funds_response, str):
                logger.warning(f"Fyers API returned string response for funds: {funds_response}")
                return {
                    'success': False,
                    'error': f'API error: {funds_response}',
                    'data': {'available_cash': 0, 'total_balance': 0, 'margin_used': 0},
                    'last_updated': datetime.now().isoformat()
                }

            # Check if response is not a dictionary
            if not isinstance(funds_response, dict):
                logger.warning(f"Fyers API returned unexpected type for funds: {type(funds_response)}")
                return {
                    'success': False,
                    'error': 'Unexpected API response format',
                    'data': {'available_cash': 0, 'total_balance': 0, 'margin_used': 0},
                    'last_updated': datetime.now().isoformat()
                }

            if funds_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': funds_response.get('message', 'Failed to fetch funds'),
                    'data': {'available_cash': 0, 'total_balance': 0, 'margin_used': 0},
                    'last_updated': datetime.now().isoformat()
                }

            funds = funds_response.get('data', [])
            balance_data = {
                'available_cash': 0,
                'total_balance': 0,
                'margin_used': 0,
                'utilized_amount': 0,
                'available_limit': 0
            }

            # Handle both list and dict formats
            if isinstance(funds, list):
                for fund in funds:
                    title = fund.get('title', '')
                    equity_amount = fund.get('equityAmount', 0)

                    if 'Available Cash' in title:
                        balance_data['available_cash'] = equity_amount
                    elif 'Total Balance' in title:
                        balance_data['total_balance'] = equity_amount
                    elif 'Margin Used' in title:
                        balance_data['margin_used'] = equity_amount
                    elif 'Utilized Amount' in title:
                        balance_data['utilized_amount'] = equity_amount
                    elif 'Available Limit' in title:
                        balance_data['available_limit'] = equity_amount
            elif isinstance(funds, dict):
                # Direct dict format
                balance_data['available_cash'] = funds.get('available_cash', 0)
                balance_data['total_balance'] = funds.get('total_balance', 0)
                balance_data['margin_used'] = funds.get('margin_used', 0)
                balance_data['utilized_amount'] = funds.get('utilized_amount', 0)
                balance_data['available_limit'] = funds.get('available_limit', 0)

            return {
                'success': True,
                'data': balance_data,
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching account balance for user {user_id}: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'data': {'available_cash': 0, 'total_balance': 0, 'margin_used': 0},
                'last_updated': datetime.now().isoformat()
            }
    
    def get_daily_pnl_chart_data(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get daily P&L data for charting using historical data."""
        try:
            # Get portfolio holdings to calculate historical P&L
            holdings_response = self.fyers_service.holdings(user_id)
            
            if holdings_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': 'Unable to fetch holdings for P&L calculation',
                    'data': [],
                    'last_updated': datetime.now().isoformat()
                }
            
            # No historical P&L data available - requires daily portfolio snapshots
            chart_data = []

            return {
                'success': True,
                'data': chart_data,
                'note': 'Historical P&L data not available. Requires daily portfolio snapshots.',
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching daily P&L chart data for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'last_updated': datetime.now().isoformat()
            }
    
    def get_performance_metrics(self, user_id: int, period: str = '1M') -> Dict[str, Any]:
        """Get comprehensive performance metrics using broker-specific data."""
        try:
            # Map period string to days
            period_days_map = {
                '1D': 1,
                '1W': 7,
                '1M': 30,
                '3M': 90,
                '6M': 180,
                '1Y': 365
            }

            period_days = period_days_map.get(period, 30)

            # Try to get current portfolio data
            portfolio_summary = self.get_portfolio_summary(user_id)

            if portfolio_summary.get('success'):
                summary_data = portfolio_summary.get('data', {})

                # DashboardMetrics uses 'total_portfolio_value', 'total_pnl', 'daily_pnl'
                portfolio_value = float(summary_data.get('total_portfolio_value', 0))
                total_pnl = float(summary_data.get('total_pnl', 0))
                daily_pnl = float(summary_data.get('daily_pnl', 0))

                # Always return portfolio value, even if it's 0
                return_percent = (total_pnl / portfolio_value * 100) if portfolio_value > 0 else 0.0
                day_return_percent = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0.0

                performance_data = {
                    'return_percent': round(return_percent, 2),
                    'annualized_return': 0.0,  # Would need historical snapshots
                    'total_pnl': round(total_pnl, 2),
                    'portfolio_value': round(portfolio_value, 2),
                    'period': period,
                    'period_days': period_days,
                    'win_rate': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'volatility': 0.0,
                    'best_day': 0.0,
                    'worst_day': 0.0,
                    'total_trading_days': 0,
                    'chart_data': []
                }

                note = 'Showing current portfolio metrics. Historical performance tracking requires daily snapshots.'
                if portfolio_value == 0:
                    note = 'No portfolio data available. Add positions or holdings to track performance.'

                return {
                    'success': True,
                    'data': performance_data,
                    'note': note,
                    'last_updated': datetime.now().isoformat()
                }

            # Fallback to empty metrics if no portfolio data
            return self._get_enhanced_fallback_metrics(user_id, period, period_days)

        except Exception as e:
            logger.error(f"Error fetching performance metrics for user {user_id}: {str(e)}")
            # Fall back to enhanced fallback metrics on error
            return self._get_enhanced_fallback_metrics(user_id, period, 30)

    def _get_current_portfolio_data(self, user_id: int) -> Dict[str, Any]:
        """Get current portfolio data to check if user has positions."""
        try:
            # Try to get current portfolio from fyers service
            portfolio_report = self.fyers_service.generate_portfolio_summary_report(user_id)

            if portfolio_report.get('status') == 'success':
                data = portfolio_report.get('data', {})
                total_value = data.get('total_portfolio_value', 0)
                has_positions = total_value > 0

                return {
                    'success': True,
                    'has_positions': has_positions,
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'has_positions': False,
                    'data': {}
                }

        except Exception as e:
            logger.warning(f"Could not fetch current portfolio for user {user_id}: {str(e)}")
            return {
                'success': False,
                'has_positions': False,
                'data': {}
            }

    def _get_enhanced_fallback_metrics(self, user_id: int, period: str, period_days: int) -> Dict[str, Any]:
        """Get enhanced fallback metrics when no historical data is available."""
        from datetime import datetime

        # Return empty data - no mock/sample data
        performance_data = {
            'return_percent': 0.0,
            'annualized_return': 0.0,
            'total_pnl': 0.0,
            'portfolio_value': 0.0,
            'period': period,
            'period_days': period_days,
            'win_rate': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'volatility': 0.0,
            'best_day': 0.0,
            'worst_day': 0.0,
            'total_trading_days': 0,
            'chart_data': []
        }

        return {
            'success': True,
            'data': performance_data,
            'note': 'No portfolio data available. Add positions or holdings to track performance.',
            'last_updated': datetime.now().isoformat()
        }

    def _get_basic_performance_metrics(self, user_id: int, period: str) -> Dict[str, Any]:
        """Get basic performance metrics as fallback."""
        try:
            portfolio_report = self.fyers_service.generate_portfolio_summary_report(user_id)

            if portfolio_report.get('status') != 'success':
                return {
                    'success': False,
                    'error': 'Unable to calculate performance metrics',
                    'data': {},
                    'last_updated': datetime.now().isoformat()
                }

            summary = portfolio_report.get('data', {})

            total_portfolio_value = summary.get('total_portfolio_value', 0)
            total_pnl = summary.get('total_pnl', 0)

            return_percent = (total_pnl / total_portfolio_value * 100) if total_portfolio_value > 0 else 0

            # Build a minimal chart using a flat line based on current portfolio value
            try:
                # Map period to days to construct chart points
                period_days_map = {
                    '1D': 1,
                    '1W': 7,
                    '1M': 30,
                    '3M': 90,
                    '6M': 180,
                    '1Y': 365
                }
                period_days = period_days_map.get(period, 30)
                today = datetime.now()
                flat_chart = []
                for i in range(period_days):
                    day = today - timedelta(days=period_days - i - 1)
                    flat_chart.append({
                        'date': day.strftime('%Y-%m-%d'),
                        'value': round(total_portfolio_value, 2),
                        'return': 0,
                        'drawdown': 0
                    })
            except Exception:
                flat_chart = []

            performance_data = {
                'return_percent': round(return_percent, 2),
                'annualized_return': 0.0,
                'total_pnl': round(total_pnl, 2),
                'portfolio_value': round(total_portfolio_value, 2),
                'period': period,
                'period_days': period_days if 'period_days' in locals() else 0,
                'win_rate': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'volatility': 0.0,
                'best_day': 0.0,
                'worst_day': 0.0,
                'total_trading_days': 0,
                'chart_data': flat_chart
            }

            return {
                'success': True,
                'data': performance_data,
                'note': 'Basic metrics - historical data not available',
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching basic performance metrics for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {},
                'last_updated': datetime.now().isoformat()
            }
    
    def get_watchlist_quotes(self, user_id: int, symbols: List[str] = None) -> Dict[str, Any]:
        """Get real-time quotes for watchlist symbols using FYERS API."""
        try:
            if not symbols:
                # Use default popular stocks for watchlist
                symbols = [
                    'NSE:RELIANCE-EQ',
                    'NSE:TCS-EQ', 
                    'NSE:HDFCBANK-EQ',
                    'NSE:INFY-EQ',
                    'NSE:HINDUNILVR-EQ'
                ]
            
            quotes_response = self.fyers_service.quotes_multiple(user_id, symbols)
            
            if quotes_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': quotes_response.get('message', 'Failed to fetch quotes'),
                    'data': [],
                    'last_updated': datetime.now().isoformat()
                }
            
            quotes_data = quotes_response.get('data', {})
            watchlist_quotes = []
            
            for symbol in symbols:
                if symbol in quotes_data:
                    quote_data = quotes_data[symbol]
                    watchlist_quotes.append({
                        'symbol': symbol,
                        'symbol_name': symbol.replace('NSE:', '').replace('-EQ', ''),
                        'price': float(quote_data.get('ltp', 0)),
                        'change': float(quote_data.get('change', 0)),
                        'change_percent': float(quote_data.get('change_percent', 0)),
                        'volume': int(quote_data.get('volume', 0)),
                        'high': float(quote_data.get('high', 0)),
                        'low': float(quote_data.get('low', 0)),
                        'open': float(quote_data.get('open', 0)),
                        'prev_close': float(quote_data.get('prev_close', 0))
                    })
            
            return {
                'success': True,
                'data': watchlist_quotes,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching watchlist quotes for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'last_updated': datetime.now().isoformat()
            }
