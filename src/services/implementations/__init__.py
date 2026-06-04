"""
Broker Implementations Package

Concrete implementations of the broker interfaces. IBKR (Interactive Brokers) providers.
"""

try:
    from .ibkr_dashboard_provider import IBKRDashboardProvider
    from .ibkr_orders_provider import IBKROrdersProvider
    from .ibkr_portfolio_provider import IBKRPortfolioProvider
    from .ibkr_reports_provider import IBKRReportsProvider
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False

__all__ = []

if FYERS_AVAILABLE:
    __all__.extend([
        'IBKRDashboardProvider',
        'IBKROrdersProvider',
        'IBKRPortfolioProvider',
        'IBKRReportsProvider'
    ])
