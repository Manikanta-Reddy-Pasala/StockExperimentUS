"""
Consolidated Order Management Service
Combines functionality from orders/ and order/ modules
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    """Order sides."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order statuses."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderService:
    """Consolidated order management service."""
    
    def __init__(self, db_manager):
        """Initialize order service."""
        self.db_manager = db_manager
    
    def create_buy_order(self, user_id: int, symbol: str, quantity: int, 
                        order_type: OrderType = OrderType.MARKET, 
                        price: Optional[float] = None,
                        stop_loss_price: Optional[float] = None,
                        take_profit_price: Optional[float] = None) -> Optional[str]:
        """Create a buy order with optional stop-loss and take-profit."""
        try:
            order_id = self._generate_order_id()
            
            with self.db_manager.get_session() as session:
                # Create main buy order
                order = self._create_order_record(
                    session, user_id, order_id, symbol, order_type, 
                    OrderSide.BUY, quantity, price
                )
                
                # Create stop-loss order if specified
                if stop_loss_price:
                    stop_loss_order_id = f"{order_id}_SL"
                    self._create_order_record(
                        session, user_id, stop_loss_order_id, symbol,
                        OrderType.STOP_LOSS, OrderSide.SELL, quantity,
                        trigger_price=stop_loss_price, parent_order_id=order_id
                    )
                
                # Create take-profit order if specified
                if take_profit_price:
                    take_profit_order_id = f"{order_id}_TP"
                    self._create_order_record(
                        session, user_id, take_profit_order_id, symbol,
                        OrderType.LIMIT, OrderSide.SELL, quantity,
                        price=take_profit_price, parent_order_id=order_id
                    )
                
                session.commit()
                logger.info(f"Created buy order {order_id} for {symbol}")
                return order_id
                
        except Exception as e:
            logger.error(f"Error creating buy order: {e}")
            return None
    
    def create_sell_order(self, user_id: int, symbol: str, quantity: int,
                         order_type: OrderType = OrderType.MARKET,
                         price: Optional[float] = None) -> Optional[str]:
        """Create a sell order."""
        try:
            order_id = self._generate_order_id()
            
            with self.db_manager.get_session() as session:
                self._create_order_record(
                    session, user_id, order_id, symbol, order_type,
                    OrderSide.SELL, quantity, price
                )
                session.commit()
                
                logger.info(f"Created sell order {order_id} for {symbol}")
                return order_id
                
        except Exception as e:
            logger.error(f"Error creating sell order: {e}")
            return None
    
    def execute_order(self, order_id: str, execution_price: float, 
                     execution_quantity: int) -> bool:
        """Execute an order (simulate order execution)."""
        try:
            with self.db_manager.get_session() as session:
                # Get order
                order = session.query(self.db_manager.Order).filter(
                    self.db_manager.Order.order_id == order_id
                ).first()
                
                if not order:
                    logger.error(f"Order {order_id} not found")
                    return False
                
                # Update order status
                if execution_quantity == order.quantity:
                    order.order_status = OrderStatus.FILLED.value
                else:
                    order.order_status = OrderStatus.PARTIALLY_FILLED.value
                
                order.filled_quantity = execution_quantity
                order.average_price = execution_price
                order.updated_at = datetime.utcnow()
                
                # Create trade record
                self._create_trade_record(session, order, execution_quantity, execution_price)
                
                # Update position
                self._update_position(session, order.user_id, order.tradingsymbol, 
                                    order.transaction_type, execution_quantity, execution_price)
                
                session.commit()
                logger.info(f"Executed order {order_id} at ₹{execution_price}")
                return True
                
        except Exception as e:
            logger.error(f"Error executing order {order_id}: {e}")
            return False
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            with self.db_manager.get_session() as session:
                order = session.query(self.db_manager.Order).filter(
                    self.db_manager.Order.order_id == order_id
                ).first()
                
                if not order:
                    logger.error(f"Order {order_id} not found")
                    return False
                
                if order.order_status in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value]:
                    logger.warning(f"Cannot cancel order {order_id} with status {order.order_status}")
                    return False
                
                order.order_status = OrderStatus.CANCELLED.value
                order.updated_at = datetime.utcnow()
                
                # Cancel related orders (stop-loss, take-profit)
                self._cancel_related_orders(session, order_id)
                
                session.commit()
                logger.info(f"Cancelled order {order_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_user_orders(self, user_id: int, status: Optional[OrderStatus] = None) -> List[Dict]:
        """Get orders for a user."""
        try:
            with self.db_manager.get_session() as session:
                query = session.query(self.db_manager.Order).filter(
                    self.db_manager.Order.user_id == user_id
                )
                
                if status:
                    query = query.filter(self.db_manager.Order.order_status == status.value)
                
                orders = query.order_by(self.db_manager.Order.placed_at.desc()).all()
                return [self._order_to_dict(order) for order in orders]
                
        except Exception as e:
            logger.error(f"Error getting orders for user {user_id}: {e}")
            return []
    
    def get_user_positions(self, user_id: int) -> List[Dict]:
        """Get positions for a user."""
        try:
            with self.db_manager.get_session() as session:
                positions = session.query(self.db_manager.Position).filter(
                    self.db_manager.Position.user_id == user_id
                ).all()
                return [self._position_to_dict(position) for position in positions]
                
        except Exception as e:
            logger.error(f"Error getting positions for user {user_id}: {e}")
            return []
    
    def get_user_trades(self, user_id: int, days: int = 30) -> List[Dict]:
        """Get trades for a user."""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            with self.db_manager.get_session() as session:
                trades = session.query(self.db_manager.Trade).filter(
                    self.db_manager.Trade.user_id == user_id,
                    self.db_manager.Trade.trade_time >= start_date
                ).order_by(self.db_manager.Trade.trade_time.desc()).all()
                
                return [self._trade_to_dict(trade) for trade in trades]
                
        except Exception as e:
            logger.error(f"Error getting trades for user {user_id}: {e}")
            return []
    
    def _create_order_record(self, session, user_id: int, order_id: str, symbol: str,
                           order_type: OrderType, side: OrderSide, quantity: int,
                           price: Optional[float] = None, trigger_price: Optional[float] = None,
                           parent_order_id: Optional[str] = None):
        """Create order record in database."""
        order = self.db_manager.Order(
            user_id=user_id,
            order_id=order_id,
            parent_order_id=parent_order_id,
            tradingsymbol=symbol,
            exchange="NSE",
            product="CNC",
            order_type=order_type.value,
            transaction_type=side.value,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_status=OrderStatus.PENDING.value,
            placed_at=datetime.utcnow()
        )
        session.add(order)
        return order
    
    def _create_trade_record(self, session, order, execution_quantity: int, execution_price: float):
        """Create trade record in database."""
        trade_id = self._generate_trade_id()
        trade = self.db_manager.Trade(
            user_id=order.user_id,
            trade_id=trade_id,
            order_id=order.order_id,
            tradingsymbol=order.tradingsymbol,
            exchange=order.exchange,
            transaction_type=order.transaction_type,
            quantity=execution_quantity,
            price=execution_price,
            filled_quantity=execution_quantity,
            trade_time=datetime.utcnow()
        )
        session.add(trade)
        return trade
    
    def _update_position(self, session, user_id: int, symbol: str, 
                        transaction_type: str, quantity: int, price: float):
        """Update user position after trade execution."""
        try:
            position = session.query(self.db_manager.Position).filter(
                self.db_manager.Position.user_id == user_id,
                self.db_manager.Position.tradingsymbol == symbol
            ).first()
            
            if not position:
                # Create new position
                position = self.db_manager.Position(
                    user_id=user_id,
                    tradingsymbol=symbol,
                    exchange="NSE",
                    product="CNC",
                    quantity=0,
                    average_price=0,
                    last_price=price
                )
                session.add(position)
            
            if transaction_type == OrderSide.BUY.value:
                # Buy transaction
                old_quantity = position.quantity
                old_avg_price = position.average_price
                
                new_quantity = old_quantity + quantity
                new_avg_price = ((old_quantity * old_avg_price) + (quantity * price)) / new_quantity if new_quantity > 0 else 0
                
                position.quantity = new_quantity
                position.average_price = new_avg_price
                position.buy_quantity = new_quantity
                position.buy_price = new_avg_price
                position.buy_value = new_quantity * new_avg_price
                
            else:
                # Sell transaction
                position.quantity = max(0, position.quantity - quantity)
                position.sell_quantity = position.sell_quantity + quantity if position.sell_quantity else quantity
                position.sell_price = price
                position.sell_value = position.sell_quantity * price if position.sell_quantity else 0
            
            position.last_price = price
            position.updated_at = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error updating position: {e}")
    
    def _cancel_related_orders(self, session, order_id: str):
        """Cancel related orders (stop-loss, take-profit)."""
        related_orders = session.query(self.db_manager.Order).filter(
            self.db_manager.Order.parent_order_id == order_id
        ).all()
        
        for related_order in related_orders:
            if related_order.order_status == OrderStatus.PENDING.value:
                related_order.order_status = OrderStatus.CANCELLED.value
                related_order.updated_at = datetime.utcnow()
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        return f"ORD_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{datetime.utcnow().microsecond}"
    
    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        return f"TRD_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{datetime.utcnow().microsecond}"
    
    def _order_to_dict(self, order) -> Dict:
        """Convert Order object to dictionary."""
        return {
            'order_id': order.order_id,
            'tradingsymbol': order.tradingsymbol,
            'exchange': order.exchange,
            'order_type': order.order_type,
            'transaction_type': order.transaction_type,
            'quantity': order.quantity,
            'price': order.price,
            'trigger_price': order.trigger_price,
            'filled_quantity': order.filled_quantity,
            'average_price': order.average_price,
            'order_status': order.order_status,
            'placed_at': order.placed_at.isoformat() if order.placed_at else None,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None
        }
    
    def _position_to_dict(self, position) -> Dict:
        """Convert Position object to dictionary."""
        return {
            'tradingsymbol': position.tradingsymbol,
            'exchange': position.exchange,
            'quantity': position.quantity,
            'average_price': position.average_price,
            'last_price': position.last_price,
            'value': position.value,
            'pnl': position.pnl,
            'unrealised': position.unrealised,
            'realised': position.realised,
            'buy_quantity': position.buy_quantity,
            'buy_price': position.buy_price,
            'buy_value': position.buy_value,
            'sell_quantity': position.sell_quantity,
            'sell_price': position.sell_price,
            'sell_value': position.sell_value,
            'updated_at': position.updated_at.isoformat() if position.updated_at else None
        }
    
    def _trade_to_dict(self, trade) -> Dict:
        """Convert Trade object to dictionary."""
        return {
            'trade_id': trade.trade_id,
            'order_id': trade.order_id,
            'tradingsymbol': trade.tradingsymbol,
            'exchange': trade.exchange,
            'transaction_type': trade.transaction_type,
            'quantity': trade.quantity,
            'price': trade.price,
            'filled_quantity': trade.filled_quantity,
            'trade_time': trade.trade_time.isoformat() if trade.trade_time else None
        }
