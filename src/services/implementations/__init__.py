"""
Broker Implementations Package

Concrete implementations of the broker interfaces. Only Fyers is supported.
"""

try:
    from .fyers_dashboard_provider import FyersDashboardProvider
    from .fyers_orders_provider import FyersOrdersProvider
    from .fyers_portfolio_provider import FyersPortfolioProvider
    from .fyers_reports_provider import FyersReportsProvider
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False

__all__ = []

if FYERS_AVAILABLE:
    __all__.extend([
        'FyersDashboardProvider',
        'FyersOrdersProvider',
        'FyersPortfolioProvider',
        'FyersReportsProvider'
    ])
