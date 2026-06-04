"""
Broker Service for managing broker connections and API interactions
"""
import os
import time
import requests
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any, List

# Configure logging
logger = logging.getLogger(__name__)

try:
    from src.models.database import get_database_manager
    from src.models.models import BrokerConfiguration, Order, Trade
except ImportError:
    from models.database import get_database_manager
    from models.models import BrokerConfiguration, Order, Trade



class BrokerService:
    """Service for managing broker configurations and connections."""
    
    def __init__(self):
        self.db_manager = get_database_manager()

    def _ibkr(self):
        """The process-wide IBKR broker (single account; user_id ignored)."""
        from ..brokers.ibkr import get_ibkr_service
        return get_ibkr_service()

    def test_broker_connection(self, user_id: int = 1):
        """Test the IBKR (TWS/Gateway) connection."""
        return self._ibkr().test_connection()

    def get_broker_funds(self, user_id: int = 1):
        return self._ibkr().get_funds()

    def get_broker_holdings(self, user_id: int = 1):
        return self._ibkr().get_holdings()

    def get_broker_positions(self, user_id: int = 1):
        return self._ibkr().get_positions()

    def get_broker_orderbook(self, user_id: int = 1):
        return self._ibkr().get_orderbook()

    def get_broker_tradebook(self, user_id: int = 1):
        return self._ibkr().get_tradebook()

    def get_broker_quotes(self, user_id: int, symbols: str):
        return self._ibkr().get_quotes(symbols)

    def get_broker_history(self, user_id: int, symbol: str, resolution: str,
                           range_from: str, range_to: str):
        return self._ibkr().get_history(symbol, resolution, range_from, range_to)

    def get_broker_profile(self, user_id: int = 1):
        return self._ibkr().get_user_profile()

    # generic aliases used by some data services
    def get_quotes(self, user_id_or_symbols, symbols=None):
        syms = symbols if symbols is not None else user_id_or_symbols
        return self._ibkr().get_quotes(syms)

    def get_historical_data(self, symbol, resolution="D", range_from=None,
                            range_to=None, *args, **kwargs):
        return self._ibkr().get_history(symbol, resolution, range_from, range_to)

    def is_token_expired(self, access_token: str) -> bool:
        """Check if a JWT access token is expired."""
        if not access_token:
            return True
        
        try:
            import jwt
            import datetime
            
            # Decode JWT token without verification to get expiration
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            exp_timestamp = decoded.get('exp', 0)
            
            # Convert to datetime and check if expired
            exp_datetime = datetime.datetime.fromtimestamp(exp_timestamp)
            current_time = datetime.datetime.now()
            
            return current_time >= exp_datetime
        except Exception as e:
            logger.warning(f"Error checking token expiration: {e}")
            return True  # Assume expired if we can't check
    
    def get_broker_config(self, broker_name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get broker configuration from database."""
        with self.db_manager.get_session() as session:
            query = session.query(BrokerConfiguration).filter_by(broker_name=broker_name)
            if user_id:
                query = query.filter_by(user_id=user_id)
            else:
                query = query.filter_by(user_id=None)  # Global config
            
            config = query.first()
            if not config:
                return None
            
            # Check if token is expired
            is_expired = self.is_token_expired(config.access_token)
            
            # Return data dictionary instead of SQLAlchemy object
            is_connected = config.is_connected and not is_expired
            return {
                'id': config.id,
                'user_id': config.user_id,
                'broker_name': config.broker_name,
                'client_id': config.client_id,
                'access_token': config.access_token,
                'refresh_token': config.refresh_token,
                'api_key': config.api_key,
                'api_secret': config.api_secret,
                'redirect_url': config.redirect_url,
                'app_type': config.app_type,
                'is_active': config.is_active,
                'is_connected': is_connected,
                'is_token_expired': is_expired,
                'last_connection_test': config.last_connection_test,
                'connection_status': 'expired' if is_expired else ('connected' if is_connected else 'disconnected'),
                'error_message': config.error_message,
                'created_at': config.created_at,
                'updated_at': config.updated_at
            }
    
    def save_broker_config(self, broker_name: str, config_data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        """Save broker configuration to database."""
        with self.db_manager.get_session() as session:
            # Check if config exists within this session
            query = session.query(BrokerConfiguration).filter_by(broker_name=broker_name)
            if user_id:
                query = query.filter_by(user_id=user_id)
            else:
                query = query.filter_by(user_id=None)  # Global config
            
            existing_config = query.first()
            
            if existing_config:
                # Update existing config
                config = existing_config
            else:
                # Create new config
                config = BrokerConfiguration(
                    broker_name=broker_name,
                    user_id=user_id
                )
                session.add(config)
            
            # Map frontend field names to DB column names
            field_aliases = {
                'secret_key': 'api_secret',
                'redirect_uri': 'redirect_url',
            }
            # Apply aliases so frontend field names work
            for alias, db_field in field_aliases.items():
                if alias in config_data and db_field not in config_data:
                    config_data[db_field] = config_data[alias]

            # Only update fields that are explicitly provided (don't overwrite with empty defaults)
            updatable_fields = [
                'client_id', 'access_token', 'refresh_token', 'api_key',
                'api_secret', 'redirect_url', 'app_type', 'is_active',
                'is_connected', 'connection_status', 'error_message'
            ]
            for field in updatable_fields:
                if field in config_data and config_data[field] is not None:
                    setattr(config, field, config_data[field])
            config.updated_at = datetime.utcnow()
            
            session.commit()
            session.refresh(config)  # Refresh to get the updated object
            
            # Return data dictionary instead of SQLAlchemy object
            return {
                'id': config.id,
                'user_id': config.user_id,
                'broker_name': config.broker_name,
                'client_id': config.client_id,
                'access_token': config.access_token,
                'refresh_token': config.refresh_token,
                'api_key': config.api_key,
                'api_secret': config.api_secret,
                'redirect_url': config.redirect_url,
                'app_type': config.app_type,
                'is_active': config.is_active,
                'is_connected': config.is_connected,
                'last_connection_test': config.last_connection_test,
                'connection_status': config.connection_status,
                'error_message': config.error_message,
                'created_at': config.created_at,
                'updated_at': config.updated_at
            }
    

    def get_broker_stats(self, broker_name: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get broker statistics from database."""
        with self.db_manager.get_session() as session:
            # Get order statistics
            query = session.query(Order)
            if user_id:
                query = query.filter_by(user_id=user_id)
            
            total_orders = query.count()
            successful_orders = query.filter_by(order_status='COMPLETE').count()
            pending_orders = query.filter_by(order_status='PENDING').count()
            failed_orders = query.filter_by(order_status='REJECTED').count()
            
            # Get last order time
            last_order = query.order_by(Order.created_at.desc()).first()
            last_order_time = last_order.created_at.strftime('%Y-%m-%d %H:%M:%S') if last_order else '-'
            
            return {
                'total_orders': total_orders,
                'successful_orders': successful_orders,
                'pending_orders': pending_orders,
                'failed_orders': failed_orders,
                'last_order_time': last_order_time,
                'api_response_time': '-'
            }


def get_broker_service() -> BrokerService:
    """Get broker service instance."""
    return BrokerService()
