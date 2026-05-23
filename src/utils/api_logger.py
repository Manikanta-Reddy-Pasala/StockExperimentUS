"""
API Logging Utility

Comprehensive logging for all API calls, requests, and responses.
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from functools import wraps
import traceback
from flask import request

# Configure API logger
api_logger = logging.getLogger('api_calls')
api_logger.setLevel(logging.INFO)

# Create handler if not exists
if not api_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    api_logger.addHandler(handler)


class APILogger:
    """Centralized API logging utility."""
    
    @staticmethod
    def log_api_call(
        service_name: str,
        method_name: str,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        duration_ms: Optional[float] = None,
        error: Optional[Exception] = None,
        request_id: Optional[str] = None
    ):
        """
        Log API call with comprehensive details.
        
        Args:
            service_name: Name of the service making the call
            method_name: Name of the method/endpoint
            request_data: Request payload/data
            response_data: Response payload/data
            user_id: User ID if available
            duration_ms: Call duration in milliseconds
            error: Exception if any
            request_id: Unique request identifier
        """
        if not request_id:
            request_id = str(uuid.uuid4())[:8]
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'request_id': request_id,
            'service': service_name,
            'method': method_name,
            'user_id': user_id,
            'duration_ms': duration_ms,
            'status': 'error' if error else 'success'
        }
        
        if request_data is not None:
            # Sanitize sensitive data
            sanitized_request = APILogger._sanitize_data(request_data)
            log_entry['request'] = sanitized_request
        
        if response_data is not None:
            # Sanitize sensitive data
            sanitized_response = APILogger._sanitize_data(response_data)
            log_entry['response'] = sanitized_response
        
        if error:
            log_entry['error'] = {
                'type': type(error).__name__,
                'message': str(error),
                'traceback': traceback.format_exc()
            }
        
        # Log as JSON for easy parsing
        api_logger.info(json.dumps(log_entry, indent=2))
    
    @staticmethod
    def _sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from data."""
        sensitive_keys = [
            'password', 'token', 'access_token', 'refresh_token', 
            'api_key', 'secret', 'auth', 'authorization', 'credentials'
        ]
        
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    sanitized[key] = '[REDACTED]'
                elif isinstance(value, dict):
                    sanitized[key] = APILogger._sanitize_data(value)
                elif isinstance(value, list):
                    sanitized[key] = [
                        APILogger._sanitize_data(item) if isinstance(item, dict) else item
                        for item in value
                    ]
                elif hasattr(value, '__dict__'):
                    # Handle objects that can't be serialized
                    sanitized[key] = f'<{type(value).__name__} object>'
                else:
                    sanitized[key] = value
            return sanitized
        elif hasattr(data, '__dict__'):
            # Handle objects that can't be serialized
            return f'<{type(data).__name__} object>'
        return data
    
    @staticmethod
    def log_request(service_name: str, method_name: str, request_data: Dict[str, Any], user_id: Optional[int] = None):
        """Log API request."""
        APILogger.log_api_call(
            service_name=service_name,
            method_name=method_name,
            request_data=request_data,
            user_id=user_id
        )
    
    @staticmethod
    def log_response(service_name: str, method_name: str, response_data: Dict[str, Any], user_id: Optional[int] = None, duration_ms: Optional[float] = None):
        """Log API response."""
        APILogger.log_api_call(
            service_name=service_name,
            method_name=method_name,
            response_data=response_data,
            user_id=user_id,
            duration_ms=duration_ms
        )
    
    @staticmethod
    def log_error(service_name: str, method_name: str, error: Exception, request_data: Optional[Dict[str, Any]] = None, user_id: Optional[int] = None):
        """Log API error."""
        APILogger.log_api_call(
            service_name=service_name,
            method_name=method_name,
            request_data=request_data,
            error=error,
            user_id=user_id
        )


def log_api_call(service_name: str, user_id: Optional[int] = None):
    """
    Decorator to automatically log API calls.
    
    Usage:
        @log_api_call("UserService", user_id=current_user.id)
        def get_user_profile(self, user_id: int):
            # method implementation
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request_id = str(uuid.uuid4())[:8]
            start_time = datetime.now()
            
            # Extract request data
            request_data = {}
            if args:
                request_data['args'] = list(args)
            if kwargs:
                request_data['kwargs'] = kwargs
            
            # Log request
            APILogger.log_request(
                service_name=service_name,
                method_name=func.__name__,
                request_data=request_data,
                user_id=user_id
            )
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # Log response
                APILogger.log_response(
                    service_name=service_name,
                    method_name=func.__name__,
                    response_data={'result': result} if result is not None else None,
                    user_id=user_id,
                    duration_ms=duration_ms
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # Log error
                APILogger.log_error(
                    service_name=service_name,
                    method_name=func.__name__,
                    error=e,
                    request_data=request_data,
                    user_id=user_id
                )
                
                raise
        
        return wrapper
    return decorator


def log_flask_route(route_name: str):
    """
    Decorator for Flask routes to log API calls.
    
    Usage:
        @app.route('/api/users')
        @log_flask_route("get_users")
        def get_users():
            # route implementation
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request_id = str(uuid.uuid4())[:8]
            start_time = datetime.now()
            
            # Get user ID if available
            user_id = None
            try:
                from flask_login import current_user
                if current_user and hasattr(current_user, 'id'):
                    user_id = current_user.id
            except:
                pass
            
            # Extract request data
            request_data = {
                'method': request.method,
                'url': request.url,
                'headers': dict(request.headers),
                'args': dict(request.args),
                'form': dict(request.form) if request.form else None,
                'json': request.get_json() if request.is_json else None
            }
            
            # Log request
            APILogger.log_request(
                service_name="FlaskAPI",
                method_name=route_name,
                request_data=request_data,
                user_id=user_id
            )
            
            try:
                # Execute route
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # Extract response data
                response_data = None
                if isinstance(result, tuple):
                    response_data = {'status_code': result[1], 'data': result[0]}
                elif hasattr(result, 'get_json'):
                    response_data = {'data': result.get_json()}
                else:
                    response_data = {'data': result}
                
                # Log response
                APILogger.log_response(
                    service_name="FlaskAPI",
                    method_name=route_name,
                    response_data=response_data,
                    user_id=user_id,
                    duration_ms=duration_ms
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # Log error
                APILogger.log_error(
                    service_name="FlaskAPI",
                    method_name=route_name,
                    error=e,
                    request_data=request_data,
                    user_id=user_id
                )
                
                raise
        
        return wrapper
    return decorator
