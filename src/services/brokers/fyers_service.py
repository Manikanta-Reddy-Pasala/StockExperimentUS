"""
Fyers Service

This service provides comprehensive Fyers broker integration with standardized
API endpoints and response formats.
"""

import logging
import time
from typing import Dict, Optional, Any
from datetime import datetime

try:
    from src.models.database import get_database_manager
    from src.models.models import BrokerConfiguration
    from src.utils.api_logger import APILogger
    from .fyers import create_fyers_api, create_fyers_auth
except ImportError:
    from models.database import get_database_manager
    from models.models import BrokerConfiguration
    from utils.api_logger import APILogger
    from .fyers import create_fyers_api, create_fyers_auth

logger = logging.getLogger(__name__)


class FyersService:
    """
    Comprehensive Fyers service with standardized API implementation.
    """
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self.broker_name = 'fyers'
    
    def _get_api_instance(self, user_id: int):
        """Get standardized API instance for user."""
        config = self.get_broker_config(user_id)
        if not config:
            raise ValueError('Fyers configuration not found')
        
        api_key = config.get('client_id')
        api_secret = config.get('api_secret')
        access_token = config.get('access_token')
        
        if not all([api_key, access_token]):
            raise ValueError('Incomplete Fyers configuration - missing client_id or access_token')
        
        return create_fyers_api(api_key, api_secret, access_token)
    
    def get_broker_config(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get Fyers broker configuration from database."""
        with self.db_manager.get_session() as session:
            query = session.query(BrokerConfiguration).filter_by(broker_name=self.broker_name)
            if user_id:
                query = query.filter_by(user_id=user_id)
            else:
                query = query.filter_by(user_id=None)
            
            config = query.first()
            if not config:
                return None
            
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
    
    def save_broker_config(self, config_data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        """Save Fyers broker configuration to database."""
        with self.db_manager.get_session() as session:
            query = session.query(BrokerConfiguration).filter_by(broker_name=self.broker_name)
            if user_id:
                query = query.filter_by(user_id=user_id)
            else:
                query = query.filter_by(user_id=None)
            
            existing_config = query.first()
            
            if existing_config:
                config = existing_config
            else:
                config = BrokerConfiguration(
                    broker_name=self.broker_name,
                    user_id=user_id
                )
                session.add(config)
            
            # Update fields
            for key, value in config_data.items():
                if hasattr(config, key) and value is not None:
                    setattr(config, key, value)
            
            config.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(config)
            
            return self.get_broker_config(user_id)
    
    # Authentication Methods
    def generate_auth_url(self, user_id: int) -> str:
        """Generate Fyers OAuth2 authorization URL."""
        config = self.get_broker_config(user_id)
        if not config or not config.get('client_id') or not config.get('api_secret'):
            raise ValueError('Fyers configuration not found. Please save your Client ID and Secret Key first.')
        
        if not config.get('redirect_url'):
            raise ValueError('Fyers redirect URL not configured. Please save your redirect URL first.')
        
        auth = create_fyers_auth(
            client_id=config.get('client_id'),
            secret_key=config.get('api_secret'),
            redirect_uri=config.get('redirect_url')
        )
        
        return auth.generate_auth_url(str(user_id))
    
    def exchange_auth_code(self, user_id: int, auth_code: str) -> dict:
        """Exchange Fyers auth code for access token."""
        config = self.get_broker_config(user_id)
        if not config or not config.get('client_id') or not config.get('api_secret'):
            raise ValueError('Fyers configuration not found.')
        
        auth = create_fyers_auth(
            client_id=config.get('client_id'),
            secret_key=config.get('api_secret'),
            redirect_uri=config.get('redirect_url')
        )
        
        token_response = auth.generate_access_token(auth_code)
        
        if token_response.get('status') == 'success':
            access_token = token_response.get('access_token')
            refresh_token = token_response.get('refresh_token', '')

            # Save the new token including refresh_token
            save_data = {
                'access_token': access_token,
                'is_connected': True,
                'connection_status': 'connected'
            }
            if refresh_token:
                save_data['refresh_token'] = refresh_token

            self.save_broker_config(save_data, user_id)

            return {'success': True, 'access_token': access_token, 'refresh_token': refresh_token}
        else:
            raise ValueError(token_response.get('message', 'Failed to obtain access token'))
    
    def test_connection(self, user_id: int):
        """Test Fyers broker connection using standardized API."""
        try:
            api = self._get_api_instance(user_id)
            result = api.login()
            
            # Update connection status in database
            with self.db_manager.get_session() as session:
                db_config = session.query(BrokerConfiguration).filter_by(
                    broker_name=self.broker_name, user_id=user_id
                ).first()
                
                if db_config:
                    success = result.get('status') == 'success'
                    db_config.is_connected = success
                    db_config.connection_status = 'connected' if success else 'disconnected'
                    db_config.last_connection_test = datetime.utcnow()
                    db_config.error_message = result.get('message', '') if not success else None
                    session.commit()
            
            return {
                'success': result.get('status') == 'success',
                'message': result.get('message', ''),
                'response_time': '-'
            }
            
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {
                'success': False,
                'message': str(e),
                'response_time': '-'
            }
    
    # Standardized API Methods
    def login(self, user_id: int):
        """Login to Fyers using standardized format."""
        APILogger.log_request("FyersService", "login", {}, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.login()
            APILogger.log_response("FyersService", "login", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "login", e, {}, user_id)
            raise
    
    def placeorder(self, user_id: int, symbol: str, quantity: str, action: str,
                   product: str, pricetype: str, price: str = "0",
                   trigger_price: str = "0", disclosed_quantity: str = "0",
                   validity: str = "DAY", tag: str = ""):
        """Place order using standardized format."""
        request_data = {
            'symbol': symbol, 'quantity': quantity, 'action': action,
            'product': product, 'pricetype': pricetype, 'price': price,
            'trigger_price': trigger_price, 'disclosed_quantity': disclosed_quantity,
            'validity': validity, 'tag': tag
        }
        
        APILogger.log_request("FyersService", "placeorder", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.placeorder(
                symbol=symbol, quantity=quantity, action=action,
                product=product, pricetype=pricetype, price=price,
                trigger_price=trigger_price, disclosed_quantity=disclosed_quantity,
                validity=validity, tag=tag
            )
            APILogger.log_response("FyersService", "placeorder", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "placeorder", e, request_data, user_id)
            raise
    
    def modifyorder(self, user_id: int, orderid: str, symbol: str = "", 
                    quantity: str = "", price: str = "", trigger_price: str = "",
                    disclosed_quantity: str = "", validity: str = ""):
        """Modify order using standardized format."""
        request_data = {
            'orderid': orderid, 'symbol': symbol, 'quantity': quantity,
            'price': price, 'trigger_price': trigger_price,
            'disclosed_quantity': disclosed_quantity, 'validity': validity
        }
        
        APILogger.log_request("FyersService", "modifyorder", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.modifyorder(
                orderid=orderid, symbol=symbol, quantity=quantity,
                price=price, trigger_price=trigger_price,
                disclosed_quantity=disclosed_quantity, validity=validity
            )
            APILogger.log_response("FyersService", "modifyorder", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "modifyorder", e, request_data, user_id)
            raise
    
    def cancelorder(self, user_id: int, orderid: str):
        """Cancel order using standardized format."""
        request_data = {'orderid': orderid}
        
        APILogger.log_request("FyersService", "cancelorder", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.cancelorder(orderid=orderid)
            APILogger.log_response("FyersService", "cancelorder", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "cancelorder", e, request_data, user_id)
            raise
    
    def placesmartorder(self, user_id: int, symbol: str, action: str, product: str,
                       quantity: str = "", position_size: str = "", price: str = "0",
                       trigger_price: str = "0", pricetype: str = "MARKET",
                       strategy: str = "", tag: str = ""):
        """Place smart order using standardized format."""
        request_data = {
            'symbol': symbol, 'action': action, 'product': product,
            'quantity': quantity, 'position_size': position_size,
            'price': price, 'trigger_price': trigger_price,
            'pricetype': pricetype, 'strategy': strategy, 'tag': tag
        }
        
        APILogger.log_request("FyersService", "placesmartorder", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.placesmartorder(
                symbol=symbol, action=action, product=product,
                quantity=quantity, position_size=position_size,
                price=price, trigger_price=trigger_price,
                pricetype=pricetype, strategy=strategy, tag=tag
            )
            APILogger.log_response("FyersService", "placesmartorder", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "placesmartorder", e, request_data, user_id)
            raise
    
    def orderbook(self, user_id: int):
        """Get orderbook using standardized format."""
        APILogger.log_request("FyersService", "orderbook", {}, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.orderbook()
            APILogger.log_response("FyersService", "orderbook", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "orderbook", e, {}, user_id)
            raise
    
    def tradebook(self, user_id: int):
        """Get tradebook using standardized format."""
        APILogger.log_request("FyersService", "tradebook", {}, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.tradebook()
            APILogger.log_response("FyersService", "tradebook", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "tradebook", e, {}, user_id)
            raise
    
    def positions(self, user_id: int):
        """Get positions using standardized format."""
        APILogger.log_request("FyersService", "positions", {}, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.positions()
            APILogger.log_response("FyersService", "positions", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "positions", e, {}, user_id)
            raise
    
    def holdings(self, user_id: int):
        """Get holdings using standardized format."""
        APILogger.log_request("FyersService", "holdings", {}, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.holdings()
            APILogger.log_response("FyersService", "holdings", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "holdings", e, {}, user_id)
            raise
    
    def funds(self, user_id: int):
        """Get funds using standardized format."""
        APILogger.log_request("FyersService", "funds", {}, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.funds()
            APILogger.log_response("FyersService", "funds", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "funds", e, {}, user_id)
            raise
    
    def quotes(self, user_id: int, symbol: str, exchange: str = ""):
        """Get quotes using standardized format."""
        request_data = {'symbol': symbol, 'exchange': exchange}
        
        APILogger.log_request("FyersService", "quotes", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.quotes(symbol=symbol, exchange=exchange)
            APILogger.log_response("FyersService", "quotes", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "quotes", e, request_data, user_id)
            raise

    def _is_valid_fyers_symbol(self, symbol: str) -> bool:
        """Validate if symbol is in correct Fyers format."""
        if not symbol or not isinstance(symbol, str):
            return False

        # Fyers symbols should be in format: EXCHANGE:SYMBOL-SEGMENT
        # Examples: NSE:INFY-EQ, BSE:SENSEX-INDEX, MCX:GOLD24FEB-COM
        if ':' not in symbol or '-' not in symbol:
            return False

        parts = symbol.split(':')
        if len(parts) != 2:
            return False

        exchange, symbol_part = parts
        if exchange not in ['NSE', 'BSE', 'MCX', 'NCDEX']:
            return False

        if '-' not in symbol_part:
            return False

        # Basic length validation
        if len(symbol) < 6 or len(symbol) > 30:
            return False

        # Additional Fyers-specific validation
        # Reject symbols with problematic characters that cause API issues
        symbol_name, segment = symbol_part.rsplit('-', 1)

        # Skip symbols with special characters that Fyers API rejects
        # Note: & is allowed as it's used in legitimate company symbols (M&M, J&K Bank, etc.)
        if any(char in symbol_name for char in ['+', '(', ')', '[', ']', '*']):
            logger.debug(f"Rejecting symbol with special characters: {symbol}")
            return False

        # Only allow standard segments
        if segment not in ['EQ', 'INDEX', 'FUT', 'OPT', 'COM']:
            return False

        return True

    def quotes_multiple(self, user_id: int, symbols: list):
        """Get quotes for multiple symbols using standardized format."""
        logger.debug(f"FyersService.quotes_multiple called for user {user_id} with {len(symbols)} symbols")

        # Validate and filter symbols for Fyers API format
        valid_symbols = []
        for symbol in symbols:
            if self._is_valid_fyers_symbol(symbol):
                valid_symbols.append(symbol)
            else:
                logger.debug(f"Invalid symbol format for Fyers API: {symbol}")

        if not valid_symbols:
            logger.warning(f"No valid symbols found in batch of {len(symbols)}")
            return {
                'status': 'error',
                'message': 'No valid symbols found',
                'data': {}
            }

        # Limit batch size to avoid API limits (Fyers typically allows 50-100 symbols per request)
        max_batch_size = 50
        if len(valid_symbols) > max_batch_size:
            valid_symbols = valid_symbols[:max_batch_size]
            logger.debug(f"Limiting batch to {max_batch_size} symbols")

        request_data = {'symbols': valid_symbols}
        APILogger.log_request("FyersService", "quotes_multiple", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.quotes_multiple(valid_symbols)

            # Enhanced error reporting
            if result.get('status') == 'success':
                logger.debug(f"Quotes successful for {len(valid_symbols)} symbols")
                APILogger.log_response("FyersService", "quotes_multiple", result, user_id)
                return result
            else:
                error_msg = result.get('message', 'Unknown error')
                error_code = result.get('error_code', 'UNKNOWN')

                # Try fallback to individual quotes if batch fails
                if 'invalid input' in error_msg.lower():
                    logger.info(f"Batch quotes failed, trying individual quotes for {len(valid_symbols)} symbols")
                    return self._try_individual_quotes(user_id, valid_symbols)
                elif 'authentication' in error_msg.lower() or 'token' in error_msg.lower():
                    logger.error(f"Authentication failed - check Fyers API credentials and access token")
                elif 'limit' in error_msg.lower():
                    logger.warning(f"API limit reached - reducing batch size next time")
                else:
                    logger.warning(f"Quotes failed for batch: {error_msg} (Code: {error_code})")

                APILogger.log_response("FyersService", "quotes_multiple", result, user_id)
                return result

        except Exception as e:
            logger.warning(f"Exception in quotes_multiple: {e}")
            APILogger.log_error("FyersService", "quotes_multiple", e, request_data, user_id)
            raise

    def _try_individual_quotes(self, user_id: int, symbols: list) -> dict:
        """Fallback method to get individual quotes when batch fails."""
        successful_quotes = {}
        failed_count = 0

        # Limit to first 10 symbols to avoid too many individual API calls
        limited_symbols = symbols[:10]
        logger.info(f"Trying individual quotes for {len(limited_symbols)} symbols (limited from {len(symbols)})")

        for symbol in limited_symbols:
            try:
                # Use the single quote method
                result = self.quotes(user_id, symbol)
                if result.get('status') == 'success' and result.get('data'):
                    successful_quotes[symbol] = result['data']
                else:
                    failed_count += 1
                    logger.debug(f"Individual quote failed for {symbol}")
            except Exception as e:
                failed_count += 1
                logger.debug(f"Exception getting individual quote for {symbol}: {e}")

            # Fyers API limit: 10 req/s, using 0.2s for safe margin (5 req/s)
            time.sleep(0.2)

        if successful_quotes:
            logger.info(f"Individual quotes successful: {len(successful_quotes)}, failed: {failed_count}")
            return {
                'status': 'success',
                'data': successful_quotes
            }
        else:
            logger.warning(f"All individual quotes failed for {len(limited_symbols)} symbols")
            return {
                'status': 'error',
                'message': 'All individual quotes failed',
                'error_code': 'INDIVIDUAL_QUOTES_FAILED'
            }

    def generate_portfolio_summary_report(self, user_id: int):
        """Generate comprehensive portfolio summary report."""
        APILogger.log_request("FyersService", "generate_portfolio_summary_report", {}, user_id)
        try:
            # Get holdings and positions
            holdings_result = self.holdings(user_id)
            positions_result = self.positions(user_id)
            funds_result = self.funds(user_id)
            
            # Calculate summary metrics
            total_value = 0
            total_pnl = 0
            total_investment = 0
            
            holdings_data = holdings_result.get('data', []) if holdings_result.get('status') == 'success' else []
            positions_data = positions_result.get('data', []) if positions_result.get('status') == 'success' else []
            funds_data = funds_result.get('data', {}) if funds_result.get('status') == 'success' else {}
            
            # Calculate holdings metrics
            for holding in holdings_data:
                if isinstance(holding, dict):
                    qty = float(holding.get('quantity', 0))
                    ltp = float(holding.get('ltp', 0))
                    avg_price = float(holding.get('avgPrice', 0))
                    
                    current_value = qty * ltp
                    investment = qty * avg_price
                    pnl = current_value - investment
                    
                    total_value += current_value
                    total_investment += investment
                    total_pnl += pnl
            
            # Calculate positions metrics
            for position in positions_data:
                if isinstance(position, dict):
                    qty = float(position.get('quantity', 0))
                    ltp = float(position.get('ltp', 0))
                    avg_price = float(position.get('avgPrice', 0))
                    
                    current_value = qty * ltp
                    investment = qty * avg_price
                    pnl = current_value - investment
                    
                    total_value += current_value
                    total_investment += investment
                    total_pnl += pnl
            
            # Get available funds
            available_cash = float(funds_data.get('fund_limit', 0))
            
            summary = {
                'total_portfolio_value': total_value,
                'total_investment': total_investment,
                'total_pnl': total_pnl,
                'total_pnl_percent': (total_pnl / total_investment * 100) if total_investment > 0 else 0,
                'available_cash': available_cash,
                'total_holdings': len(holdings_data),
                'total_positions': len(positions_data),
                'last_updated': datetime.now().isoformat()
            }
            
            result = {
                'status': 'success',
                'data': summary
            }
            
            APILogger.log_response("FyersService", "generate_portfolio_summary_report", result, user_id)
            return result
            
        except Exception as e:
            APILogger.log_error("FyersService", "generate_portfolio_summary_report", e, {}, user_id)
            return {
                'status': 'error',
                'message': str(e),
                'data': {}
            }
    
    def depth(self, user_id: int, symbol: str, exchange: str = ""):
        """Get market depth using standardized format."""
        request_data = {'symbol': symbol, 'exchange': exchange}
        
        APILogger.log_request("FyersService", "depth", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.depth(symbol=symbol, exchange=exchange)
            APILogger.log_response("FyersService", "depth", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "depth", e, request_data, user_id)
            raise
    
    def history(self, user_id: int, symbol: str, exchange: str, interval: str,
                start_date: str, end_date: str):
        """Get historical data using standardized format."""
        request_data = {
            'symbol': symbol, 'exchange': exchange, 'interval': interval,
            'start_date': start_date, 'end_date': end_date
        }
        
        APILogger.log_request("FyersService", "history", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.history(
                symbol=symbol, exchange=exchange, interval=interval,
                start_date=start_date, end_date=end_date
            )
            APILogger.log_response("FyersService", "history", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "history", e, request_data, user_id)
            raise
    
    def search(self, user_id: int, symbol: str, exchange: str = ""):
        """Search symbols using standardized format."""
        request_data = {'symbol': symbol, 'exchange': exchange}
        
        APILogger.log_request("FyersService", "search", request_data, user_id)
        try:
            api = self._get_api_instance(user_id)
            result = api.search(symbol=symbol, exchange=exchange)
            APILogger.log_response("FyersService", "search", result, user_id)
            return result
        except Exception as e:
            APILogger.log_error("FyersService", "search", e, request_data, user_id)
            raise
    
    # Legacy compatibility methods (for backward compatibility)
    def get_funds(self, user_id: int):
        """Legacy method - redirects to standardized format."""
        return self.funds(user_id)
    
    def get_holdings(self, user_id: int):
        """Legacy method - redirects to standardized format."""
        return self.holdings(user_id)
    
    def get_positions(self, user_id: int):
        """Legacy method - redirects to standardized format."""
        return self.positions(user_id)
    
    def get_orderbook(self, user_id: int):
        """Legacy method - redirects to standardized format."""
        return self.orderbook(user_id)
    
    def get_tradebook(self, user_id: int):
        """Legacy method - redirects to standardized format."""
        return self.tradebook(user_id)
    
    def get_quotes(self, user_id: int, symbols: str):
        """Legacy method - redirects to standardized format."""
        # Handle multiple symbols (legacy format)
        if ',' in symbols:
            symbol = symbols.split(',')[0]  # Take first symbol for now
        else:
            symbol = symbols
        
        return self.quotes(user_id, symbol)
    
    def get_history(self, user_id: int, symbol: str, resolution: str, 
                    range_from: str, range_to: str):
        """Legacy method - redirects to standardized format."""
        # Map legacy parameters to standard format
        exchange = "NSE"  # Default
        if ":" in symbol:
            exchange = symbol.split(":")[0]
        
        return self.history(user_id, symbol, exchange, resolution, range_from, range_to)
    
    def get_profile(self, user_id: int):
        """Legacy method - redirects to login."""
        return self.login(user_id)
    
    def get_broker_stats(self, user_id: int) -> Dict[str, Any]:
        """Get broker statistics for the user - optimized for fast loading."""
        try:
            # Return cached/default stats for fast page loading
            # In a production system, you would cache these stats and update them periodically
            # or calculate them from local database records instead of making API calls
            
            return {
                'total_orders': 0,
                'successful_orders': 0,
                'pending_orders': 0,
                'failed_orders': 0,
                'last_order_time': '-',
                'api_response_time': '-'
            }
        except Exception as e:
            logger.error(f"Error getting broker stats: {str(e)}")
            return {
                'total_orders': 0,
                'successful_orders': 0,
                'pending_orders': 0,
                'failed_orders': 0,
                'last_order_time': '-',
                'api_response_time': '-'
            }
    
    def get_token_status(self, user_id: int) -> Dict[str, Any]:
        """Get token status and information - optimized for fast loading."""
        try:
            # Use a simple database query instead of the full get_broker_config method
            with self.db_manager.get_session() as session:
                config = session.query(BrokerConfiguration).filter_by(
                    broker_name=self.broker_name, user_id=user_id
                ).first()
                
                if not config:
                    return {
                        'has_token': False,
                        'is_valid': False,
                        'expires_at': None,
                        'last_refresh': None,
                        'status': 'not_configured'
                    }
                
                has_token = bool(config.access_token)
                is_connected = config.is_connected or False
                last_connection_test = config.last_connection_test
                
                # Format datetime for JSON serialization
                last_refresh = None
                if last_connection_test:
                    if hasattr(last_connection_test, 'isoformat'):
                        last_refresh = last_connection_test.isoformat()
                    else:
                        last_refresh = str(last_connection_test)
                
                return {
                    'has_token': has_token,
                    'is_valid': is_connected,
                    'expires_at': None,  # FYERS tokens don't have explicit expiry
                    'last_refresh': last_refresh,
                    'status': 'connected' if is_connected else 'disconnected',
                    'client_id': config.client_id or '',
                    'connection_status': config.connection_status or 'unknown'
                }
        except Exception as e:
            logger.error(f"Error getting token status: {str(e)}")
            return {
                'has_token': False,
                'is_valid': False,
                'expires_at': None,
                'last_refresh': None,
                'status': 'error'
            }
    
    def start_auto_refresh(self, user_id: int, check_interval_minutes: int = 30):
        """Start automatic token refresh for the user."""
        # This is a placeholder implementation
        # In a real implementation, you would start a background task
        logger.info(f"Auto-refresh started for user {user_id} with {check_interval_minutes} minute intervals")
        return True
    
    def stop_auto_refresh(self, user_id: int):
        """Stop automatic token refresh for the user."""
        # This is a placeholder implementation
        # In a real implementation, you would stop the background task
        logger.info(f"Auto-refresh stopped for user {user_id}")
        return True
    
    def invalidate_token_cache(self, user_id: int):
        """Invalidate cached token data for the user."""
        # This is a placeholder implementation
        # In a real implementation, you would clear any cached tokens
        logger.info(f"Token cache invalidated for user {user_id}")
        return True
    
    def get_detailed_broker_stats(self, user_id: int) -> Dict[str, Any]:
        """Get detailed broker statistics with actual API calls - use sparingly."""
        try:
            # This method makes actual API calls and should be used only when needed
            # Get orderbook and tradebook to calculate stats
            orders = self.orderbook(user_id)
            trades = self.tradebook(user_id)
            
            # Calculate statistics
            total_orders = len(orders.get('orderBook', [])) if orders.get('orderBook') else 0
            successful_orders = len(trades.get('tradeBook', [])) if trades.get('tradeBook') else 0
            pending_orders = total_orders - successful_orders
            failed_orders = 0  # This would need to be tracked separately
            
            # Get last order time
            last_order_time = '-'
            if trades.get('tradeBook'):
                last_trade = trades['tradeBook'][0] if trades['tradeBook'] else None
                if last_trade and 'orderDateTime' in last_trade:
                    last_order_time = last_trade['orderDateTime']
            
            return {
                'total_orders': total_orders,
                'successful_orders': successful_orders,
                'pending_orders': pending_orders,
                'failed_orders': failed_orders,
                'last_order_time': last_order_time,
                'api_response_time': '-'
            }
        except Exception as e:
            logger.error(f"Error getting detailed broker stats: {str(e)}")
            return {
                'total_orders': 0,
                'successful_orders': 0,
                'pending_orders': 0,
                'failed_orders': 0,
                'last_order_time': '-',
                'api_response_time': '-'
            }
    
    def _get_sector_for_symbol(self, symbol: str) -> str:
        """Get sector for a given symbol - simplified implementation."""
        # This is a simplified implementation
        # In a real system, you would have a database of symbols and their sectors
        # or use an external API to get sector information
        
        # Common sector mappings for Indian stocks
        sector_mappings = {
            'RELIANCE': 'Energy',
            'TCS': 'Technology',
            'INFY': 'Technology',
            'HDFC': 'Banking',
            'HDFCBANK': 'Banking',
            'ICICIBANK': 'Banking',
            'SBIN': 'Banking',
            'ITC': 'FMCG',
            'HINDUNILVR': 'FMCG',
            'MARUTI': 'Auto',
            'BAJFINANCE': 'Financial Services',
            'BHARTIARTL': 'Telecom',
            'ASIANPAINT': 'Paints',
            'NESTLEIND': 'FMCG',
            'ULTRACEMCO': 'Cement',
            'TITAN': 'Consumer Goods',
            'SUNPHARMA': 'Pharma',
            'DRREDDY': 'Pharma',
            'CIPLA': 'Pharma',
            'WIPRO': 'Technology',
            'LT': 'Infrastructure',
            'BAJAJFINSV': 'Financial Services',
            'KOTAKBANK': 'Banking',
            'AXISBANK': 'Banking',
            'POWERGRID': 'Power',
            'NTPC': 'Power',
            'ONGC': 'Energy',
            'COALINDIA': 'Energy',
            'TATAMOTORS': 'Auto',
            'M&M': 'Auto',
            'HEROMOTOCO': 'Auto',
            'EICHERMOT': 'Auto',
            'BAJAJ-AUTO': 'Auto',
            'TECHM': 'Technology',
            'HCLTECH': 'Technology',
            'MINDTREE': 'Technology',
            'LTI': 'Technology',
            'MPHASIS': 'Technology'
        }
        
        # Extract clean symbol name
        clean_symbol = symbol.split(':')[-1].split('-')[0] if ':' in symbol else symbol.split('-')[0]
        
        return sector_mappings.get(clean_symbol, 'Others')
    
    def _get_market_cap_category(self, price: float) -> str:
        """Get market cap category based on price - simplified implementation."""
        # This is a very simplified implementation
        # In reality, you would need market cap data from external sources
        
        if price > 2000:
            return 'Large Cap'
        elif price > 500:
            return 'Mid Cap'
        else:
            return 'Small Cap'
    
    def _extract_symbol_name(self, symbol: str) -> str:
        """Extract clean symbol name from formatted symbol."""
        if ':' in symbol:
            parts = symbol.split(':')
            if len(parts) > 1:
                name_part = parts[1].split('-')[0]
                return name_part
        return symbol


# Global service instance
_fyers_service = None

def get_fyers_service() -> FyersService:
    """Get the global Fyers service instance."""
    global _fyers_service
    if _fyers_service is None:
        _fyers_service = FyersService()
    return _fyers_service
