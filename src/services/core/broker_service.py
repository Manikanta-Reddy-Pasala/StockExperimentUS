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

try:
    from fyers_apiv3 import fyersModel
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False


class BrokerService:
    """Service for managing broker configurations and connections."""
    
    def __init__(self):
        self.db_manager = get_database_manager()

    def _get_fyers_connector(self, user_id: int) -> 'FyersAPIConnector':
        """Helper to get an initialized FyersAPIConnector for a user."""
        # Debug print removed for clean console
        config = self.get_broker_config('fyers', user_id)
        # Debug print removed for clean console
        if not config or not config.get('client_id') or not config.get('access_token'):
        # Debug print removed for clean console
            raise ValueError('FYERS credentials not configured or access token missing.')
        # Debug print removed for clean console
        connector = FyersAPIConnector(config['client_id'], config['access_token'])
        # Debug print removed for clean console
        return connector

    def test_fyers_connection(self, user_id: int):
        """Test FYERS broker connection."""
        config = self.get_broker_config('fyers', user_id)
        if not config or not config.get('client_id') or not config.get('access_token'):
            raise ValueError('FYERS credentials not configured.')

        connector = FyersAPIConnector(config.get('client_id'), config.get('access_token'))
        result = connector.test_connection()

        with self.db_manager.get_session() as session:
            db_config = session.query(BrokerConfiguration).filter_by(broker_name='fyers', user_id=user_id).first()
            if db_config:
                db_config.is_connected = result['success']
                db_config.connection_status = 'connected' if result['success'] else 'disconnected'
                db_config.last_connection_test = datetime.utcnow()
                db_config.error_message = result.get('message', '') if not result['success'] else None
                session.commit()

        return result

    def generate_fyers_auth_url(self, user_id: int) -> str:
        """Generate FYERS OAuth2 authorization URL."""
        config = self.get_broker_config('fyers', user_id)
        if not config or not config.get('client_id') or not config.get('api_secret'):
            raise ValueError('FYERS configuration not found. Please save your Client ID and Secret Key first.')

        oauth_flow = FyersOAuth2Flow(
            client_id=config.get('client_id'),
            secret_key=config.get('api_secret'),
            redirect_uri=config.get('redirect_url')
        )
        return oauth_flow.generate_auth_url(user_id)

    def exchange_fyers_auth_code(self, user_id: int, auth_code: str) -> dict:
        """Exchange FYERS auth code for an access token and save it."""
        config = self.get_broker_config('fyers', user_id)
        if not config or not config.get('client_id') or not config.get('api_secret'):
            raise ValueError('FYERS configuration not found.')

        oauth_flow = FyersOAuth2Flow(
            client_id=config.get('client_id'),
            secret_key=config.get('api_secret'),
            redirect_uri=config.get('redirect_url')
        )
        token_response = oauth_flow.exchange_auth_code_for_token(auth_code)

        if 'access_token' in token_response:
            access_token = token_response['access_token']
            refresh_token = token_response.get('refresh_token', '')

            # Save the new tokens including refresh_token for API-based refresh
            save_data = {
                'access_token': access_token,
                'is_connected': True,
                'connection_status': 'connected'
            }
            if refresh_token:
                save_data['refresh_token'] = refresh_token

            self.save_broker_config('fyers', save_data, user_id)

            return {'success': True, 'access_token': access_token, 'refresh_token': refresh_token}
        else:
            raise ValueError(token_response.get('message', 'Failed to obtain access token'))

    def get_fyers_funds(self, user_id: int):
        connector = self._get_fyers_connector(user_id)
        return connector.funds()

    def get_fyers_holdings(self, user_id: int):
        connector = self._get_fyers_connector(user_id)
        return connector.holdings()

    def get_fyers_positions(self, user_id: int):
        # Debug print removed for clean console
        try:
        # Debug print removed for clean console
            connector = self._get_fyers_connector(user_id)
        # Debug print removed for clean console
        # Debug print removed for clean console
            result = connector.positions()
        # Debug print removed for clean console
            return result
        except Exception as e:
        # Debug print removed for clean console
            return {'success': False, 'error': str(e)}

    def get_fyers_orderbook(self, user_id: int):
        connector = self._get_fyers_connector(user_id)
        return connector.orderbook()

    def get_fyers_tradebook(self, user_id: int):
        connector = self._get_fyers_connector(user_id)
        return connector.tradebook()

    def get_fyers_quotes(self, user_id: int, symbols: str):
        connector = self._get_fyers_connector(user_id)
        return connector.quotes(symbols)

    def get_fyers_history(self, user_id: int, symbol: str, resolution: str, range_from: str, range_to: str):
        connector = self._get_fyers_connector(user_id)
        return connector.history(symbol, resolution, range_from, range_to)

    def get_fyers_profile(self, user_id: int):
        connector = self._get_fyers_connector(user_id)
        return connector.login()
    
    def is_token_expired(self, access_token: str) -> bool:
        """Check if FYERS access token is expired."""
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


class FyersOAuth2Flow:
    """FYERS OAuth2 authentication flow handler."""
    
    def __init__(self, client_id: str, secret_key: str, redirect_uri: str):
        self.client_id = client_id
        self.secret_key = secret_key
        self.redirect_uri = redirect_uri
        self.grant_type = "authorization_code"
        self.response_type = "code"
        self.state = "sample"
    
    def generate_auth_url(self, user_id: int = 1) -> str:
        """Generate the authorization URL for user login with automated callback."""
        if not FYERS_AVAILABLE:
            raise Exception("fyers-apiv3 library not available")

        try:
            # Use credentials passed via constructor (already fetched by BrokerService)
            app_session = fyersModel.SessionModel(
                client_id=self.client_id,
                redirect_uri=self.redirect_uri,
                response_type=self.response_type,
                state=str(user_id),
                secret_key=self.secret_key,
                grant_type=self.grant_type
            )
            
            # Generate the authorization URL
            auth_url = app_session.generate_authcode()
            logger.info(f"Generated FYERS authorization URL with automated callback: {auth_url}")
            return auth_url
            
        except Exception as e:
            logger.error(f"Error generating FYERS auth URL: {str(e)}")
            raise
    
    def exchange_auth_code_for_token(self, auth_code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        if not FYERS_AVAILABLE:
            raise Exception("fyers-apiv3 library not available")
        
        try:
            # Create session model for OAuth flow
            app_session = fyersModel.SessionModel(
                client_id=self.client_id,
                redirect_uri=self.redirect_uri,
                response_type=self.response_type,
                state=self.state,
                secret_key=self.secret_key,
                grant_type=self.grant_type
            )
            
            # Set the auth code and generate token
            app_session.set_token(auth_code)
            response = app_session.generate_token()
            
            logger.info("Successfully exchanged auth code for access token")
            return response
            
        except Exception as e:
            logger.error(f"Error exchanging auth code for token: {str(e)}")
            raise


class FyersAPIConnector:
    """FYERS API connector for real-time connection testing and operations."""
    
    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = "https://api-t1.fyers.in/api/v3"
        
        # Initialize requests session for fallback API calls
        import requests
        self.session = requests.Session()
        
        # Official library handles everything internally
        if FYERS_AVAILABLE:
            self.fyers_client = fyersModel.FyersModel(
                token=access_token,
                is_async=False,
                client_id=client_id,
                log_path=""
            )
        else:
            self.fyers_client = None
            logger.warning("fyers-apiv3 library not available")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test FYERS API connection by making a real API call."""
        try:
            logger.info(f"Testing FYERS connection with client_id: {self.client_id[:10]}...")
            start_time = time.time()
            
            if not self.fyers_client:
                return {
                    'success': False,
                    'message': 'FYERS client not available',
                    'response_time': '0ms',
                    'status_code': 500
                }
            
            # Use official library to test connection
            response = self.fyers_client.get_profile()
            response_time = round((time.time() - start_time) * 1000, 2)
            
            logger.info(f"FYERS API response status: {response.get('s', 'unknown')}, time: {response_time}ms")
            
            if response.get('s') == 'ok':
                logger.info("FYERS connection test successful")
                return {
                    'success': True,
                    'message': 'Connection successful',
                    'response_time': f"{response_time}ms",
                    'profile_data': response.get('data', {}),
                    'status_code': 200
                }
            else:
                error_msg = f"API Error: {response.get('message', 'Unknown error')}"
                logger.warning(f"FYERS API error: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'response_time': f"{response_time}ms",
                    'status_code': 400
                }
                
        except Exception as e:
            error_msg = f'Connection failed: {str(e)}'
            logger.error(f"FYERS unexpected error: {error_msg}")
            return {
                'success': False,
                'message': error_msg,
                'response_time': '-',
                'status_code': 0
            }
    
    def get_profile(self) -> Dict[str, Any]:
        """Get user profile information."""
        try:
            logger.info("Fetching FYERS user profile")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.get_profile()
                    logger.info("FYERS profile fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 profile fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/profile"
            response = self.session.get(url, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info("FYERS profile fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS profile: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS profile: {error_msg}")
            return {'error': error_msg}
    
    def get_funds(self) -> Dict[str, Any]:
        """Get user funds."""
        try:
            logger.info("Fetching FYERS user funds")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.funds()
                    logger.info(f"FYERS funds response: {response}")
                    logger.info("FYERS funds fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 funds fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/funds"
            response = self.session.get(url, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info(f"FYERS funds response: {data}")
                logger.info("FYERS funds fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS funds: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS funds: {error_msg}")
            return {'error': error_msg}
    
    def get_holdings(self) -> Dict[str, Any]:
        """Get user holdings."""
        try:
            logger.info("Fetching FYERS user holdings")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.holdings()
                    logger.info(f"FYERS holdings response: {response}")
                    logger.info("FYERS holdings fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 holdings fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/holdings"
            response = self.session.get(url, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info(f"FYERS holdings response: {data}")
                logger.info("FYERS holdings fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS holdings: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS holdings: {error_msg}")
            return {'error': error_msg}
    
    def get_positions(self) -> Dict[str, Any]:
        """Get user positions."""
        try:
            logger.info("Fetching FYERS user positions")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.positions()
                    logger.info(f"FYERS positions response: {response}")
                    logger.info("FYERS positions fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 positions fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/positions"
            response = self.session.get(url, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info(f"FYERS positions response: {data}")
                logger.info("FYERS positions fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS positions: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS positions: {error_msg}")
            return {'error': error_msg}
    
    def get_tradebook(self) -> Dict[str, Any]:
        """Get user tradebook."""
        try:
            logger.info("Fetching FYERS user tradebook")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.tradebook()
                    logger.info(f"FYERS tradebook response: {response}")
                    logger.info("FYERS tradebook fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 tradebook fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/tradebook"
            response = self.session.get(url, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info(f"FYERS tradebook response: {data}")
                logger.info("FYERS tradebook fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS tradebook: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS tradebook: {error_msg}")
            return {'error': error_msg}
    
    def get_orderbook(self) -> Dict[str, Any]:
        """Get user orderbook."""
        try:
            logger.info("Fetching FYERS user orderbook")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.orderbook()
                    logger.info("FYERS orderbook fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 orderbook fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/orderbook"
            response = self.session.get(url, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info("FYERS orderbook fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS orderbook: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS orderbook: {error_msg}")
            return {'error': error_msg}
    
    def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Place a single order."""
        try:
            logger.info("Placing FYERS order")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.place_order(order_data)
                    logger.info("FYERS order placed successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 order placement failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/orders"
            response = self.session.post(url, json=order_data, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info("FYERS order placed successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error placing FYERS order: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while placing FYERS order: {error_msg}")
            return {'error': error_msg}
    
    def positions(self) -> Dict[str, Any]:
        """Get user positions - alias for get_positions."""
        return self.get_positions()
    
    def quotes(self, symbols: str) -> Dict[str, Any]:
        """Get quotes for symbols."""
        try:
            logger.info(f"Fetching FYERS quotes for symbols: {symbols}")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    # Correct usage: pass an object with `symbols`
                    payload = {"symbols": symbols}
                    response = self.fyers_client.quotes(payload)
                    logger.info(f"FYERS quotes raw response: {response}")
                    logger.info("FYERS quotes fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 quotes fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/quotes"
            params = {
                'access_token': self.access_token,
                'symbols': symbols
            }
            logger.info(f"Making fallback request to: {url} with params: {params}")
            
            response = self.session.get(url, params=params)
            logger.info(f"Fallback response status: {response.status_code}")
            logger.info(f"Fallback response text: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"FYERS quotes fallback response: {data}")
                logger.info("FYERS quotes fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS quotes: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS quotes: {error_msg}")
            return {'error': error_msg}
    
    def place_basket_orders(self, orders_data: list) -> Dict[str, Any]:
        """Place multiple orders (basket)."""
        try:
            logger.info("Placing FYERS basket orders")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    response = self.fyers_client.place_basket_orders(orders_data)
                    logger.info("FYERS basket orders placed successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 basket orders placement failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/orders-basket"
            response = self.session.post(url, json=orders_data, params={'access_token': self.access_token})
            if response.status_code == 200:
                data = response.json()
                logger.info("FYERS basket orders placed successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error placing FYERS basket orders: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while placing FYERS basket orders: {error_msg}")
            return {'error': error_msg}
    
    def get_quotes(self, symbols: str) -> Dict[str, Any]:
        """Get market quotes for symbols."""
        try:
            logger.info(f"Fetching FYERS quotes for symbols: {symbols}")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    data = {"symbols": symbols}
                    response = self.fyers_client.quotes(data)
                    logger.info("FYERS quotes fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 quotes fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/quotes"
            params = {'symbols': symbols, 'access_token': self.access_token}
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                logger.info("FYERS quotes fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS quotes: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS quotes: {error_msg}")
            return {'error': error_msg}
    
    def get_history(self, symbol: str, resolution: str = "D", range_from: str = None, range_to: str = None) -> Dict[str, Any]:
        """Get historical data for a symbol."""
        try:
            logger.info(f"Fetching FYERS historical data for symbol: {symbol}")
            
            # Use FYERS API client if available
            if self.fyers_client:
                try:
                    data = {
                        "symbol": symbol,
                        "resolution": resolution,
                        "date_format": "0",
                        "range_from": range_from or "1622097600",
                        "range_to": range_to or "1622097685",
                        "cont_flag": "1"
                    }
                    response = self.fyers_client.history(data)
                    logger.info("FYERS historical data fetched successfully using fyers-apiv3")
                    return response
                except Exception as e:
                    logger.warning(f"fyers-apiv3 historical data fetch failed, falling back to requests: {str(e)}")
            
            # Fallback to direct API call
            url = f"{self.base_url}/history"
            params = {
                'symbol': symbol,
                'resolution': resolution,
                'date_format': '0',
                'range_from': range_from or '1622097600',
                'range_to': range_to or '1622097685',
                'cont_flag': '1',
                'access_token': self.access_token
            }
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                logger.info("FYERS historical data fetched successfully using requests")
                return data
            else:
                error_msg = f'HTTP {response.status_code}: {response.text}'
                logger.error(f"Error fetching FYERS historical data: {error_msg}")
                return {'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Exception while fetching FYERS historical data: {error_msg}")
            return {'error': error_msg}

    def orderbook(self) -> Dict[str, Any]:
        """Alias for get_orderbook method."""
        return self.get_orderbook()

    def tradebook(self) -> Dict[str, Any]:
        """Alias for get_tradebook method."""
        return self.get_tradebook()

    def funds(self) -> Dict[str, Any]:
        """Alias for get_funds method."""
        return self.get_funds()

    def holdings(self) -> Dict[str, Any]:
        """Alias for get_holdings method."""
        return self.get_holdings()

    def login(self) -> Dict[str, Any]:
        """Alias for get_profile method."""
        return self.get_profile()

    def history(self, symbol: str, resolution: str = "D", range_from: str = None, range_to: str = None) -> Dict[str, Any]:
        """Alias for get_history method."""
        return self.get_history(symbol, resolution, range_from, range_to)


def get_broker_service() -> BrokerService:
    """Get broker service instance."""
    return BrokerService()
