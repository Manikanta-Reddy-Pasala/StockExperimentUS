"""
Base Broker Service Interface
Defines the common interface that all broker services must implement
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime


class BaseBrokerService(ABC):
    """Base class for all broker services."""
    
    def __init__(self, client_id: str = None, access_token: str = None, api_secret: str = None):
        self.client_id = client_id
        self.access_token = access_token
        self.api_secret = api_secret
        self.is_connected = False
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test broker connection."""
        pass
    
    @abstractmethod
    def get_user_profile(self) -> Dict[str, Any]:
        """Get user profile information."""
        pass
    
    @abstractmethod
    def get_funds(self) -> Dict[str, Any]:
        """Get available funds."""
        pass
    
    @abstractmethod
    def get_holdings(self) -> Dict[str, Any]:
        """Get current holdings."""
        pass
    
    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        """Get current positions."""
        pass
    
    @abstractmethod
    def get_orderbook(self) -> Dict[str, Any]:
        """Get order book."""
        pass
    
    @abstractmethod
    def get_tradebook(self) -> Dict[str, Any]:
        """Get trade book."""
        pass
    
    @abstractmethod
    def get_quotes(self, symbols: str) -> Dict[str, Any]:
        """Get market quotes."""
        pass
    
    @abstractmethod
    def get_history(self, symbol: str, resolution: str = "D", range_from: str = None, range_to: str = None) -> Dict[str, Any]:
        """Get historical data."""
        pass
    
    @abstractmethod
    def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Place an order."""
        pass
    
    @abstractmethod
    def modify_order(self, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Modify an existing order."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        pass


class BrokerDataProcessor:
    """Common data processing utilities for all brokers."""
    
    @staticmethod
    def calculate_pnl(current_price: float, avg_price: float, quantity: int) -> Dict[str, float]:
        """Calculate P&L for a position."""
        if quantity == 0:
            return {'pnl': 0.0, 'pnl_percent': 0.0}
        
        pnl = (current_price - avg_price) * quantity
        pnl_percent = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
        
        return {
            'pnl': round(pnl, 2),
            'pnl_percent': round(pnl_percent, 2)
        }
    
    @staticmethod
    def format_currency(amount: float) -> str:
        """Format currency with proper Indian notation."""
        if amount >= 10000000:  # 1 crore
            return f"₹{amount/10000000:.2f}Cr"
        elif amount >= 100000:  # 1 lakh
            return f"₹{amount/100000:.2f}L"
        else:
            return f"₹{amount:,.2f}"
    
    @staticmethod
    def format_quantity(quantity: int) -> str:
        """Format quantity with proper notation."""
        if quantity >= 100000:
            return f"{quantity/100000:.1f}L"
        elif quantity >= 1000:
            return f"{quantity/1000:.1f}K"
        else:
            return str(quantity)
    
    @staticmethod
    def get_order_status_color(status: str) -> str:
        """Get Bootstrap color class for order status."""
        status_colors = {
            'open': 'warning',
            'complete': 'success',
            'cancelled': 'danger',
            'rejected': 'danger',
            'pending': 'info',
            'partially_filled': 'primary'
        }
        return status_colors.get(status.lower(), 'secondary')
    
    @staticmethod
    def get_pnl_color(pnl: float) -> str:
        """Get Bootstrap color class for P&L."""
        if pnl > 0:
            return 'success'
        elif pnl < 0:
            return 'danger'
        else:
            return 'secondary'
