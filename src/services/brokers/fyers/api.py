"""
Fyers API Implementation

This module provides a comprehensive Fyers API implementation with standardized
response formats and error handling.
"""

import logging
import time
import hashlib
import hmac
import base64
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlencode

# No custom config needed - using official fyers_apiv3 library

logger = logging.getLogger(__name__)

class FyersAPI:
    """
    Comprehensive Fyers API implementation using the official fyers_apiv3 library.
    """
    
    def __init__(self, api_key: str, api_secret: str, access_token: str):
        """Initialize Fyers API with credentials using official library."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        # Official library handles everything internally
        
        # Import the official library
        try:
            from fyers_apiv3 import fyersModel
            self.fyersModel = fyersModel
            
            # Create FyersModel instance for API calls
            self.fyers_client = fyersModel.FyersModel(
                token=access_token,
                is_async=False,
                client_id=api_key,
                log_path=""
            )
        except ImportError:
            logger.error("fyers_apiv3 library not available. Please install it using: pip install fyers-apiv3")
            raise ImportError("fyers_apiv3 library not available")
    
    def _make_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> Dict[str, Any]:
        """
        Make API request using the official FYERS library.
        This is a compatibility method for existing code.
        """
        try:
            if method == 'GET':
                if endpoint == 'quotes':
                    symbols = params.get('symbols', '') if params else ''
                    response = self.fyers_client.quotes(symbols)
                elif endpoint == 'orderbook':
                    response = self.fyers_client.orderbook()
                elif endpoint == 'tradebook':
                    response = self.fyers_client.tradebook()
                elif endpoint == 'positions':
                    response = self.fyers_client.positions()
                elif endpoint == 'holdings':
                    response = self.fyers_client.holdings()
                elif endpoint == 'funds':
                    response = self.fyers_client.funds()
                else:
                    return {'status': 'error', 'message': f'GET endpoint {endpoint} not implemented'}
                
                # Standardize response format
                return self._standardize_response(response)
            
            elif method == 'POST':
                if endpoint == 'orders':
                    response = self.fyers_client.placeorder(**data)
                elif endpoint == 'depth':
                    response = self.fyers_client.depth(**data)
                elif endpoint == 'history':
                    response = self.fyers_client.history(data=data)
                elif endpoint == 'search_scrips':
                    # This endpoint is deprecated - use the search() method instead
                    return {'status': 'error', 'message': 'Use search() method instead of search_scrips endpoint', 'error_code': 'DEPRECATED_ENDPOINT'}
                else:
                    return {'status': 'error', 'message': f'POST endpoint {endpoint} not implemented'}
                
                # Standardize response format
                return self._standardize_response(response)
            
            elif method == 'PUT':
                if endpoint == 'orders':
                    response = self.fyers_client.modify_order(data=data)
                else:
                    return {'status': 'error', 'message': f'PUT endpoint {endpoint} not implemented'}

                # Standardize response format
                return self._standardize_response(response)

            elif method == 'DELETE':
                if endpoint == 'orders':
                    response = self.fyers_client.cancel_order(data=data)
                else:
                    return {'status': 'error', 'message': f'DELETE endpoint {endpoint} not implemented'}
                
                # Standardize response format
                return self._standardize_response(response)
            
            else:
                return {'status': 'error', 'message': f'Method {method} not supported'}
                
        except Exception as e:
            logger.error(f"API request error for {method} {endpoint}: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'API_REQUEST_FAILED'
            }
    
    def _standardize_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Standardize FYERS API response format."""
        try:
            # Log the raw response for debugging
            logger.info(f"Raw FYERS API response: {response}")
            logger.info(f"Response type: {type(response)}")
            logger.info(f"Response keys: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}")

            # Check if response has 's' field (FYERS status)
            if isinstance(response, dict) and 's' in response:
                if response['s'] == 'ok':
                    logger.info("FYERS API response: SUCCESS")

                    # Extract the correct data field based on what's available
                    data = {}
                    if 'netPositions' in response:
                        data = response['netPositions']
                    elif 'holdings' in response:
                        data = response['holdings']
                    elif 'orderBook' in response:
                        data = response['orderBook']
                    elif 'tradeBook' in response:
                        data = response['tradeBook']
                    elif 'fund_limit' in response:
                        data = response['fund_limit']
                    elif 'data' in response:
                        data = response['data']
                    else:
                        # Return the whole response minus status fields
                        data = {k: v for k, v in response.items() if k not in ['s', 'code', 'message']}

                    return {
                        'status': 'success',
                        'data': data,
                        'message': 'Success'
                    }
                else:
                    logger.warning(f"FYERS API response: ERROR - {response.get('message', 'Unknown error')}")
                    return {
                        'status': 'error',
                        'message': response.get('message', 'API Error'),
                        'error_code': response.get('code', 'UNKNOWN_ERROR')
                    }
            
            # If no 's' field, assume success if response is not empty
            elif response:
                logger.info("FYERS API response: SUCCESS (no 's' field)")
                return {
                    'status': 'success',
                    'data': response,
                    'message': 'Success'
                }
            
            # Empty response
            else:
                logger.warning("FYERS API response: EMPTY")
                return {
                    'status': 'error',
                    'message': 'Empty response from API',
                    'error_code': 'EMPTY_RESPONSE'
                }
                
        except Exception as e:
            logger.error(f"Error standardizing response: {str(e)}")
            logger.error(f"Response that caused error: {response}")
            return {
                'status': 'error',
                'message': f'Response parsing error: {str(e)}',
                'error_code': 'RESPONSE_PARSE_ERROR'
            }
    
    # Authentication and Session Management
    def login(self) -> Dict[str, Any]:
        """
        Validate login credentials and session using official library.
        Check if access token is valid.
        """
        try:
            # Use official library to get profile
            result = self.fyers_client.get_profile()
            
            # Handle response from FYERS API
            if isinstance(result, dict):
                if result.get('s') == 'ok':
                    return {
                        'status': 'success',
                        'message': 'Login successful',
                        'data': {
                            'login_status': True,
                            'profile': result.get('data', {})
                        }
                    }
                else:
                    return {
                        'status': 'error',
                        'message': result.get('message', 'Login failed - Invalid credentials or expired token'),
                        'data': {'login_status': False}
                    }
            else:
                return {
                    'status': 'error',
                    'message': 'Unexpected response format from FYERS API',
                    'data': {'login_status': False}
                }
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'data': {'login_status': False}
            }
    
    # Order Management
    def placeorder(self, symbol: str, quantity: str, action: str, 
                   product: str, pricetype: str, price: str = "0", 
                   trigger_price: str = "0", disclosed_quantity: str = "0",
                   validity: str = "DAY", tag: str = "") -> Dict[str, Any]:
        """
        Place a new order with standardized parameters.
        """
        try:
            # Map parameters to Fyers format
            side = 1 if action.upper() == 'BUY' else -1
            
            # Map price types
            order_type_map = {
                'MARKET': 2,
                'LIMIT': 1,
                'SL': 3,  # Stop Loss Market
                'SL-M': 3,  # Stop Loss Market  
                'SL-L': 4   # Stop Loss Limit
            }
            
            order_data = {
                "symbol": symbol,
                "qty": int(quantity),
                "type": order_type_map.get(pricetype.upper(), 2),
                "side": side,
                "productType": product.upper(),
                "validity": validity.upper(),
                "disclosedQty": int(disclosed_quantity) if disclosed_quantity else 0,
                "orderTag": tag
            }
            
            # Add price fields based on order type
            if pricetype.upper() != 'MARKET':
                order_data["limitPrice"] = float(price) if price and price != "0" else 0
                
            if pricetype.upper() in ['SL', 'SL-M', 'SL-L']:
                order_data["stopPrice"] = float(trigger_price) if trigger_price and trigger_price != "0" else 0
            
            # Use official library to place order
            result = self.fyers_client.place_order(order_data)
            
            if result.get('s') == 'ok':
                order_id = result.get('data', {}).get('id', '')
                return {
                    'status': 'success',
                    'message': 'Order placed successfully',
                    'data': {'orderid': order_id}
                }
            else:
                return {
                    'status': 'error',
                    'message': result.get('message', 'Order placement failed'),
                    'error_code': result.get('code', 'ORDER_ERROR')
                }
                
        except Exception as e:
            logger.error(f"Place order error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'PLACE_ORDER_FAILED'
            }
    
    def modifyorder(self, orderid: str, symbol: str = "", quantity: str = "",
                    price: str = "", trigger_price: str = "", 
                    disclosed_quantity: str = "", validity: str = "") -> Dict[str, Any]:
        """
        Modify an existing order.
        """
        try:
            modify_data = {"id": orderid}
            
            # Add fields to modify
            if quantity:
                modify_data["qty"] = int(quantity)
            if price and price != "0":
                modify_data["limitPrice"] = float(price)
            if trigger_price and trigger_price != "0":
                modify_data["stopPrice"] = float(trigger_price)
            if disclosed_quantity:
                modify_data["disclosedQty"] = int(disclosed_quantity)
            if validity:
                modify_data["validity"] = validity.upper()
            
            result = self._make_request('PUT', 'orders', data=modify_data)
            
            if result['status'] == 'success':
                return {
                    'status': 'success',
                    'message': 'Order modified successfully',
                    'data': {'orderid': orderid}
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Modify order error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'MODIFY_ORDER_FAILED'
            }
    
    def cancelorder(self, orderid: str) -> Dict[str, Any]:
        """
        Cancel an existing order.
        """
        try:
            cancel_data = {"id": orderid}
            result = self._make_request('DELETE', 'orders', data=cancel_data)
            
            if result['status'] == 'success':
                return {
                    'status': 'success',
                    'message': 'Order cancelled successfully',
                    'data': {'orderid': orderid}
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Cancel order error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'CANCEL_ORDER_FAILED'
            }
    
    # Smart Order Management  
    def placesmartorder(self, symbol: str, action: str, product: str,
                       quantity: str = "", position_size: str = "",
                       price: str = "0", trigger_price: str = "0",
                       pricetype: str = "MARKET", strategy: str = "",
                       tag: str = "") -> Dict[str, Any]:
        """
        Place smart order with position sizing.
        """
        try:
            # Calculate actual quantity if position_size is provided
            if position_size and not quantity:
                # Get current positions to calculate quantity based on position size
                positions_result = self.positions()
                if positions_result['status'] == 'success':
                    # Calculate quantity based on position size logic
                    # This is a simplified implementation
                    quantity = position_size
            
            # Use regular place order
            return self.placeorder(
                symbol=symbol,
                quantity=quantity or position_size,
                action=action,
                product=product,
                pricetype=pricetype,
                price=price,
                trigger_price=trigger_price,
                tag=f"{strategy}_{tag}" if strategy else tag
            )
            
        except Exception as e:
            logger.error(f"Place smart order error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'PLACE_SMART_ORDER_FAILED'
            }
    
    # Account Information
    def orderbook(self) -> Dict[str, Any]:
        """
        Get order book with standard format using official library.
        """
        try:
            result = self._make_request('GET', 'orderbook')
            
            if result.get('status') == 'success':
                orders = result.get('data', [])
                formatted_orders = []
                
                for order in orders:
                    formatted_order = {
                        'orderid': order.get('id', ''),
                        'symbol': order.get('symbol', ''),
                        'product': order.get('productType', ''),
                        'action': 'BUY' if order.get('side', 1) == 1 else 'SELL',
                        'quantity': str(order.get('qty', 0)),
                        'price': str(order.get('limitPrice', 0)),
                        'trigger_price': str(order.get('stopPrice', 0)),
                        'pricetype': self._get_order_type_name(order.get('type', 2)),
                        'status': self._get_order_status_name(order.get('status', 1)),
                        'timestamp': order.get('orderDateTime', ''),
                        'filled_quantity': str(order.get('filledQty', 0)),
                        'remaining_quantity': str(order.get('remainingQty', 0)),
                        'average_price': str(order.get('avgPrice', 0)),
                        'exchange': self._extract_exchange(order.get('symbol', '')),
                        'tag': order.get('orderTag', '')
                    }
                    formatted_orders.append(formatted_order)
                
                return {
                    'status': 'success',
                    'data': formatted_orders
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Order book error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'ORDERBOOK_FAILED'
            }
    
    def tradebook(self) -> Dict[str, Any]:
        """
        Get trade book with standard format.
        """
        try:
            result = self._make_request('GET', 'tradebook')
            
            if result.get('status') == 'success':
                trades = result.get('data', [])
                formatted_trades = []
                
                for trade in trades:
                    formatted_trade = {
                        'tradeid': trade.get('id', ''),
                        'orderid': trade.get('orderNumber', ''),
                        'symbol': trade.get('symbol', ''),
                        'product': trade.get('productType', ''),
                        'action': 'BUY' if trade.get('side', 1) == 1 else 'SELL',
                        'quantity': str(trade.get('qty', 0)),
                        'price': str(trade.get('tradePrice', 0)),
                        'timestamp': trade.get('tradeDateTime', ''),
                        'exchange': self._extract_exchange(trade.get('symbol', '')),
                        'tag': trade.get('orderTag', '')
                    }
                    formatted_trades.append(formatted_trade)
                
                return {
                    'status': 'success',
                    'data': formatted_trades
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Trade book error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'TRADEBOOK_FAILED'
            }
    
    def positions(self) -> Dict[str, Any]:
        """
        Get positions with standard format.
        """
        try:
            result = self._make_request('GET', 'positions')
            
            if result.get('status') == 'success':
                positions = result.get('data', [])
                formatted_positions = []
                
                for position in positions:
                    formatted_position = {
                        'symbol': position.get('symbol', ''),
                        'product': position.get('productType', ''),
                        'quantity': str(position.get('netQty', 0)),
                        'average_price': str(position.get('netAvg', 0)),
                        'last_price': str(position.get('ltp', 0)),
                        'pnl': str(position.get('pl', 0)),
                        'exchange': self._extract_exchange(position.get('symbol', ''))
                    }
                    formatted_positions.append(formatted_position)
                
                return {
                    'status': 'success',
                    'data': formatted_positions
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Positions error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'POSITIONS_FAILED'
            }
    
    def holdings(self) -> Dict[str, Any]:
        """
        Get holdings with standard format.
        """
        try:
            result = self._make_request('GET', 'holdings')
            
            if result.get('status') == 'success':
                holdings = result.get('data', [])
                formatted_holdings = []
                
                for holding in holdings:
                    # remainingQuantity = actual sellable qty after T+1 settlements
                    # quantity = total demat qty (may include just-sold-pending-debit)
                    rem = holding.get('remainingQuantity')
                    qty_field = holding.get('quantity', 0)
                    qty = rem if rem is not None else qty_field
                    formatted_holding = {
                        'symbol': holding.get('symbol', ''),
                        'quantity': str(qty or 0),
                        'remaining_quantity': str(rem if rem is not None else qty_field),
                        'average_price': str(holding.get('costPrice', 0)),
                        'last_price': str(holding.get('ltp', 0)),
                        'pnl': str(holding.get('pl', 0)),
                        'market_value': str(holding.get('marketVal', 0)),
                        'exchange': self._extract_exchange(holding.get('symbol', ''))
                    }
                    formatted_holdings.append(formatted_holding)
                
                return {
                    'status': 'success',
                    'data': formatted_holdings
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Holdings error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'HOLDINGS_FAILED'
            }
    
    def funds(self) -> Dict[str, Any]:
        """
        Get account funds with standard format.
        """
        try:
            result = self._make_request('GET', 'funds')
            
            if result.get('status') == 'success':
                fund_data = result.get('data', [])
                
                # Extract key fund information
                funds_info = {
                    'available_cash': '0',
                    'utilized_margin': '0',
                    'total_margin': '0'
                }
                
                # Fyers fund_limit titles (verified from prod payload):
                # 1=Total Balance, 2=Utilized Amount, 3=Clear Balance,
                # 4=Realized P&L, 5=Collaterals, 6=Fund Transfer,
                # 7=Receivables, 8=Adhoc Limit, 9=Limit start of day,
                # 10=Available Balance
                for fund in fund_data:
                    title = fund.get('title', '')
                    if title in ('Available Balance', 'Available Cash'):
                        funds_info['available_cash'] = str(fund.get('equityAmount', 0))
                    elif title == 'Total Balance':
                        funds_info['total_margin'] = str(fund.get('equityAmount', 0))
                    elif title in ('Utilized Amount', 'Utilized Margin'):
                        funds_info['utilized_margin'] = str(fund.get('equityAmount', 0))
                
                return {
                    'status': 'success',
                    'data': funds_info
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Funds error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'FUNDS_FAILED'
            }
    
    # Market Data
    def quotes(self, symbol: str, exchange: str = "") -> Dict[str, Any]:
        """
        Get real-time quotes with standard format using official library.
        """
        try:
            # Format symbol for Fyers API
            if exchange and ":" not in symbol:
                formatted_symbol = f"{exchange}:{symbol}"
            else:
                formatted_symbol = symbol
            
            # Use official library to get quotes
            result = self.fyers_client.quotes(data={"symbols": formatted_symbol})
            
            if result.get('s') == 'ok':
                quotes_data = result.get('d', [])
                
                # Find the symbol in the response array
                quote_data = None
                for item in quotes_data:
                    if item.get('n') == formatted_symbol and item.get('s') == 'ok':
                        quote_data = item.get('v')
                        break
                
                if quote_data:
                    
                    formatted_quote = {
                        'symbol': symbol,
                        'exchange': exchange or self._extract_exchange(formatted_symbol),
                        'ltp': str(quote_data.get('lp', 0)),
                        'open': str(quote_data.get('open_price', 0)),
                        'high': str(quote_data.get('high_price', 0)),
                        'low': str(quote_data.get('low_price', 0)),
                        'prev_close': str(quote_data.get('prev_close_price', 0)),
                        'change': str(quote_data.get('ch', 0)),
                        'change_percent': str(quote_data.get('chp', 0)),
                        'volume': str(quote_data.get('volume', 0)),
                        'bid': str(quote_data.get('bid', 0)),
                        'ask': str(quote_data.get('ask', 0)),
                        'timestamp': str(quote_data.get('tt', ''))
                    }
                    
                    return {
                        'status': 'success',
                        'data': formatted_quote
                    }
                else:
                    return {
                        'status': 'error',
                        'message': 'Symbol not found in quotes data',
                        'error_code': 'SYMBOL_NOT_FOUND'
                    }
            else:
                return {
                    'status': 'error',
                    'message': result.get('message', 'Failed to get quotes'),
                    'error_code': 'QUOTES_FAILED'
                }
                
        except Exception as e:
            logger.error(f"Quotes error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'QUOTES_FAILED'
            }
    
    def quotes_multiple(self, symbols: list) -> Dict[str, Any]:
        """
        Get real-time quotes for multiple symbols with standard format.
        """
        try:
            # Format symbols for Fyers API
            import urllib.parse
            formatted_symbols = []
            for symbol in symbols:
                # URL encode symbols to handle special characters like &
                encoded_symbol = urllib.parse.quote(symbol, safe=':,-')
                formatted_symbols.append(encoded_symbol)

            # Use official library to get quotes
            result = self.fyers_client.quotes(data={"symbols": ",".join(formatted_symbols)})
            
            if result.get('s') == 'ok':
                quotes_data = result.get('d', [])
                formatted_quotes = {}
                
                # Process each item in the response array
                for item in quotes_data:
                    if item.get('s') == 'ok':
                        symbol_name = item.get('n')
                        quote_data = item.get('v')
                        
                        if symbol_name and quote_data:
                            formatted_quotes[symbol_name] = {
                                'symbol': symbol_name,
                                'ltp': str(quote_data.get('lp', 0)),
                                'open': str(quote_data.get('open_price', 0)),
                                'high': str(quote_data.get('high_price', 0)),
                                'low': str(quote_data.get('low_price', 0)),
                                'prev_close': str(quote_data.get('prev_close_price', 0)),
                                'change': str(quote_data.get('ch', 0)),
                                'change_percent': str(quote_data.get('chp', 0)),
                                'volume': str(quote_data.get('volume', 0)),
                                'bid': str(quote_data.get('bid', 0)),
                                'ask': str(quote_data.get('ask', 0)),
                                'timestamp': str(quote_data.get('tt', ''))
                            }
                
                return {
                    'status': 'success',
                    'data': formatted_quotes
                }
            else:
                return {
                    'status': 'error',
                    'message': result.get('message', 'Failed to get quotes'),
                    'error_code': 'QUOTES_MULTIPLE_FAILED'
                }
                
        except Exception as e:
            logger.error(f"Multiple quotes error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'QUOTES_MULTIPLE_FAILED'
            }
    
    def depth(self, symbol: str, exchange: str = "") -> Dict[str, Any]:
        """
        Get market depth with standard format.
        """
        try:
            # Format symbol for Fyers API
            if exchange and ":" not in symbol:
                formatted_symbol = f"{exchange}:{symbol}"
            else:
                formatted_symbol = symbol
            
            depth_data = {
                "symbol": [formatted_symbol],
                "ohlcv_flag": 1
            }
            
            result = self._make_request('POST', 'depth', data=depth_data)
            
            if result['status'] == 'success':
                depth_info = result.get('data', {}).get('d', {})
                
                if formatted_symbol in depth_info:
                    market_depth = depth_info[formatted_symbol]['v']
                    
                    formatted_depth = {
                        'symbol': symbol,
                        'exchange': exchange or self._extract_exchange(formatted_symbol),
                        'ltp': str(market_depth.get('lp', 0)),
                        'bid': [],
                        'ask': []
                    }
                    
                    # Extract bid/ask data if available
                    if 'bid' in market_depth:
                        for i in range(5):  # Top 5 levels
                            bid_key = f"bid_price_{i+1}"
                            bid_qty_key = f"bid_size_{i+1}"
                            if bid_key in market_depth:
                                formatted_depth['bid'].append({
                                    'price': str(market_depth.get(bid_key, 0)),
                                    'quantity': str(market_depth.get(bid_qty_key, 0))
                                })
                    
                    if 'ask' in market_depth:
                        for i in range(5):  # Top 5 levels
                            ask_key = f"ask_price_{i+1}"
                            ask_qty_key = f"ask_size_{i+1}"
                            if ask_key in market_depth:
                                formatted_depth['ask'].append({
                                    'price': str(market_depth.get(ask_key, 0)),
                                    'quantity': str(market_depth.get(ask_qty_key, 0))
                                })
                    
                    return {
                        'status': 'success',
                        'data': formatted_depth
                    }
                else:
                    return {
                        'status': 'error',
                        'message': 'Symbol not found in depth data',
                        'error_code': 'SYMBOL_NOT_FOUND'
                    }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Depth error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'DEPTH_FAILED'
            }
    
    def history(self, symbol: str, exchange: str, interval: str,
                start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Get historical data with standard format.
        """
        try:
            # Format symbol for Fyers API
            if ":" not in symbol:
                formatted_symbol = f"{exchange}:{symbol}"
            else:
                formatted_symbol = symbol
            
            # Map intervals to Fyers format
            interval_map = {
                '1m': '1',
                '3m': '3',
                '5m': '5',
                '10m': '10',
                '15m': '15',
                '30m': '30',
                '1h': '60',
                '2h': '120',
                '3h': '180',
                '4h': '240',
                '1d': 'D',
                '1D': 'D',
                'D': 'D'
            }
            
            fyers_interval = interval_map.get(interval, 'D')
            
            # Convert date format if needed
            try:
                start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
                end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp())
            except:
                # Try with timestamp format
                start_ts = int(start_date) if start_date.isdigit() else int(datetime.now().timestamp()) - 86400*30
                end_ts = int(end_date) if end_date.isdigit() else int(datetime.now().timestamp())
            
            history_data = {
                "symbol": formatted_symbol,
                "resolution": fyers_interval,
                "date_format": "0",  # Unix timestamp
                "range_from": str(start_ts),
                "range_to": str(end_ts),
                "cont_flag": "1"
            }
            
            result = self._make_request('POST', 'history', data=history_data)
            
            if result['status'] == 'success':
                candles = result.get('data', {}).get('candles', [])
                
                formatted_candles = []
                for candle in candles:
                    if len(candle) >= 6:
                        formatted_candles.append({
                            'timestamp': str(candle[0]),
                            'open': str(candle[1]),
                            'high': str(candle[2]),
                            'low': str(candle[3]),
                            'close': str(candle[4]),
                            'volume': str(candle[5])
                        })
                
                return {
                    'status': 'success',
                    'data': {
                        'symbol': symbol,
                        'exchange': exchange,
                        'interval': interval,
                        'candles': formatted_candles
                    }
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"History error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'HISTORY_FAILED'
            }
    
    # Search and Symbol Information
    def search(self, symbol: str, exchange: str = "") -> Dict[str, Any]:
        """
        Search for symbols using Fyers Symbol Service.
        """
        try:
            # Import here to avoid circular imports
            from src.services.data.fyers_symbol_service import get_fyers_symbol_service

            # Get symbol service
            symbol_service = get_fyers_symbol_service()

            # Use NSE by default if no exchange specified
            search_exchange = exchange.upper() if exchange else "NSE"

            # Search symbols using the symbol service
            search_results = symbol_service.search_symbols(symbol, search_exchange, limit=50)

            if search_results:
                formatted_results = []

                for item in search_results:
                    formatted_result = {
                        'symbol': item.get('symbol', ''),
                        'name': item.get('name', ''),
                        'exchange': item.get('exchange', ''),
                        'segment': item.get('segment', ''),
                        'instrument_type': item.get('instrument_type', ''),
                        'lot': item.get('lot', 1),
                        'tick': item.get('tick', 0.05),
                        'fytoken': item.get('fytoken', '')
                    }
                    formatted_results.append(formatted_result)

                return {
                    'status': 'success',
                    'data': formatted_results
                }
            else:
                return {
                    'status': 'success',
                    'data': []
                }

        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'SEARCH_FAILED'
            }
    
    # Utility Methods
    def _get_order_type_name(self, order_type: int) -> str:
        """Convert Fyers order type number to standard format."""
        type_mapping = {
            1: 'LIMIT',
            2: 'MARKET',
            3: 'SL-M',
            4: 'SL-L'
        }
        return type_mapping.get(order_type, 'MARKET')
    
    def _get_order_status_name(self, status: int) -> str:
        """Convert Fyers order status number to standard format.

        Per Fyers API v3 docs:
          1 = Cancelled
          2 = Traded / Filled
          4 = Transit
          5 = Rejected
          6 = Pending
        """
        status_mapping = {
            1: 'CANCELLED',
            2: 'COMPLETE',
            4: 'TRANSIT',
            5: 'REJECTED',
            6: 'PENDING',
        }
        return status_mapping.get(status, 'PENDING')
    
    def _extract_exchange(self, symbol: str) -> str:
        """Extract exchange from symbol."""
        if ':' in symbol:
            return symbol.split(':')[0]
        return 'NSE'  # Default
    
    def _extract_symbol_name(self, symbol: str) -> str:
        """Extract clean symbol name."""
        if ':' in symbol:
            parts = symbol.split(':')
            if len(parts) > 1:
                name_part = parts[1].split('-')[0]
                return name_part
        return symbol


# Authentication and session management utilities using official fyers_apiv3 library
class FyersAuth:
    """
    Fyers authentication utilities using the official fyers_apiv3 library.
    """
    
    def __init__(self, client_id: str, secret_key: str, redirect_uri: str):
        self.client_id = client_id
        self.secret_key = secret_key
        self.redirect_uri = redirect_uri
        
        # Import the official library
        try:
            from fyers_apiv3 import fyersModel
            self.fyersModel = fyersModel
        except ImportError:
            logger.error("fyers_apiv3 library not available. Please install it using: pip install fyers-apiv3")
            raise ImportError("fyers_apiv3 library not available")
    
    def generate_auth_url(self, state: str = "trading") -> str:
        """Generate authorization URL for OAuth flow using official library."""
        try:
            # Create session model using official library
            session = self.fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code",
                state=state,
                grant_type="authorization_code"
            )
            
            # Generate the auth code URL
            auth_url = session.generate_authcode()
            return auth_url
            
        except Exception as e:
            logger.error(f"Error generating auth URL: {str(e)}")
            raise
    
    def generate_access_token(self, auth_code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token using official library."""
        try:
            # Create session model for token exchange
            session = self.fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )
            
            # Set the auth code
            session.set_token(auth_code)
            
            # Generate access token
            response = session.generate_token()
            
            if response.get('s') == 'ok':
                return {
                    'status': 'success',
                    'access_token': response.get('access_token'),
                    'refresh_token': response.get('refresh_token', ''),
                    'message': 'Token generated successfully'
                }
            else:
                return {
                    'status': 'error',
                    'message': response.get('message', 'Token generation failed'),
                    'error_code': response.get('code', 'TOKEN_ERROR')
                }
                
        except Exception as e:
            logger.error(f"Token generation error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'error_code': 'TOKEN_GENERATION_FAILED'
            }


# Factory function for creating API instances
def create_fyers_api(api_key: str, api_secret: str, access_token: str) -> FyersAPI:
    """
    Factory function to create Fyers API instance.
    """
    return FyersAPI(api_key, api_secret, access_token)


def create_fyers_auth(client_id: str, secret_key: str, redirect_uri: str) -> FyersAuth:
    """
    Factory function to create Fyers authentication instance.
    """
    return FyersAuth(client_id, secret_key, redirect_uri)
