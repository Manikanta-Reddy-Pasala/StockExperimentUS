"""
Order Synchronization Service

Handles efficient syncing of orders between Fyers API and local database.
Uses Redis for caching and PostgreSQL for persistent storage.
"""

from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
import logging
import json
from enum import Enum

from src.models.database import get_database_manager
from src.models.models import Order
from src.services.utils.cache_service import get_cache_service
from src.services.core.broker_service import get_broker_service

logger = logging.getLogger(__name__)


class OrderSyncService:
    """Service to sync orders between Fyers API and database efficiently."""

    def __init__(self):
        """Initialize the order sync service."""
        self.db_manager = get_database_manager()
        self.cache_service = get_cache_service()
        self.broker_service = get_broker_service()

        # Cache keys
        self.ORDERS_CACHE_KEY = "user_orders:{user_id}"
        self.LAST_SYNC_KEY = "last_order_sync:{user_id}"
        self.ORDERS_HASH_KEY = "orders_hash:{user_id}"

        # Cache expiration times
        self.ORDERS_CACHE_TTL = 300  # 5 minutes
        self.SYNC_INTERVAL = 60  # 1 minute minimum between syncs

    def get_user_orders(self, user_id: int, force_refresh: bool = False) -> List[Dict]:
        """
        Get user orders with intelligent caching.

        Args:
            user_id: User ID
            force_refresh: Force refresh from API

        Returns:
            List of order dictionaries
        """
        try:
            # Check if we should use cached data
            if not force_refresh and self._should_use_cache(user_id):
                cached_orders = self._get_cached_orders(user_id)
                if cached_orders is not None:
                    logger.info(f"Returning cached orders for user {user_id}")
                    return cached_orders

            # Sync with Fyers API
            synced_orders = self._sync_orders_from_fyers(user_id)

            # Cache the results
            self._cache_orders(user_id, synced_orders)

            return synced_orders

        except Exception as e:
            logger.error(f"Error getting user orders: {e}")
            # Try to return cached data as fallback
            cached_orders = self._get_cached_orders(user_id)
            return cached_orders if cached_orders is not None else []

    def _sync_orders_from_fyers(self, user_id: int) -> List[Dict]:
        """Sync orders from Fyers API with database."""
        try:
            logger.info(f"Syncing orders from Fyers for user {user_id}")

            # Get current orders from database
            db_orders = self._get_db_orders(user_id)
            db_order_ids = {order['order_id'] for order in db_orders}

            # Fetch from Fyers API
            fyers_result = self.broker_service.get_fyers_orderbook(user_id)

            # Check if Fyers API call was successful
            if fyers_result.get('code') != 200 or fyers_result.get('s') != 'ok':
                error_msg = fyers_result.get('message', 'Unknown error')
                logger.warning(f"Fyers API call failed for user {user_id}: {error_msg}")
                return db_orders  # Return existing DB orders

            # Parse Fyers orders
            fyers_orders = self._parse_fyers_orders(fyers_result)

            # Determine what needs to be synced
            new_orders = []
            updated_orders = []
            stale_orders = []

            # Get order IDs from Fyers response
            fyers_order_ids = {order.get('order_id') for order in fyers_orders if order.get('order_id')}

            for fyers_order in fyers_orders:
                order_id = fyers_order.get('order_id')
                if not order_id:
                    continue

                if order_id in db_order_ids:
                    # Check if order needs updating
                    db_order = next((o for o in db_orders if o['order_id'] == order_id), None)
                    if db_order and self._order_needs_update(db_order, fyers_order):
                        updated_orders.append(fyers_order)
                else:
                    # New order
                    new_orders.append(fyers_order)

            # Find orders that exist in DB but not in Fyers response (stale orders)
            for db_order in db_orders:
                db_order_id = db_order.get('order_id')
                if db_order_id and db_order_id not in fyers_order_ids:
                    # Order exists in DB but not in broker - mark as stale/removed
                    stale_order = db_order.copy()
                    stale_order['status'] = 'CANCELLED'  # Mark as cancelled since it's no longer on broker
                    stale_order['updated_at'] = datetime.utcnow().isoformat()
                    stale_orders.append(stale_order)
                    logger.info(f"Found stale order {db_order_id} - marking as cancelled")

            # Update database with all changes including stale orders
            if new_orders or updated_orders or stale_orders:
                self._update_database(user_id, new_orders, updated_orders, stale_orders)
                logger.info(f"Synced {len(new_orders)} new orders, {len(updated_orders)} updated orders, and {len(stale_orders)} stale orders for user {user_id}")

            # Update sync timestamp
            self._update_last_sync(user_id)

            # Return fresh data from database
            return self._get_db_orders(user_id)

        except Exception as e:
            logger.error(f"Error syncing orders from Fyers: {e}")
            return self._get_db_orders(user_id)

    def _get_db_orders(self, user_id: int) -> List[Dict]:
        """Get orders from database."""
        try:
            with self.db_manager.get_session() as session:
                orders = session.query(Order).filter(
                    Order.user_id == user_id,
                    Order.is_mock_order != True
                ).order_by(
                    Order.placed_at.desc()
                ).all()

                return [self._db_order_to_dict(order) for order in orders]

        except Exception as e:
            logger.error(f"Error getting orders from database: {e}")
            return []

    def _parse_fyers_orders(self, fyers_data: Dict) -> List[Dict]:
        """Parse Fyers API response into standardized order format."""
        try:
            if isinstance(fyers_data, dict):
                raw_orders = fyers_data.get('orderBook', [])
            elif isinstance(fyers_data, list):
                raw_orders = fyers_data
            else:
                logger.warning(f"Unexpected Fyers data format: {type(fyers_data)}")
                return []

            standardized_orders = []

            for raw_order in raw_orders:
                try:
                    standardized_order = {
                        'order_id': raw_order.get('id', ''),
                        'symbol': raw_order.get('symbol', ''),
                        'type': raw_order.get('type', ''),
                        'transaction': raw_order.get('side', ''),
                        'quantity': int(raw_order.get('qty', 0)),
                        'filled': int(raw_order.get('filledQty', 0)),
                        'status': self._map_fyers_status(raw_order.get('status', '')),
                        'price': float(raw_order.get('limitPrice', 0)) or float(raw_order.get('stopPrice', 0)) or 0,
                        'average_price': float(raw_order.get('avgPrice', 0)),
                        'created_at': raw_order.get('orderDateTime', ''),
                        'product_type': raw_order.get('productType', ''),
                        'remaining_quantity': int(raw_order.get('remainingQuantity', 0)),
                        'exchange': raw_order.get('ex', 'NSE'),
                        'trigger_price': float(raw_order.get('stopPrice', 0)),
                        'disclosed_quantity': int(raw_order.get('disclosedQty', 0)),
                        'validity': raw_order.get('validity', ''),
                        'variety': raw_order.get('type', ''),
                        'tag': raw_order.get('tag', ''),
                        'placed_by': raw_order.get('pan', ''),
                        'parent_order_id': raw_order.get('parentId', ''),
                        'exchange_order_id': raw_order.get('exchOrdId', ''),
                        'status_message': raw_order.get('message', ''),
                        'updated_at': datetime.utcnow().isoformat()
                    }

                    if standardized_order['order_id']:  # Only add orders with valid IDs
                        standardized_orders.append(standardized_order)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing Fyers order {raw_order}: {e}")
                    continue

            return standardized_orders

        except Exception as e:
            logger.error(f"Error parsing Fyers orders: {e}")
            return []

    def _map_fyers_status(self, fyers_status: str) -> str:
        """Map Fyers order status to standardized status."""
        status_map = {
            '1': 'PENDING',     # Pending
            '2': 'PLACED',      # Placed/Open
            '3': 'COMPLETE',    # Executed/Filled
            '4': 'COMPLETE',    # Complete
            '5': 'CANCELLED',   # Cancelled
            '6': 'REJECTED',    # Rejected
            '7': 'PARTIAL',     # Partially filled
            '8': 'MODIFY_PENDING', # Modify pending
            '9': 'CANCEL_PENDING', # Cancel pending
        }

        # Handle both numeric and string status
        return status_map.get(str(fyers_status), str(fyers_status).upper())

    def _order_needs_update(self, db_order: Dict, fyers_order: Dict) -> bool:
        """Check if database order needs updating based on Fyers data."""
        # Key fields that would indicate an order update
        check_fields = ['status', 'filled', 'average_price', 'remaining_quantity']

        for field in check_fields:
            if db_order.get(field) != fyers_order.get(field):
                return True

        return False

    def _update_database(self, user_id: int, new_orders: List[Dict], updated_orders: List[Dict], stale_orders: List[Dict] = None):
        """Update database with new, updated, and stale orders."""
        try:
            with self.db_manager.get_session() as session:
                # Insert new orders
                for order_data in new_orders:
                    db_order = self._create_db_order(user_id, order_data)
                    session.add(db_order)

                # Update existing orders
                for order_data in updated_orders:
                    order_id = order_data['order_id']
                    db_order = session.query(Order).filter(
                        Order.order_id == order_id,
                        Order.user_id == user_id
                    ).first()

                    if db_order:
                        self._update_db_order(db_order, order_data)

                # Handle stale orders (orders that exist in DB but not on broker)
                if stale_orders:
                    for stale_order_data in stale_orders:
                        order_id = stale_order_data['order_id']
                        db_order = session.query(Order).filter(
                            Order.order_id == order_id,
                            Order.user_id == user_id
                        ).first()

                        if db_order and not db_order.is_mock_order:
                            # Mark as cancelled since it no longer exists on broker
                            db_order.order_status = 'CANCELLED'
                            db_order.status_message = 'Order not found on broker - marked as cancelled'
                            db_order.updated_at = datetime.utcnow()
                            logger.info(f"Updated stale order {order_id} status to CANCELLED")

                session.commit()

        except Exception as e:
            logger.error(f"Error updating database: {e}")
            raise

    def _create_db_order(self, user_id: int, order_data: Dict):
        """Create database order from standardized order data."""
        return Order(
            user_id=user_id,
            order_id=order_data['order_id'],
            parent_order_id=order_data.get('parent_order_id'),
            exchange_order_id=order_data.get('exchange_order_id'),
            tradingsymbol=order_data['symbol'],
            exchange=order_data.get('exchange', 'NSE'),
            product=order_data.get('product_type', 'CNC'),
            order_type=order_data['type'],
            transaction_type=order_data['transaction'],
            quantity=order_data['quantity'],
            disclosed_quantity=order_data.get('disclosed_quantity', 0),
            price=order_data.get('price', 0),
            trigger_price=order_data.get('trigger_price', 0),
            average_price=order_data.get('average_price', 0),
            filled_quantity=order_data.get('filled', 0),
            pending_quantity=order_data.get('remaining_quantity', 0),
            order_status=order_data['status'],
            status_message=order_data.get('status_message', ''),
            tag=order_data.get('tag', ''),
            placed_at=self._parse_datetime(order_data.get('created_at')),
            placed_by=order_data.get('placed_by', ''),
            variety=order_data.get('variety', ''),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _update_db_order(self, db_order, order_data: Dict):
        """Update existing database order with new data."""
        db_order.order_status = order_data['status']
        db_order.filled_quantity = order_data.get('filled', 0)
        db_order.pending_quantity = order_data.get('remaining_quantity', 0)
        db_order.average_price = order_data.get('average_price', 0)
        db_order.status_message = order_data.get('status_message', '')
        db_order.updated_at = datetime.utcnow()

    def _parse_datetime(self, dt_string: str) -> Optional[datetime]:
        """Parse datetime string from Fyers format."""
        if not dt_string:
            return None

        try:
            # Try different formats
            formats = [
                '%d-%b-%Y %H:%M:%S',
                '%Y-%m-%d %H:%M:%S',
                '%d/%m/%Y %H:%M:%S'
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(dt_string, fmt)
                except ValueError:
                    continue

            logger.warning(f"Could not parse datetime: {dt_string}")
            return datetime.utcnow()  # Fallback to current time

        except Exception as e:
            logger.warning(f"Error parsing datetime {dt_string}: {e}")
            return datetime.utcnow()

    def _should_use_cache(self, user_id: int) -> bool:
        """Check if we should use cached data or refresh from API."""
        try:
            last_sync_str = self.cache_service.get(self.LAST_SYNC_KEY.format(user_id=user_id))
            if not last_sync_str:
                return False

            last_sync = datetime.fromisoformat(last_sync_str)
            time_since_sync = datetime.utcnow() - last_sync

            # Use cache if last sync was within interval
            return time_since_sync.total_seconds() < self.SYNC_INTERVAL

        except Exception as e:
            logger.warning(f"Error checking cache validity: {e}")
            return False

    def _get_cached_orders(self, user_id: int) -> Optional[List[Dict]]:
        """Get orders from Redis cache."""
        try:
            cache_key = self.ORDERS_CACHE_KEY.format(user_id=user_id)
            cached_data = self.cache_service.get(cache_key)

            if cached_data:
                return json.loads(cached_data)
            return None

        except Exception as e:
            logger.warning(f"Error getting cached orders: {e}")
            return None

    def _cache_orders(self, user_id: int, orders: List[Dict]):
        """Cache orders in Redis."""
        try:
            cache_key = self.ORDERS_CACHE_KEY.format(user_id=user_id)
            self.cache_service.set(
                cache_key,
                json.dumps(orders, default=str),
                expire_seconds=self.ORDERS_CACHE_TTL
            )

        except Exception as e:
            logger.warning(f"Error caching orders: {e}")

    def _update_last_sync(self, user_id: int):
        """Update last sync timestamp."""
        try:
            sync_key = self.LAST_SYNC_KEY.format(user_id=user_id)
            self.cache_service.set(
                sync_key,
                datetime.utcnow().isoformat(),
                expire_seconds=self.ORDERS_CACHE_TTL * 2  # Keep sync time longer than cache
            )

        except Exception as e:
            logger.warning(f"Error updating last sync time: {e}")

    def _db_order_to_dict(self, order) -> Dict:
        """Convert database Order object to dictionary for API response."""
        return {
            'order_id': order.order_id,
            'symbol': order.tradingsymbol,
            'type': order.order_type,
            'transaction': order.transaction_type,
            'quantity': order.quantity,
            'filled': order.filled_quantity or 0,
            'status': order.order_status,
            'price': order.price or 0,
            'average_price': order.average_price or 0,
            'created_at': order.placed_at.strftime('%d-%b-%Y %H:%M:%S') if order.placed_at else '',
            'product_type': order.product,
            'remaining_quantity': order.pending_quantity or 0,
            'exchange': order.exchange,
            'trigger_price': order.trigger_price or 0,
            'disclosed_quantity': order.disclosed_quantity or 0,
            'variety': order.variety,
            'tag': order.tag or '',
            'placed_by': order.placed_by or '',
            'parent_order_id': order.parent_order_id or '',
            'exchange_order_id': order.exchange_order_id or '',
            'status_message': order.status_message or '',
            'updated_at': order.updated_at.isoformat() if order.updated_at else ''
        }

    def clear_user_cache(self, user_id: int):
        """Clear cached data for a user (useful for testing or manual refresh)."""
        try:
            keys_to_clear = [
                self.ORDERS_CACHE_KEY.format(user_id=user_id),
                self.LAST_SYNC_KEY.format(user_id=user_id),
                self.ORDERS_HASH_KEY.format(user_id=user_id)
            ]

            for key in keys_to_clear:
                self.cache_service.delete(key)

            logger.info(f"Cleared cache for user {user_id}")

        except Exception as e:
            logger.warning(f"Error clearing cache for user {user_id}: {e}")


# Singleton pattern for service
_order_sync_service = None

def get_order_sync_service() -> OrderSyncService:
    """Get the order sync service singleton."""
    global _order_sync_service
    if _order_sync_service is None:
        _order_sync_service = OrderSyncService()
    return _order_sync_service