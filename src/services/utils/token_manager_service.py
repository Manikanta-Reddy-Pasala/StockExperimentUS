"""
Token Manager Service - Automatic token refresh and management for broker APIs
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Callable
import jwt
from src.models.database import get_database_manager
from src.models.models import BrokerConfiguration
from .cache_service import get_cache_service

logger = logging.getLogger(__name__)

class TokenManagerService:
    """Service for managing broker tokens with automatic refresh capabilities."""
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self.cache_service = get_cache_service()
        self._refresh_callbacks = {}  # Store refresh callbacks for different brokers
        self._refresh_threads = {}  # Store background refresh threads
        self._stop_refresh = {}  # Control flags for stopping refresh threads
        
    def register_refresh_callback(self, broker_name: str, callback: Callable[[int, str], Dict[str, Any]]):
        """
        Register a callback function for token refresh.
        
        Args:
            broker_name (str): Name of the broker (e.g., 'fyers')
            callback (Callable): Function that takes (user_id, refresh_token) and returns new token data
        """
        self._refresh_callbacks[broker_name] = callback
        logger.info(f"Registered refresh callback for broker: {broker_name}")
    
    def is_token_expired(self, access_token: str, buffer_minutes: int = 5) -> bool:
        """
        Check if a JWT token is expired.
        
        Args:
            access_token (str): JWT access token
            buffer_minutes (int): Buffer time in minutes before actual expiration
            
        Returns:
            bool: True if token is expired or will expire within buffer time
        """
        if not access_token:
            return True
        
        try:
            # Decode JWT token without verification to get expiration
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            exp_timestamp = decoded.get('exp', 0)
            
            if not exp_timestamp:
                logger.warning("No expiration timestamp found in token")
                return False  # Don't assume expired if we can't determine expiration
            
            # Convert to datetime and check if expired
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            current_time = datetime.now()
            
            # Add buffer time to avoid edge cases
            buffer_time = timedelta(minutes=buffer_minutes)
            return current_time >= (exp_datetime - buffer_time)
            
        except Exception as e:
            logger.warning(f"Error checking token expiration: {e}")
            return False  # Don't assume expired if we can't check
    
    def get_token_expiry_time(self, access_token: str) -> Optional[datetime]:
        """
        Get the expiration time of a JWT token.
        
        Args:
            access_token (str): JWT access token
            
        Returns:
            datetime: Expiration time or None if can't determine
        """
        if not access_token:
            return None
        
        try:
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            exp_timestamp = decoded.get('exp', 0)
            
            if exp_timestamp:
                return datetime.fromtimestamp(exp_timestamp)
            
        except Exception as e:
            logger.warning(f"Error getting token expiry time: {e}")
        
        return None
    
    def get_valid_token(self, user_id: int, broker_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a valid (non-expired) token for a user and broker.
        Will attempt to refresh if expired.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
            
        Returns:
            Dict: Token data with access_token, refresh_token, etc. or None if not available
        """
        # First check cache
        cached_token = self.cache_service.get_cached_token(user_id, broker_name)
        if cached_token and not self.is_token_expired(cached_token.get('access_token', '')):
            logger.debug(f"Using cached valid token for user {user_id}, broker {broker_name}")
            return cached_token
        
        # Get from database
        with self.db_manager.get_session() as session:
            config = session.query(BrokerConfiguration).filter_by(
                broker_name=broker_name, 
                user_id=user_id
            ).first()
            
            if not config or not config.access_token:
                logger.warning(f"No token found for user {user_id}, broker {broker_name}")
                return None
            
            token_data = {
                'access_token': config.access_token,
                'refresh_token': config.refresh_token,
                'client_id': config.client_id,
                'api_secret': config.api_secret,
                'redirect_url': config.redirect_url,
                'is_connected': config.is_connected,
                'connection_status': config.connection_status
            }
            
            # Check if token is expired
            if self.is_token_expired(config.access_token):
                logger.info(f"Token expired for user {user_id}, broker {broker_name}. Attempting refresh...")
                
                # Try to refresh the token
                refreshed_token = self.refresh_token(user_id, broker_name, config.refresh_token)
                if refreshed_token:
                    # Update database with new token
                    self._update_token_in_db(session, config, refreshed_token)
                    token_data.update(refreshed_token)
                else:
                    logger.error(f"Failed to refresh token for user {user_id}, broker {broker_name}")
                    return None
            
            # Cache the valid token
            expiry_time = self.get_token_expiry_time(token_data['access_token'])
            if expiry_time:
                cache_ttl = int((expiry_time - datetime.now()).total_seconds())
                if cache_ttl > 0:
                    self.cache_service.cache_token(user_id, broker_name, token_data, cache_ttl)
            
            return token_data
    
    def refresh_token(self, user_id: int, broker_name: str, refresh_token: str = None) -> Optional[Dict[str, Any]]:
        """
        Refresh a broker token using the refresh callback.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
            refresh_token (str): Refresh token (optional, will get from DB if not provided)
            
        Returns:
            Dict: New token data or None if refresh failed
        """
        if broker_name not in self._refresh_callbacks:
            logger.error(f"No refresh callback registered for broker: {broker_name}")
            return None
        
        # Get refresh token from database if not provided
        if not refresh_token:
            with self.db_manager.get_session() as session:
                config = session.query(BrokerConfiguration).filter_by(
                    broker_name=broker_name, 
                    user_id=user_id
                ).first()
                
                if not config:
                    logger.error(f"No broker configuration found for user {user_id}, broker {broker_name}")
                    return None
                
                refresh_token = config.refresh_token
        
        try:
            # Call the registered refresh callback (pass empty string if no refresh_token,
            # let the callback handle missing-token logic and mark reauth_required)
            callback = self._refresh_callbacks[broker_name]
            new_token_data = callback(user_id, refresh_token or '')
            
            if new_token_data and new_token_data.get('access_token'):
                logger.info(f"Successfully refreshed token for user {user_id}, broker {broker_name}")
                return new_token_data
            else:
                logger.error(f"Refresh callback returned invalid data for user {user_id}, broker {broker_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error refreshing token for user {user_id}, broker {broker_name}: {e}")
            return None
    
    def _update_token_in_db(self, session, config: BrokerConfiguration, new_token_data: Dict[str, Any]):
        """Update token data in database."""
        try:
            if 'access_token' in new_token_data:
                config.access_token = new_token_data['access_token']
            if 'refresh_token' in new_token_data:
                config.refresh_token = new_token_data['refresh_token']
            if 'is_connected' in new_token_data:
                config.is_connected = new_token_data['is_connected']
            if 'connection_status' in new_token_data:
                config.connection_status = new_token_data['connection_status']
            
            config.updated_at = datetime.utcnow()
            session.commit()
            
            logger.info(f"Updated token in database for user {config.user_id}, broker {config.broker_name}")
            
        except Exception as e:
            logger.error(f"Error updating token in database: {e}")
            session.rollback()
            raise
    
    def start_auto_refresh(self, user_id: int, broker_name: str, check_interval_minutes: int = 30):
        """
        Start automatic token refresh for a user and broker.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
            check_interval_minutes (int): How often to check for token expiration
        """
        thread_key = f"{broker_name}:{user_id}"
        
        # Stop existing thread if running
        if thread_key in self._refresh_threads:
            self.stop_auto_refresh(user_id, broker_name)
        
        # Create stop flag
        self._stop_refresh[thread_key] = False
        
        def refresh_worker():
            logger.info(f"Started auto-refresh thread for user {user_id}, broker {broker_name}")
            
            while not self._stop_refresh.get(thread_key, True):
                try:
                    # Get current token
                    token_data = self.get_valid_token(user_id, broker_name)
                    
                    if token_data:
                        # Check if token will expire soon (within next check interval)
                        expiry_time = self.get_token_expiry_time(token_data['access_token'])
                        if expiry_time:
                            time_until_expiry = expiry_time - datetime.now()
                            check_interval = timedelta(minutes=check_interval_minutes)
                            
                            if time_until_expiry <= check_interval:
                                logger.info(f"Token for user {user_id}, broker {broker_name} will expire soon. Refreshing...")
                                self.refresh_token(user_id, broker_name)
                    
                    # Wait for next check
                    time.sleep(check_interval_minutes * 60)
                    
                except Exception as e:
                    logger.error(f"Error in auto-refresh thread for user {user_id}, broker {broker_name}: {e}")
                    time.sleep(60)  # Wait 1 minute before retrying
            
            logger.info(f"Stopped auto-refresh thread for user {user_id}, broker {broker_name}")
        
        # Start the thread
        thread = threading.Thread(target=refresh_worker, daemon=True)
        thread.start()
        self._refresh_threads[thread_key] = thread
        
        logger.info(f"Started auto-refresh for user {user_id}, broker {broker_name}")
    
    def stop_auto_refresh(self, user_id: int, broker_name: str):
        """
        Stop automatic token refresh for a user and broker.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
        """
        thread_key = f"{broker_name}:{user_id}"
        
        if thread_key in self._stop_refresh:
            self._stop_refresh[thread_key] = True
        
        if thread_key in self._refresh_threads:
            thread = self._refresh_threads[thread_key]
            if thread.is_alive():
                thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
            
            del self._refresh_threads[thread_key]
        
        if thread_key in self._stop_refresh:
            del self._stop_refresh[thread_key]
        
        logger.info(f"Stopped auto-refresh for user {user_id}, broker {broker_name}")
    
    def invalidate_user_tokens(self, user_id: int, broker_name: str = None):
        """
        Invalidate all cached tokens for a user.
        
        Args:
            user_id (int): User ID
            broker_name (str): Specific broker name, or None for all brokers
        """
        if broker_name:
            self.cache_service.invalidate_token(user_id, broker_name)
            logger.info(f"Invalidated cached token for user {user_id}, broker {broker_name}")
        else:
            # Invalidate for all known brokers
            for broker in self._refresh_callbacks.keys():
                self.cache_service.invalidate_token(user_id, broker)
            logger.info(f"Invalidated all cached tokens for user {user_id}")
    
    def get_token_status(self, user_id: int, broker_name: str) -> Dict[str, Any]:
        """
        Get detailed token status for a user and broker.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
            
        Returns:
            Dict: Token status information
        """
        token_data = self.get_valid_token(user_id, broker_name)
        
        if not token_data:
            return {
                'has_token': False,
                'is_valid': False,
                'is_expired': True,
                'expires_at': None,
                'time_until_expiry': None,
                'auto_refresh_active': False
            }
        
        access_token = token_data.get('access_token', '')
        expiry_time = self.get_token_expiry_time(access_token)
        is_expired = self.is_token_expired(access_token)
        
        time_until_expiry = None
        if expiry_time:
            time_until_expiry = expiry_time - datetime.now()
        
        thread_key = f"{broker_name}:{user_id}"
        auto_refresh_active = thread_key in self._refresh_threads and self._refresh_threads[thread_key].is_alive()
        
        return {
            'has_token': True,
            'is_valid': not is_expired,
            'is_expired': is_expired,
            'expires_at': expiry_time.isoformat() if expiry_time else None,
            'time_until_expiry': str(time_until_expiry) if time_until_expiry else None,
            'auto_refresh_active': auto_refresh_active,
            'cached': self.cache_service.exists(f"token:{broker_name}:{user_id}")
        }


# Global token manager instance
_token_manager = None

def get_token_manager() -> TokenManagerService:
    """Get global token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManagerService()
    return _token_manager
