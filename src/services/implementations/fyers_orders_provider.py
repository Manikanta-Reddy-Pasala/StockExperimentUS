"""
FYERS Orders Provider Implementation

Implements the IOrdersProvider interface for FYERS broker.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from ..interfaces.orders_interface import IOrdersProvider, Order, OrderType, OrderSide, OrderStatus
try:
    from ..brokers.fyers_service import get_fyers_service
except ImportError:
    from src.services.brokers.fyers_service import get_fyers_service

logger = logging.getLogger(__name__)


class FyersOrdersProvider(IOrdersProvider):
    """FYERS implementation of orders provider."""
    
    def __init__(self):
        self.fyers_service = get_fyers_service()
    
    def get_orders_history(self, user_id: int, start_date: datetime = None, 
                          end_date: datetime = None, limit: int = 100) -> Dict[str, Any]:
        """Get orders history using FYERS API."""
        try:
            orderbook_data = self.fyers_service.orderbook(user_id)
            
            if orderbook_data.get('status') != 'success':
                return {
                    'success': False,
                    'error': orderbook_data.get('message', 'Failed to fetch orders'),
                    'data': [],
                    'total': 0,
                    'last_updated': datetime.now().isoformat()
                }
            
            orders = orderbook_data.get('data', [])
            
            # Process and format orders
            processed_orders = []
            for order_data in orders[:limit]:
                order = Order(
                    order_id=order_data.get('id', ''),
                    symbol=order_data.get('symbol', ''),
                    side=OrderSide.BUY if order_data.get('side') == '1' else OrderSide.SELL,
                    order_type=OrderType.LIMIT if order_data.get('type') == '1' else OrderType.MARKET,
                    quantity=order_data.get('qty', 0),
                    price=order_data.get('limitPrice', 0)
                )
                
                order.status = self._map_order_status(order_data.get('status', ''))
                order.filled_quantity = order_data.get('filledQty', 0)
                order.remaining_quantity = order_data.get('remainingQty', 0)
                order.product = order_data.get('product', '')
                
                # Parse order time
                if order_data.get('orderDateTime'):
                    try:
                        order.order_time = datetime.fromisoformat(order_data['orderDateTime'])
                    except:
                        order.order_time = datetime.now()
                
                processed_orders.append(order.to_dict())
            
            return {
                'success': True,
                'data': processed_orders,
                'total': len(processed_orders),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching orders history for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'total': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def get_pending_orders(self, user_id: int) -> Dict[str, Any]:
        """Get pending orders using FYERS API."""
        try:
            orderbook_data = self.fyers_service.orderbook(user_id)
            
            if not orderbook_data.get('success'):
                return {
                    'success': False,
                    'error': orderbook_data.get('error', 'Failed to fetch pending orders'),
                    'data': [],
                    'total': 0,
                    'last_updated': datetime.now().isoformat()
                }
            
            orders = orderbook_data['data'].get('orderBook', [])
            
            # Filter pending orders
            pending_orders = []
            for order_data in orders:
                status = order_data.get('status', '')
                if status in ['1', '2', '3']:  # Pending statuses in FYERS
                    order = Order(
                        order_id=order_data.get('id', ''),
                        symbol=order_data.get('symbol', ''),
                        side=OrderSide.BUY if order_data.get('side') == '1' else OrderSide.SELL,
                        order_type=OrderType.LIMIT if order_data.get('type') == '1' else OrderType.MARKET,
                        quantity=order_data.get('qty', 0),
                        price=order_data.get('limitPrice', 0)
                    )
                    
                    order.status = self._map_order_status(status)
                    order.filled_quantity = order_data.get('filledQty', 0)
                    order.remaining_quantity = order_data.get('remainingQty', 0)
                    order.product = order_data.get('product', '')
                    
                    if order_data.get('orderDateTime'):
                        try:
                            order.order_time = datetime.fromisoformat(order_data['orderDateTime'])
                        except:
                            order.order_time = datetime.now()
                    
                    pending_orders.append(order.to_dict())
            
            return {
                'success': True,
                'data': pending_orders,
                'total': len(pending_orders),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching pending orders for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'total': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def get_trades_history(self, user_id: int, start_date: datetime = None, 
                          end_date: datetime = None, limit: int = 100) -> Dict[str, Any]:
        """Get trades history using FYERS API."""
        try:
            tradebook_data = self.fyers_service.tradebook(user_id)
            
            if tradebook_data.get('status') != 'success':
                return {
                    'success': False,
                    'error': tradebook_data.get('message', 'Failed to fetch trades'),
                    'data': [],
                    'total': 0,
                    'last_updated': datetime.now().isoformat()
                }
            
            trades = tradebook_data.get('data', [])
            
            # Process and format trades
            processed_trades = []
            for trade_data in trades[:limit]:
                trade = {
                    'id': trade_data.get('id', ''),
                    'symbol': trade_data.get('symbol', ''),
                    'symbol_name': trade_data.get('symbol_name', ''),
                    'side': 'BUY' if trade_data.get('side') == '1' else 'SELL',
                    'quantity': trade_data.get('qty', 0),
                    'price': trade_data.get('tradedPrice', 0),
                    'trade_time': trade_data.get('tradeDateTime', ''),
                    'order_id': trade_data.get('orderNumber', ''),
                    'product': trade_data.get('product', ''),
                    'pnl': trade_data.get('pnl', 0),
                    'brokerage': trade_data.get('brokerage', 0),
                    'exchange': trade_data.get('exchange', '')
                }
                processed_trades.append(trade)
            
            return {
                'success': True,
                'data': processed_trades,
                'total': len(processed_trades),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching trades history for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'total': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def place_order(self, user_id: int, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Place an order using FYERS API."""
        try:
            # Map order data to FYERS format
            fyers_order = {
                'symbol': order_data.get('symbol'),
                'qty': order_data.get('quantity'),
                'type': '1' if order_data.get('type') == 'limit' else '2',  # 1=limit, 2=market
                'side': '1' if order_data.get('side') == 'buy' else '-1',  # 1=buy, -1=sell
                'productType': order_data.get('product', 'INTRADAY'),
                'limitPrice': order_data.get('price', 0),
                'stopPrice': order_data.get('stop_price', 0),
                'validity': order_data.get('validity', 'DAY'),
                'disclosedQty': order_data.get('disclosed_quantity', 0),
                'offlineOrder': 'False'
            }
            
            result = self.fyers_service.placeorder(user_id, fyers_order['symbol'], str(fyers_order['qty']), fyers_order['side'], fyers_order['productType'], fyers_order['limitPrice'], fyers_order['stopPrice'], fyers_order['validity'])
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'order_id': result.get('data', {}).get('id', ''),
                    'message': 'Order placed successfully'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Failed to place order')
                }
                
        except Exception as e:
            logger.error(f"Error placing order for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def modify_order(self, user_id: int, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Modify an order using FYERS API."""
        try:
            # Map order data to FYERS format
            fyers_order = {
                'id': order_id,
                'qty': order_data.get('quantity'),
                'type': '1' if order_data.get('type') == 'limit' else '2',
                'limitPrice': order_data.get('price', 0),
                'stopPrice': order_data.get('stop_price', 0)
            }
            
            result = self.fyers_service.modifyorder(user_id, order_id, fyers_order.get('type', 1), fyers_order.get('limitPrice', 0), fyers_order.get('qty', 0))
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'message': 'Order modified successfully'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Failed to modify order')
                }
                
        except Exception as e:
            logger.error(f"Error modifying order {order_id} for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_order(self, user_id: int, order_id: str) -> Dict[str, Any]:
        """Cancel an order using FYERS API."""
        try:
            result = self.fyers_service.cancelorder(user_id, order_id)
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'message': 'Order cancelled successfully'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Failed to cancel order')
                }
                
        except Exception as e:
            logger.error(f"Error cancelling order {order_id} for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_order_details(self, user_id: int, order_id: str) -> Dict[str, Any]:
        """Get order details using FYERS API."""
        try:
            orderbook_data = self.fyers_service.orderbook(user_id)
            
            if orderbook_data.get('status') != 'success':
                return {
                    'success': False,
                    'error': orderbook_data.get('message', 'Failed to fetch order details'),
                    'data': {},
                    'last_updated': datetime.now().isoformat()
                }
            
            orders = orderbook_data.get('data', [])
            
            # Find the specific order
            for order_data in orders:
                if order_data.get('id') == order_id:
                    order = Order(
                        order_id=order_data.get('id', ''),
                        symbol=order_data.get('symbol', ''),
                        side=OrderSide.BUY if order_data.get('side') == '1' else OrderSide.SELL,
                        order_type=OrderType.LIMIT if order_data.get('type') == '1' else OrderType.MARKET,
                        quantity=order_data.get('qty', 0),
                        price=order_data.get('limitPrice', 0)
                    )
                    
                    order.status = self._map_order_status(order_data.get('status', ''))
                    order.filled_quantity = order_data.get('filledQty', 0)
                    order.remaining_quantity = order_data.get('remainingQty', 0)
                    order.product = order_data.get('product', '')
                    
                    if order_data.get('orderDateTime'):
                        try:
                            order.order_time = datetime.fromisoformat(order_data['orderDateTime'])
                        except:
                            order.order_time = datetime.now()
                    
                    return {
                        'success': True,
                        'data': order.to_dict(),
                        'last_updated': datetime.now().isoformat()
                    }
            
            return {
                'success': False,
                'error': 'Order not found',
                'data': {},
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching order details {order_id} for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {},
                'last_updated': datetime.now().isoformat()
            }
    
    def _map_order_status(self, fyers_status: str) -> OrderStatus:
        """Map FYERS order status to our OrderStatus enum."""
        status_mapping = {
            '1': OrderStatus.OPEN,
            '2': OrderStatus.PENDING,
            '3': OrderStatus.PENDING,
            '4': OrderStatus.FILLED,
            '5': OrderStatus.CANCELLED,
            '6': OrderStatus.REJECTED
        }
        return status_mapping.get(fyers_status, OrderStatus.PENDING)