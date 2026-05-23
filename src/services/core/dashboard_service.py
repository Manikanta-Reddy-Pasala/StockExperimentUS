"""
Service for dashboard-related logic.
Now uses the new DashboardIntegrationService for broker-agnostic integration.
"""
from datetime import datetime
from .broker_service import get_broker_service
from .dashboard_integration_service import get_dashboard_integration_service

class DashboardService:
    def __init__(self, broker_service):
        self.broker_service = broker_service
        self.integration_service = get_dashboard_integration_service(broker_service)

    def get_dashboard_metrics(self, user_id: int):
        """Get dashboard metrics using broker-specific APIs."""
        metrics = self.integration_service.get_dashboard_metrics(user_id)

        metrics['active_strategies_count'] = 1
        metrics['active_strategies'] = ['EMA 200/400 1H Crossover']

        return metrics
    
    def get_portfolio_holdings(self, user_id: int):
        """Get portfolio holdings using broker-specific APIs."""
        return self.integration_service.get_portfolio_holdings(user_id)
    
    def get_pending_orders(self, user_id: int):
        """Get pending orders using broker-specific APIs."""
        return self.integration_service.get_pending_orders(user_id)
    
    def get_recent_orders(self, user_id: int, limit: int = 10):
        """Get recent orders using broker-specific APIs."""
        return self.integration_service.get_recent_orders(user_id, limit)
    
    def get_portfolio_performance(self, user_id: int, period: str = '1W'):
        """Get portfolio performance data using broker-specific APIs."""
        return self.integration_service.get_portfolio_performance(user_id, period)

_dashboard_service = None

def get_dashboard_service():
    """Singleton factory for DashboardService."""
    global _dashboard_service
    if _dashboard_service is None:
        broker_service = get_broker_service()
        _dashboard_service = DashboardService(broker_service)
    return _dashboard_service
