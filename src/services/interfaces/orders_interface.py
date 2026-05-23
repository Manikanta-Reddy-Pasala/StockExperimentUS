"""
Orders Interface Definition

Defines the contract for orders management features across different brokers.
Each broker implementation must provide these methods.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order sides."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status."""
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PENDING = "pending"


class IOrdersProvider(ABC):
    """
    Interface for orders data providers.
    
    This interface defines all the methods that must be implemented
    by each broker to provide orders functionality.
    """

    @abstractmethod
    def get_orders_history(self, user_id: int, start_date: datetime = None, 
                          end_date: datetime = None, limit: int = 100) -> Dict[str, Any]:
        """
        Get orders history.
        
        Args:
            user_id: The user ID for broker-specific authentication
            start_date: Start date for filtering orders
            end_date: End date for filtering orders
            limit: Maximum number of orders to return
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of orders with details
            - total: Total number of orders
            - last_updated: timestamp
        """
        pass
    @abstractmethod
    def get_pending_orders(self, user_id: int) -> Dict[str, Any]:
        """
        Get pending orders.
        
        Args:
            user_id: The user ID for broker-specific authentication
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of pending orders
            - total: Total number of pending orders
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def get_trades_history(self, user_id: int, start_date: datetime = None, 
                          end_date: datetime = None, limit: int = 100) -> Dict[str, Any]:
        """
        Get trades history.
        
        Args:
            user_id: The user ID for broker-specific authentication
            start_date: Start date for filtering trades
            end_date: End date for filtering trades
            limit: Maximum number of trades to return
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of trades with details
            - total: Total number of trades
            - last_updated: timestamp
        """
        pass

    @abstractmethod
    def place_order(self, user_id: int, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place a new order.
        
        Args:
            user_id: The user ID for broker-specific authentication
            order_data: Order details (symbol, side, type, quantity, price, etc.)
            
        Returns:
            Dict containing:
            - success: bool
            - order_id: ID of the placed order
            - message: Success/error message
        """
        pass
    @abstractmethod
    def modify_order(self, user_id: int, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Modify an existing order.
        
        Args:
            user_id: The user ID for broker-specific authentication
            order_id: ID of the order to modify
            order_data: Modified order details
            
        Returns:
            Dict containing:
            - success: bool
            - message: Success/error message
        """
        pass

    @abstractmethod
    def cancel_order(self, user_id: int, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            user_id: The user ID for broker-specific authentication
            order_id: ID of the order to cancel
            
        Returns:
            Dict containing:
            - success: bool
            - message: Success/error message
        """
        pass

    @abstractmethod
    def get_order_details(self, user_id: int, order_id: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific order.
        
        Args:
            user_id: The user ID for broker-specific authentication
            order_id: ID of the order
            
        Returns:
            Dict containing:
            - success: bool
            - data: Detailed order information
            - last_updated: timestamp
        """
        pass


class Order:
    """Data class for order information."""
    
    def __init__(self, order_id: str, symbol: str, side: OrderSide, 
                 order_type: OrderType, quantity: int, price: float):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.quantity = quantity
        self.price = price
        self.status: OrderStatus = OrderStatus.PENDING
        self.filled_quantity: int = 0
        self.remaining_quantity: int = quantity
        self.order_time: datetime = datetime.now()
        self.fill_time: Optional[datetime] = None
        self.product: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'type': self.order_type.value,
            'quantity': self.quantity,
            'price': self.price,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'remaining_quantity': self.remaining_quantity,
            'order_time': self.order_time.isoformat(),
            'fill_time': self.fill_time.isoformat() if self.fill_time else None,
            'product': self.product
        }
