"""
Service for portfolio-related logic.
"""
import logging
from datetime import datetime
from ..core.broker_service import get_broker_service

logger = logging.getLogger(__name__)

class PortfolioService:
    def __init__(self, broker_service):
        self.broker_service = broker_service

    def get_portfolio_holdings(self, user_id: int):
        """Get portfolio holdings using FYERS API."""
        # Debug print removed for clean console
        try:
            holdings_data = self.broker_service.get_fyers_holdings(user_id)
        # Debug print removed for clean console

            # Check if the response is successful (FYERS format: 's': 'ok')
            if holdings_data.get('s') == 'ok':
                holdings = holdings_data.get('holdings', [])

                processed_holdings = []
                for holding in holdings:
                    processed_holdings.append({
                        'symbol': holding.get('symbol', ''),
                        'quantity': holding.get('quantity', 0),
                        'average_price': holding.get('average_price', 0),
                        'market_value': holding.get('market_value', 0),
                        'pnl': holding.get('pnl', 0),
                        'pnl_percent': holding.get('pnl_percent', 0),
                        'ltp': holding.get('ltp', 0)
                    })

                return {
                    'success': True,
                    'data': processed_holdings,
                    'last_updated': datetime.now().isoformat()
                }
            else:
                error_msg = holdings_data.get('message', 'Unknown error')
        # Debug print removed for clean console
                return {
                    'success': False,
                    'error': f'Failed to fetch holdings data from FYERS: {error_msg}'
                }
        except Exception as e:
        # Debug print removed for clean console
            return {
                'success': False,
                'error': f'Failed to fetch holdings data from FYERS: {str(e)}'
            }

    def get_portfolio_positions(self, user_id: int):
        """Get portfolio positions using FYERS API."""
        # Debug print removed for clean console
        try:
        # Debug print removed for clean console
            positions_data = self.broker_service.get_fyers_positions(user_id)
        # Debug print removed for clean console
            logger.info(f"Portfolio positions response: {positions_data}")

            # Check if the response is successful (FYERS format: 's': 'ok')
            if positions_data.get('s') == 'ok':
                positions = positions_data.get('netPositions', [])
        # Debug print removed for clean console

                processed_positions = []
                for position in positions:
                    # Normalize FYERS fields and add defensive defaults
                    avg_price = position.get('average_price')
                    if avg_price in (None, 0):
                        avg_price = position.get('buyAvg', position.get('netAvg', 0))
                    quantity = position.get('quantity', position.get('netQty', position.get('qty', 0)))
                    pnl_val = position.get('pnl', position.get('pl', 0))
                    ltp_val = position.get('ltp', position.get('last_price', 0))
                    side_raw = position.get('side', '')
                    side = 'long' if side_raw == 1 or str(side_raw).lower() == 'long' else ('short' if side_raw == -1 else side_raw)
                    product = position.get('product', position.get('productType', ''))

                    # Debug each mapped position clearly for docker logs
        # Debug print removed for clean console

                    processed_positions.append({
                        'symbol': position.get('symbol', ''),
                        'quantity': quantity,
                        'average_price': avg_price,
                        'ltp': ltp_val,
                        'pnl': pnl_val,
                        'pnl_percent': position.get('plPercent', position.get('pnl_percent', 0)),
                        'side': side,
                        'product': product
                    })

                return {
                    'success': True,
                    'data': processed_positions,
                    'last_updated': datetime.now().isoformat()
                }
            else:
                error_msg = positions_data.get('message', 'Unknown error')
        # Debug print removed for clean console
                logger.error(f"Failed to fetch positions data: {error_msg}")
                return {
                    'success': False,
                    'error': f'Failed to fetch positions data from FYERS: {error_msg}'
                }
        except Exception as e:
        # Debug print removed for clean console
            logger.error(f"Exception in get_portfolio_positions: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to fetch positions data from FYERS: {str(e)}'
            }

_portfolio_service = None

def get_portfolio_service():
    """Singleton factory for PortfolioService."""
    global _portfolio_service
    if _portfolio_service is None:
        broker_service = get_broker_service()
        _portfolio_service = PortfolioService(broker_service)
    return _portfolio_service
