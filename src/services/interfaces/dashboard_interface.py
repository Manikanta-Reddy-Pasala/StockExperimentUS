"""
Dashboard Interface Definition

Defines the contract for dashboard-related features across different brokers.
Each broker implementation must provide these methods.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime


class IDashboardProvider(ABC):
    """
    Interface for dashboard data providers.
    
    This interface defines all the methods that must be implemented
    by each broker to provide dashboard functionality.
    """

    @abstractmethod
    def get_market_overview(self, user_id: int) -> Dict[str, Any]:
        """
        Get market overview data for major indices.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of market indices with price, change, change_percent
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        """
        Get portfolio summary metrics.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: Dict with total_pnl, total_value, holdings_count, positions_count
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_top_holdings(self, user_id: int, limit: int = 5) -> Dict[str, Any]:
        """
        Get top holdings by value.
        
        Args:
            user_id: The user ID for broker-specific authentication
            limit: Maximum number of holdings to return
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of holdings with symbol, quantity, current_value, pnl
            - last_updated: timestamp
        """
        pass
    @abstractmethod
    def get_recent_activity(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """
        Get recent trading activity.
        
        Args:
            user_id: The user ID for broker-specific authentication
            limit: Maximum number of activities to return
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of recent orders/trades with type, symbol, status, timestamp
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_account_balance(self, user_id: int) -> Dict[str, Any]:
        """
        Get account balance and available funds.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: Dict with available_cash, total_balance, margin_used
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_daily_pnl_chart_data(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Get daily P&L data for charting.
        
        Args:
            user_id: The user ID for broker-specific authentication
            days: Number of days of historical data
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of daily P&L data points with date and pnl
            - last_updated: timestamp
        """
        pass
    @abstractmethod
    def get_performance_metrics(self, user_id: int, period: str = '1M') -> Dict[str, Any]:
        """
        Get performance metrics for a given period.
        
        Args:
            user_id: The user ID for broker-specific authentication
            period: Time period ('1D', '1W', '1M', '3M', '6M', '1Y')
            
        Returns:
            Dict containing:
            - success: bool
            - data: Dict with return_percent, win_rate, sharpe_ratio, max_drawdown
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_watchlist_quotes(self, user_id: int, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Get real-time quotes for watchlist symbols.
        
        Args:
            user_id: The user ID for broker-specific authentication
            symbols: List of symbols to get quotes for (defaults to user's watchlist)
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of symbol quotes with price, change, volume
            - last_updated: timestamp
        """
        pass


class DashboardMetrics:
    """Data class for standardized dashboard metrics."""
    
    def __init__(self, total_pnl: float = 0.0, total_portfolio_value: float = 0.0, 
                 available_cash: float = 0.0, holdings_count: int = 0, 
                 positions_count: int = 0, daily_pnl: float = 0.0, 
                 daily_pnl_percent: float = 0.0, total_pnl_percent: float = 0.0):
        self.total_pnl: float = total_pnl
        self.total_portfolio_value: float = total_portfolio_value
        self.available_cash: float = available_cash
        self.holdings_count: int = holdings_count
        self.positions_count: int = positions_count
        self.daily_pnl: float = daily_pnl
        self.daily_pnl_percent: float = daily_pnl_percent
        self.total_pnl_percent: float = total_pnl_percent
        self.last_updated: datetime = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'total_pnl': self.total_pnl,
            'total_portfolio_value': self.total_portfolio_value,
            'available_cash': self.available_cash,
            'holdings_count': self.holdings_count,
            'positions_count': self.positions_count,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_percent': self.daily_pnl_percent,
            'total_pnl_percent': self.total_pnl_percent,
            'last_updated': self.last_updated.isoformat()
        }
class MarketIndex:
    """Data class for market index information."""
    
    def __init__(self, symbol: str, name: str, price: float, change: float, change_percent: float):
        self.symbol = symbol
        self.name = name
        self.price = price
        self.change = change
        self.change_percent = change_percent
        self.last_updated = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'price': self.price,
            'change': self.change,
            'change_percent': self.change_percent,
            'last_updated': self.last_updated.isoformat()
        }
