"""
Dashboard Integration Service
Integrates all dashboard sections with broker-specific APIs
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DashboardIntegrationService:
    """Service for integrating dashboard sections with broker APIs."""
    
    def __init__(self, broker_service=None):
        self.broker_service = broker_service
        self.current_broker = None
        self.broker_instance = None
    
    def _get_broker_instance(self, user_id: int = 1) -> Optional[Any]:
        """Get the current broker instance based on user settings."""
        try:
            if not self.broker_service:
                return None
            
            # Get current broker from user settings
            from .user_settings_service import get_user_settings_service
            settings_service = get_user_settings_service()
            settings = settings_service.get_user_settings(user_id)
            
            current_broker = settings.get('current_broker', 'fyers')
            
            # Get broker configuration
            broker_config = self.broker_service.get_broker_config(current_broker, user_id)
            
            if not broker_config or not broker_config.get('is_connected'):
                logger.warning(f"Broker {current_broker} not connected for user {user_id}")
                return None
            
            # Import and initialize the appropriate broker service
            if current_broker == 'fyers':
                from ..brokers.ibkr import IBKRBrokerService
                self.broker_instance = IBKRBrokerService()
            else:
                logger.error(f"Unknown broker: {current_broker}")
                return None
            
            self.current_broker = current_broker
            return self.broker_instance
            
        except Exception as e:
            logger.error(f"Error getting broker instance: {e}")
            return None
    
    def get_dashboard_metrics(self, user_id: int = 1) -> Dict[str, Any]:
        """Get comprehensive dashboard metrics from broker."""
        try:
            broker = self._get_broker_instance(user_id)
            if not broker:
                return {
                    'success': False,
                    'error': 'No broker connected. Please configure your broker connection.',
                    'data': None
                }
            
            # Fetch data from broker
            funds_data = broker.funds(user_id)
            holdings_data = broker.holdings(user_id)
            positions_data = broker.positions(user_id)
            orderbook_data = broker.orderbook(user_id)
            
            # Calculate metrics
            total_pnl = self._calculate_total_pnl(positions_data, holdings_data)
            active_positions = self._count_active_positions(positions_data)
            pending_orders = self._count_pending_orders(orderbook_data)
            active_strategies = self._count_active_strategies(user_id)
            
            return {
                'success': True,
                'data': {
                    'total_pnl': total_pnl,
                    'active_positions': active_positions,
                    'pending_orders': pending_orders,
                    'active_strategies': active_strategies,
                    'broker': self.current_broker,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard metrics: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': None
            }
    
    def get_portfolio_holdings(self, user_id: int = 1) -> Dict[str, Any]:
        """Get portfolio holdings from broker."""
        try:
            broker = self._get_broker_instance(user_id)
            if not broker:
                return {
                    'success': False,
                    'error': 'No broker connected. Please configure your broker connection.',
                    'data': []
                }
            
            holdings_data = broker.holdings(user_id)
            positions_data = broker.positions(user_id)
            
            # Process and combine holdings and positions
            processed_holdings = self._process_holdings_data(holdings_data, positions_data)
            
            return {
                'success': True,
                'data': processed_holdings,
                'broker': self.current_broker,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting portfolio holdings: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }
    
    def get_pending_orders(self, user_id: int = 1) -> Dict[str, Any]:
        """Get pending orders from broker."""
        try:
            broker = self._get_broker_instance(user_id)
            if not broker:
                return {
                    'success': False,
                    'error': 'No broker connected. Please configure your broker connection.',
                    'data': []
                }
            
            orderbook_data = broker.orderbook(user_id)
            processed_orders = self._process_orders_data(orderbook_data, status_filter='pending')
            
            return {
                'success': True,
                'data': processed_orders,
                'broker': self.current_broker,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting pending orders: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }
    
    def get_recent_orders(self, user_id: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Get recent orders from broker."""
        try:
            broker = self._get_broker_instance(user_id)
            if not broker:
                return {
                    'success': False,
                    'error': 'No broker connected. Please configure your broker connection.',
                    'data': []
                }
            
            orderbook_data = broker.orderbook(user_id)
            processed_orders = self._process_orders_data(orderbook_data, limit=limit)
            
            return {
                'success': True,
                'data': processed_orders,
                'broker': self.current_broker,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting recent orders: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }
    
    def get_portfolio_performance(self, user_id: int = 1, period: str = '1W') -> Dict[str, Any]:
        """Get portfolio performance data for charts."""
        try:
            broker = self._get_broker_instance(user_id)
            if not broker:
                return {
                    'success': False,
                    'error': 'No broker connected. Please configure your broker connection.',
                    'data': None
                }
            
            # Get historical portfolio data
            performance_data = self._get_historical_portfolio_data(broker, period)
            
            return {
                'success': True,
                'data': performance_data,
                'broker': self.current_broker,
                'period': period,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting portfolio performance: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': None
            }
    
    def _calculate_total_pnl(self, positions_data: Dict, holdings_data: Dict) -> float:
        """Calculate total P&L from positions and holdings."""
        try:
            total_pnl = 0.0
            
            # Calculate P&L from positions
            if positions_data and positions_data.get('status') == 'success':
                positions = positions_data.get('data', [])
                for position in positions:
                    pnl = position.get('pl', 0)
                    total_pnl += float(pnl) if pnl else 0
            
            # Calculate P&L from holdings (include all holdings, even with zero quantity)
            if holdings_data and holdings_data.get('status') == 'success':
                holdings = holdings_data.get('data', [])
                for holding in holdings:
                    pnl = holding.get('pnl', 0)
                    pnl_float = float(pnl) if pnl else 0
                    total_pnl += pnl_float
            return round(total_pnl, 2)
            
        except Exception as e:
            logger.error(f"Error calculating total P&L: {e}")
            return 0.0
    
    def _count_active_positions(self, positions_data: Dict) -> int:
        """Count active positions."""
        try:
            if not positions_data or not positions_data.get('success'):
                return 0
            
            positions = positions_data.get('data', {}).get('overall', {}).get('net', [])
            active_count = 0
            
            for position in positions:
                qty = position.get('qty', 0)
                if qty != 0:  # Non-zero quantity means active position
                    active_count += 1
            
            return active_count
            
        except Exception as e:
            logger.error(f"Error counting active positions: {e}")
            return 0
    
    def _count_pending_orders(self, orderbook_data: Dict) -> int:
        """Count pending orders."""
        try:
            if not orderbook_data or not orderbook_data.get('success'):
                return 0
            
            orders = orderbook_data.get('data', {}).get('orderBook', [])
            pending_count = 0
            
            for order in orders:
                status = order.get('status', '').lower()
                if status in ['open', 'pending', 'trigger_pending']:
                    pending_count += 1
            
            return pending_count
            
        except Exception as e:
            logger.error(f"Error counting pending orders: {e}")
            return 0
    
    def _count_active_strategies(self, user_id: int) -> int:
        """Count active strategies (mock implementation)."""
        # This would integrate with your strategy service
        return 3  # Mock value
    
    def _process_holdings_data(self, holdings_data: Dict, positions_data: Dict) -> List[Dict]:
        """Process holdings data for display."""
        processed = []
        
        try:
            # Process holdings
            if holdings_data and holdings_data.get('status') == 'success':
                holdings = holdings_data.get('data', [])
                for holding in holdings:
                    # Include all holdings for display, even with zero quantity
                    processed.append({
                        'symbol': holding.get('symbol', ''),
                        'quantity': float(holding.get('quantity', 0)),
                        'avg_price': float(holding.get('average_price', 0)),
                        'current_price': float(holding.get('last_price', 0)),
                        'pnl': float(holding.get('pnl', 0)),
                        'pnl_percent': 0,  # Calculate if needed
                        'type': 'holding'
                    })
            
            # Process positions
            if positions_data and positions_data.get('status') == 'success':
                positions = positions_data.get('data', [])
                for position in positions:
                    if position.get('qty', 0) != 0:  # Only active positions
                        processed.append({
                            'symbol': position.get('symbol', ''),
                            'quantity': position.get('qty', 0),
                            'avg_price': position.get('avgPrice', 0),
                            'current_price': position.get('ltp', 0),
                            'pnl': position.get('pl', 0),
                            'pnl_percent': position.get('pl_percent', 0),
                            'type': 'position'
                        })
            
        except Exception as e:
            logger.error(f"Error processing holdings data: {e}")
        
        return processed
    
    def _process_orders_data(self, orderbook_data: Dict, status_filter: str = None, limit: int = None) -> List[Dict]:
        """Process orders data for display."""
        processed = []
        
        try:
            if not orderbook_data or not orderbook_data.get('success'):
                return processed
            
            orders = orderbook_data.get('data', {}).get('orderBook', [])
            
            for order in orders:
                status = order.get('status', '').lower()
                
                # Apply status filter if specified
                if status_filter and status != status_filter:
                    continue
                
                processed.append({
                    'order_id': order.get('id', ''),
                    'symbol': order.get('symbol', ''),
                    'type': order.get('type', ''),
                    'side': order.get('side', ''),
                    'quantity': order.get('qty', 0),
                    'price': order.get('limitPrice', 0),
                    'status': status,
                    'timestamp': order.get('orderDateTime', ''),
                    'filled_qty': order.get('filledQty', 0)
                })
            
            # Apply limit if specified
            if limit:
                processed = processed[:limit]
            
        except Exception as e:
            logger.error(f"Error processing orders data: {e}")
        
        return processed
    
    def _get_historical_portfolio_data(self, broker: Any, period: str) -> Dict:
        """Get historical portfolio data for performance chart."""
        # This would integrate with your portfolio tracking service
        # For now, return empty data structure
        return {
            'labels': [],
            'datasets': [{
                'label': 'Portfolio Value',
                'data': [],
                'borderColor': 'rgb(75, 192, 192)',
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'tension': 0.1
            }]
        }


def get_dashboard_integration_service(broker_service=None) -> DashboardIntegrationService:
    """Get dashboard integration service instance."""
    return DashboardIntegrationService(broker_service)
