"""
Portfolio Interface Definition

Defines the contract for portfolio management features across different brokers.
Each broker implementation must provide these methods.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime


class IPortfolioProvider(ABC):
    """
    Interface for portfolio data providers.
    
    This interface defines all the methods that must be implemented
    by each broker to provide portfolio functionality.
    """

    @abstractmethod
    def get_holdings(self, user_id: int) -> Dict[str, Any]:
        """
        Get current holdings.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of holdings with details
            - total_value: Total portfolio value
            - total_pnl: Total P&L
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_positions(self, user_id: int) -> Dict[str, Any]:
        """
        Get current positions.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of positions with details
            - total_value: Total positions value
            - total_pnl: Total P&L
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        """
        Get portfolio summary and metrics.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: Portfolio summary metrics
            - last_updated: timestamp
        """
        pass
    @abstractmethod
    def get_portfolio_allocation(self, user_id: int) -> Dict[str, Any]:
        """
        Get portfolio allocation by sector/asset class.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: Portfolio allocation breakdown
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_portfolio_performance(self, user_id: int, period: str = '1M') -> Dict[str, Any]:
        """
        Get portfolio performance metrics.
        
        Args:
            user_id: The user ID for broker-specific authentication
            period: Time period for performance calculation
            
        Returns:
            Dict containing:
            - success: bool
            - data: Performance metrics (returns, volatility, sharpe ratio, etc.)
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_dividend_history(self, user_id: int, start_date: datetime = None, 
                           end_date: datetime = None) -> Dict[str, Any]:
        """
        Get dividend history.
        
        Args:
            user_id: The user ID for broker-specific authentication
            start_date: Start date for filtering dividends
            end_date: End date for filtering dividends
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of dividend records
            - total_dividends: Total dividend amount
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_portfolio_risk_metrics(self, user_id: int) -> Dict[str, Any]:
        """
        Get portfolio risk analysis.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: Risk metrics (VaR, beta, correlation, etc.)
            - last_updated: timestamp
        """
        pass
class Holding:
    """Data class for holding information."""
    
    def __init__(self, symbol: str, name: str, quantity: int, 
                 avg_price: float, current_price: float):
        self.symbol = symbol
        self.name = name
        self.quantity = quantity
        self.avg_price = avg_price
        self.current_price = current_price
        self.current_value = quantity * current_price
        self.investment_value = quantity * avg_price
        self.pnl = self.current_value - self.investment_value
        self.pnl_percent = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        self.last_updated = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'quantity': self.quantity,
            'avg_price': self.avg_price,
            'current_price': self.current_price,
            'current_value': self.current_value,
            'investment_value': self.investment_value,
            'pnl': self.pnl,
            'pnl_percent': self.pnl_percent,
            'last_updated': self.last_updated.isoformat()
        }


class Position:
    """Data class for position information."""
    
    def __init__(self, symbol: str, side: str, quantity: int, 
                 avg_price: float, current_price: float):
        self.symbol = symbol
        self.side = side  # 'long' or 'short'
        self.quantity = quantity
        self.avg_price = avg_price
        self.current_price = current_price
        self.current_value = quantity * current_price
        self.pnl = (current_price - avg_price) * quantity if side == 'long' else (avg_price - current_price) * quantity
        self.pnl_percent = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        self.last_updated = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'avg_price': self.avg_price,
            'current_price': self.current_price,
            'current_value': self.current_value,
            'pnl': self.pnl,
            'pnl_percent': self.pnl_percent,
            'last_updated': self.last_updated.isoformat()
        }
