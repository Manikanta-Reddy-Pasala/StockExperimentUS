"""
Unified Multi-Broker Service

Unified interface for all broker features via Strategy pattern.
Broker-only: Fyers is the sole data source. No yfinance fallback.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from ..interfaces import (
    IDashboardProvider, IOrdersProvider,
    IPortfolioProvider, IReportsProvider, BrokerFeatureFactory,
    get_broker_feature_factory
)

logger = logging.getLogger(__name__)


class UnifiedBrokerService:
    """
    Unified service that delegates to broker-specific implementations
    based on user settings.
    """
    
    def __init__(self):
        self.factory = get_broker_feature_factory()
    
    # Dashboard methods
    def get_market_overview(self, user_id: int) -> Dict[str, Any]:
        """Get market overview using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_market_overview(user_id)
    
    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        """Get portfolio summary using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_portfolio_summary(user_id)
    
    def get_top_holdings(self, user_id: int, limit: int = 5) -> Dict[str, Any]:
        """Get top holdings using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_top_holdings(user_id, limit)
    
    def get_recent_activity(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Get recent activity using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_recent_activity(user_id, limit)
    
    def get_account_balance(self, user_id: int) -> Dict[str, Any]:
        """Get account balance using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_account_balance(user_id)
    
    def get_daily_pnl_chart_data(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get daily P&L chart data using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_daily_pnl_chart_data(user_id, days)
    
    def get_performance_metrics(self, user_id: int, period: str = '1M') -> Dict[str, Any]:
        """Get performance metrics using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_performance_metrics(user_id, period)
    
    def get_watchlist_quotes(self, user_id: int, symbols: List[str] = None) -> Dict[str, Any]:
        """Get watchlist quotes using user's selected broker."""
        provider = self.factory.get_dashboard_provider(user_id)
        if not provider:
            return self._no_provider_error('dashboard')
        return provider.get_watchlist_quotes(user_id, symbols)
    
    # Orders methods
    def get_orders_history(self, user_id: int, start_date: datetime = None, 
                          end_date: datetime = None, limit: int = 100) -> Dict[str, Any]:
        """Get orders history using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.get_orders_history(user_id, start_date, end_date, limit)
    
    def get_pending_orders(self, user_id: int) -> Dict[str, Any]:
        """Get pending orders using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.get_pending_orders(user_id)
    
    def get_trades_history(self, user_id: int, start_date: datetime = None, 
                          end_date: datetime = None, limit: int = 100) -> Dict[str, Any]:
        """Get trades history using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.get_trades_history(user_id, start_date, end_date, limit)
    
    def place_order(self, user_id: int, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Place order using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.place_order(user_id, order_data)
    
    def modify_order(self, user_id: int, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Modify order using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.modify_order(user_id, order_id, order_data)
    
    def cancel_order(self, user_id: int, order_id: str) -> Dict[str, Any]:
        """Cancel order using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.cancel_order(user_id, order_id)
    
    def get_order_details(self, user_id: int, order_id: str) -> Dict[str, Any]:
        """Get order details using user's selected broker."""
        provider = self.factory.get_orders_provider(user_id)
        if not provider:
            return self._no_provider_error('orders')
        return provider.get_order_details(user_id, order_id)
    
    # Portfolio methods
    def get_holdings(self, user_id: int) -> Dict[str, Any]:
        """Get holdings using user's selected broker."""
        provider = self.factory.get_portfolio_provider(user_id)
        if not provider:
            return self._no_provider_error('portfolio')
        return provider.holdings(user_id)
    
    def get_positions(self, user_id: int) -> Dict[str, Any]:
        """Get positions using user's selected broker."""
        provider = self.factory.get_portfolio_provider(user_id)
        if not provider:
            return self._no_provider_error('portfolio')
        return provider.positions(user_id)
    
    def get_portfolio_allocation(self, user_id: int) -> Dict[str, Any]:
        """Get portfolio allocation using user's selected broker."""
        provider = self.factory.get_portfolio_provider(user_id)
        if not provider:
            return self._no_provider_error('portfolio')
        return provider.get_portfolio_allocation(user_id)
    
    def get_portfolio_performance(self, user_id: int, period: str = '1M') -> Dict[str, Any]:
        """Get portfolio performance using user's selected broker."""
        provider = self.factory.get_portfolio_provider(user_id)
        if not provider:
            return self._no_provider_error('portfolio')
        return provider.get_portfolio_performance(user_id, period)
    
    def get_dividend_history(self, user_id: int, start_date: datetime = None, 
                           end_date: datetime = None) -> Dict[str, Any]:
        """Get dividend history using user's selected broker."""
        provider = self.factory.get_portfolio_provider(user_id)
        if not provider:
            return self._no_provider_error('portfolio')
        return provider.get_dividend_history(user_id, start_date, end_date)
    
    def get_portfolio_risk_metrics(self, user_id: int) -> Dict[str, Any]:
        """Get portfolio risk metrics using user's selected broker."""
        provider = self.factory.get_portfolio_provider(user_id)
        if not provider:
            return self._no_provider_error('portfolio')
        return provider.get_portfolio_risk_metrics(user_id)
    
    # Reports methods
    def generate_pnl_report(self, user_id: int, start_date: datetime, 
                           end_date: datetime, report_format: Any = None) -> Dict[str, Any]:
        """Generate P&L report using user's selected broker."""
        provider = self.factory.get_reports_provider(user_id)
        if not provider:
            return self._no_provider_error('reports')
        return provider.generate_pnl_report(user_id, start_date, end_date, report_format)
    
    def generate_tax_report(self, user_id: int, financial_year: str, 
                          report_format: Any = None) -> Dict[str, Any]:
        """Generate tax report using user's selected broker."""
        provider = self.factory.get_reports_provider(user_id)
        if not provider:
            return self._no_provider_error('reports')
        return provider.generate_tax_report(user_id, financial_year, report_format)
    
    def generate_portfolio_report(self, user_id: int, report_type: Any, 
                                 report_format: Any = None) -> Dict[str, Any]:
        """Generate portfolio report using user's selected broker."""
        provider = self.factory.get_reports_provider(user_id)
        if not provider:
            return self._no_provider_error('reports')
        return provider.generate_portfolio_report(user_id, report_type, report_format)
    
    def generate_trading_summary(self, user_id: int, start_date: datetime, 
                               end_date: datetime, report_format: Any = None) -> Dict[str, Any]:
        """Generate trading summary using user's selected broker."""
        provider = self.factory.get_reports_provider(user_id)
        if not provider:
            return self._no_provider_error('reports')
        return provider.generate_trading_summary(user_id, start_date, end_date, report_format)
    
    def get_report_history(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        """Get report history using user's selected broker."""
        provider = self.factory.get_reports_provider(user_id)
        if not provider:
            return self._no_provider_error('reports')
        return provider.get_report_history(user_id, limit)
    
    def download_report(self, user_id: int, report_id: str) -> Dict[str, Any]:
        """Download report using user's selected broker."""
        provider = self.factory.get_reports_provider(user_id)
        if not provider:
            return self._no_provider_error('reports')
        return provider.download_report(user_id, report_id)
    
    # Market data methods
    def get_quotes(self, user_id: int, symbols: List[str]) -> Dict[str, Any]:
        """Get market quotes from Fyers. No fallback."""
        try:
            from src.models.database import get_database_manager
            from src.models.models import User, BrokerConfiguration

            db_manager = get_database_manager()
            with db_manager.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    return self._no_provider_error('quotes')

                broker_config = session.query(BrokerConfiguration).filter(
                    BrokerConfiguration.user_id == user_id,
                    BrokerConfiguration.is_active == True
                ).first()
                current_broker = broker_config.broker_name if broker_config else 'fyers'

            if current_broker == 'fyers':
                from ..brokers.ibkr import IBKRBrokerService
                return IBKRBrokerService().quotes_multiple(user_id, symbols)
            return self._no_provider_error('quotes')

        except Exception as e:
            logger.error(f"Error getting quotes for user {user_id}: {e}")
            return {
                'success': False,
                'error': f'Failed to get quotes: {str(e)}',
                'data': {}
            }

    def get_historical_data(self, user_id: int, symbol: str, resolution: str = "1D", period: str = "1d") -> Dict[str, Any]:
        """Get historical data from Fyers. No fallback."""
        try:
            import re
            from datetime import datetime, timedelta
            if period == "1d":
                days = 1
            elif period == "1w":
                days = 7
            elif period == "1m":
                days = 30
            elif period == "1y":
                days = 365
            else:
                match = re.match(r'(\d+)d', period)
                days = int(match.group(1)) if match else 1

            from src.models.database import get_database_manager
            from src.models.models import User, BrokerConfiguration

            db_manager = get_database_manager()
            with db_manager.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    return self._no_provider_error('historical_data')

                broker_config = session.query(BrokerConfiguration).filter(
                    BrokerConfiguration.user_id == user_id,
                    BrokerConfiguration.is_active == True
                ).first()
                current_broker = broker_config.broker_name if broker_config else 'fyers'

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')

            if current_broker == 'fyers':
                from ..brokers.ibkr import IBKRBrokerService
                exchange = symbol.split(':')[0] if ':' in symbol else 'NSE'
                return IBKRBrokerService().history(user_id, symbol, exchange, resolution, start_date_str, end_date_str)
            return self._no_provider_error('historical_data')

        except Exception as e:
            logger.error(f"Error getting historical data for user {user_id}, symbol {symbol}: {e}")
            return {
                'success': False,
                'error': f'Failed to get historical data: {str(e)}',
                'data': {}
            }

    # Utility methods
    def get_available_brokers(self) -> Dict[str, Dict[str, bool]]:
        """Get list of available brokers and their supported features."""
        return self.factory.get_available_brokers()
    
    def _no_provider_error(self, feature_type: str) -> Dict[str, Any]:
        """Return error when no provider is available for the feature."""
        return {
            'success': False,
            'error': f'No {feature_type} provider available for the selected broker',
            'data': [],
            'last_updated': datetime.now().isoformat()
        }


# Global service instance
_unified_broker_service = None

def get_unified_broker_service() -> UnifiedBrokerService:
    """Get the global unified broker service instance."""
    global _unified_broker_service
    if _unified_broker_service is None:
        _unified_broker_service = UnifiedBrokerService()
    return _unified_broker_service
