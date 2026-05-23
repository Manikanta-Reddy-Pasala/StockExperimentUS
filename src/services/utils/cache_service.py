"""
Cache Service - Dragonfly-based caching for tokens, API responses, and session data
"""
import json
import logging
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import redis
import os

logger = logging.getLogger(__name__)

class CacheService:
    """Dragonfly-based cache service for the trading system."""
    
    def __init__(self, dragonfly_url: str = None):
        """
        Initialize Dragonfly cache service.
        
        Args:
            dragonfly_url (str, optional): Dragonfly connection URL
        """
        self.dragonfly_url = dragonfly_url or os.environ.get('DRAGONFLY_URL', 'redis://localhost:6379/0')
        self.redis_client = None
        self._connect()
    
    def _connect(self):
        """Connect to Dragonfly server."""
        try:
            self.redis_client = redis.from_url(self.dragonfly_url, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            logger.info("Successfully connected to Dragonfly")
        except Exception as e:
            logger.warning(f"Failed to connect to Dragonfly: {e}. Cache operations will be disabled.")
            self.redis_client = None
    
    def is_available(self) -> bool:
        """Check if Dragonfly is available."""
        return self.redis_client is not None
    
    def set(self, key: str, value: Any, expire_seconds: int = None) -> bool:
        """
        Set a key-value pair in cache.
        
        Args:
            key (str): Cache key
            value (Any): Value to cache (will be JSON serialized)
            expire_seconds (int, optional): Expiration time in seconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            # Serialize value to JSON
            serialized_value = json.dumps(value, default=str)
            
            if expire_seconds:
                result = self.redis_client.setex(key, expire_seconds, serialized_value)
            else:
                result = self.redis_client.set(key, serialized_value)
            
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.
        
        Args:
            key (str): Cache key
            
        Returns:
            Any: Cached value or None if not found
        """
        if not self.is_available():
            return None
        
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            # Deserialize from JSON
            return json.loads(value)
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.
        
        Args:
            key (str): Cache key
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            result = self.redis_client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.
        
        Args:
            key (str): Cache key
            
        Returns:
            bool: True if key exists, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {e}")
            return False
    
    def get_ttl(self, key: str) -> int:
        """
        Get time to live for a key.
        
        Args:
            key (str): Cache key
            
        Returns:
            int: TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        if not self.is_available():
            return -2
        
        try:
            return self.redis_client.ttl(key)
        except Exception as e:
            logger.error(f"Error getting TTL for cache key {key}: {e}")
            return -2
    
    # Token-specific cache methods
    def cache_token(self, user_id: int, broker_name: str, token_data: Dict[str, Any], expire_seconds: int = 7200) -> bool:
        """
        Cache broker token data.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name (e.g., 'fyers')
            token_data (Dict): Token data including access_token, refresh_token, etc.
            expire_seconds (int): Expiration time (default 2 hours for FYERS)
            
        Returns:
            bool: True if successful
        """
        key = f"token:{broker_name}:{user_id}"
        return self.set(key, token_data, expire_seconds)
    
    def get_cached_token(self, user_id: int, broker_name: str) -> Optional[Dict[str, Any]]:
        """
        Get cached broker token data.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
            
        Returns:
            Dict: Token data or None if not found
        """
        key = f"token:{broker_name}:{user_id}"
        return self.get(key)
    
    def invalidate_token(self, user_id: int, broker_name: str) -> bool:
        """
        Invalidate cached token data.
        
        Args:
            user_id (int): User ID
            broker_name (str): Broker name
            
        Returns:
            bool: True if successful
        """
        key = f"token:{broker_name}:{user_id}"
        return self.delete(key)
    
    # API response caching
    def cache_api_response(self, endpoint: str, params: Dict[str, Any], response_data: Any, expire_seconds: int = 300) -> bool:
        """
        Cache API response data.
        
        Args:
            endpoint (str): API endpoint
            params (Dict): Request parameters
            response_data (Any): Response data to cache
            expire_seconds (int): Cache expiration (default 5 minutes)
            
        Returns:
            bool: True if successful
        """
        # Create a hash of the parameters for the cache key
        params_str = json.dumps(params, sort_keys=True)
        key = f"api:{endpoint}:{hash(params_str)}"
        return self.set(key, response_data, expire_seconds)
    
    def get_cached_api_response(self, endpoint: str, params: Dict[str, Any]) -> Optional[Any]:
        """
        Get cached API response data.
        
        Args:
            endpoint (str): API endpoint
            params (Dict): Request parameters
            
        Returns:
            Any: Cached response data or None if not found
        """
        params_str = json.dumps(params, sort_keys=True)
        key = f"api:{endpoint}:{hash(params_str)}"
        return self.get(key)
    
    # Session data caching
    def cache_user_session(self, user_id: int, session_data: Dict[str, Any], expire_seconds: int = 3600) -> bool:
        """
        Cache user session data.
        
        Args:
            user_id (int): User ID
            session_data (Dict): Session data
            expire_seconds (int): Session expiration (default 1 hour)
            
        Returns:
            bool: True if successful
        """
        key = f"session:user:{user_id}"
        return self.set(key, session_data, expire_seconds)
    
    def get_user_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached user session data.
        
        Args:
            user_id (int): User ID
            
        Returns:
            Dict: Session data or None if not found
        """
        key = f"session:user:{user_id}"
        return self.get(key)
    
    def clear_user_session(self, user_id: int) -> bool:
        """
        Clear user session data.
        
        Args:
            user_id (int): User ID
            
        Returns:
            bool: True if successful
        """
        key = f"session:user:{user_id}"
        return self.delete(key)


# Global cache service instance
_cache_service = None

def get_cache_service() -> CacheService:
    """Get global cache service instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
