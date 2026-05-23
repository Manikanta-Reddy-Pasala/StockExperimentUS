"""
FYERS Broker API Routes - Dedicated routes for FYERS broker operations
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory
from flask_login import login_required, current_user
import logging
import os

# Configure logging
logger = logging.getLogger(__name__)

try:
    from ...services.brokers.fyers_service import get_fyers_service
except ImportError:
    try:
        from services.brokers.fyers_service import get_fyers_service
    except ImportError:
        from src.services.brokers.fyers_service import get_fyers_service

# Create Blueprint for FYERS routes
fyers_bp = Blueprint('fyers', __name__, url_prefix='/brokers/fyers')

@fyers_bp.route('/')
@login_required
def fyers_page():
    """FYERS broker configuration page."""
    return render_template('brokers/fyers.html')

@fyers_bp.route('/api/info', methods=['GET'])
@login_required
def api_get_fyers_info():
    """Get FYERS broker information with token expiry details."""
    try:
        fyers_service = get_fyers_service()
        config = fyers_service.get_broker_config(current_user.id)

        if not config:
            return jsonify({
                'success': True,
                'broker': 'fyers',
                'client_id': '',
                'access_token': False,
                'connected': False,
                'last_updated': '-',
                'token_expiry': None,
                'token_expires_in_hours': None,
                'token_expiring_soon': False,
                'stats': {'total_orders': 0, 'successful_orders': 0, 'pending_orders': 0,
                        'failed_orders': 0, 'last_order_time': '-', 'api_response_time': '-'}
            })

        # Get token expiry information
        token_expiry_info = {}
        if config.get('access_token'):
            try:
                from src.services.utils.token_manager_service import get_token_manager
                token_manager = get_token_manager()

                # Get token status
                token_status = token_manager.get_token_status(current_user.id, 'fyers')

                if token_status.get('expires_at'):
                    from datetime import datetime
                    expiry_time = datetime.fromisoformat(token_status['expires_at'])
                    time_until_expiry = expiry_time - datetime.now()
                    hours_until_expiry = time_until_expiry.total_seconds() / 3600

                    token_expiry_info = {
                        'token_expiry': token_status['expires_at'],
                        'token_expires_in_hours': round(hours_until_expiry, 1),
                        'token_expiring_soon': hours_until_expiry < 12,
                        'token_is_expired': token_status.get('is_expired', False)
                    }
                else:
                    token_expiry_info = {
                        'token_expiry': None,
                        'token_expires_in_hours': None,
                        'token_expiring_soon': False,
                        'token_is_expired': False
                    }
            except Exception as e:
                logger.warning(f"Could not get token expiry info: {e}")
                token_expiry_info = {
                    'token_expiry': None,
                    'token_expires_in_hours': None,
                    'token_expiring_soon': False,
                    'token_is_expired': False
                }

        stats = fyers_service.get_broker_stats(current_user.id)
        config['access_token'] = bool(config.get('access_token'))

        return jsonify({
            'success': True,
            'broker': 'fyers',
            **config,
            **token_expiry_info,
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Error getting FYERS broker info for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@fyers_bp.route('/api/test', methods=['POST'])
@login_required
def api_test_fyers_connection():
    """Test FYERS broker connection."""
    try:
        fyers_service = get_fyers_service()
        result = fyers_service.test_connection(current_user.id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error testing FYERS connection for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/config', methods=['POST'])
@login_required
def api_save_fyers_config():
    """Save FYERS broker configuration."""
    try:
        data = request.get_json()
        fyers_service = get_fyers_service()
        
        config_data = {
            'client_id': data.get('client_id'),
            'api_secret': data.get('secret_key'),
            'redirect_url': data.get('redirect_uri')
        }
        
        saved_config = fyers_service.save_broker_config(config_data, current_user.id)
        
        # Generate auth URL if credentials are provided
        auth_url = None
        if config_data['client_id'] and config_data['api_secret']:
            try:
                auth_url = fyers_service.generate_auth_url(current_user.id)
            except Exception as e:
                logger.warning(f"Could not generate auth URL: {str(e)}")
        
        return jsonify({
            'success': True, 
            'message': 'Configuration saved successfully',
            'auth_url': auth_url
        })
        
    except Exception as e:
        logger.error(f"Error saving FYERS config for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/refresh-token', methods=['POST'])
@login_required
def api_refresh_fyers_token():
    """Refresh FYERS access token using v3 API (no browser needed)."""
    try:
        from src.services.brokers.fyers_token_refresh import FyersTokenRefreshService

        fyers_service = get_fyers_service()
        config = fyers_service.get_broker_config(current_user.id)

        if not config or not config.get('refresh_token'):
            # No refresh token - fall back to generating auth URL for manual login
            auth_url = fyers_service.generate_auth_url(current_user.id)
            return jsonify({
                'success': False,
                'message': 'No refresh token stored. Please complete OAuth login first.',
                'auth_url': auth_url
            })

        refresh_service = FyersTokenRefreshService()
        result = refresh_service.refresh_fyers_token(current_user.id, config['refresh_token'])

        if result:
            return jsonify({
                'success': True,
                'message': 'Token refreshed successfully via API',
                'refreshed_at': result.get('refreshed_at')
            })
        else:
            # API refresh failed - fall back to auth URL
            auth_url = fyers_service.generate_auth_url(current_user.id)
            return jsonify({
                'success': False,
                'message': 'API refresh failed. Refresh token may be expired. Please re-authenticate.',
                'auth_url': auth_url
            })

    except Exception as e:
        logger.error(f"Error refreshing FYERS token for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/oauth/callback', methods=['GET'])
def fyers_oauth_callback():
    """FYERS OAuth2 callback handler - serves the callback HTML page."""
    try:
        # Get the directory of the current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(current_dir, '../../static')
        return send_from_directory(static_dir, 'fyers_callback.html')
    except Exception as e:
        logger.error(f"Error serving FYERS OAuth callback page: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': 'Callback page not found'}), 404

@fyers_bp.route('/api/oauth/complete', methods=['POST'])
def api_fyers_oauth_complete():
    """Complete FYERS OAuth2 flow by exchanging auth code for access token."""
    try:
        data = request.get_json()
        auth_code = data.get('auth_code')
        state = data.get('state')
        
        if not auth_code:
            return jsonify({'success': False, 'error': 'Authorization code not provided'}), 400
        
        # Extract user_id from state (default to current user if available)
        if state and state.isdigit():
            user_id = int(state)
        elif current_user and hasattr(current_user, 'id'):
            user_id = current_user.id
        else:
            user_id = 1  # Default user
        
        logger.info(f"Completing OAuth flow for user {user_id} with auth_code: {auth_code[:10]}...")
        
        fyers_service = get_fyers_service()
        result = fyers_service.exchange_auth_code(user_id, auth_code)
        
        if result.get('success'):
            logger.info(f"OAuth flow completed successfully for user {user_id}")
            # Test the connection to update status
            try:
                fyers_service.test_connection(user_id)
            except Exception as test_error:
                logger.warning(f"Could not test connection after OAuth: {str(test_error)}")
            
            return jsonify({'success': True, 'message': 'Authorization successful'})
        else:
            error_msg = result.get('error', 'Authorization failed')
            logger.error(f"OAuth flow failed for user {user_id}: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
            
    except Exception as e:
        logger.error(f"Error in FYERS OAuth complete: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/funds', methods=['GET'])
@login_required
def api_get_fyers_funds():
    """Get FYERS user funds."""
    try:
        fyers_service = get_fyers_service()
        funds = fyers_service.funds(current_user.id)
        return jsonify({'success': True, 'data': funds})
        
    except Exception as e:
        logger.error(f"Error getting FYERS funds for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/holdings', methods=['GET'])
@login_required
def api_get_fyers_holdings():
    """Get FYERS user holdings."""
    try:
        fyers_service = get_fyers_service()
        holdings = fyers_service.holdings(current_user.id)
        return jsonify({'success': True, 'data': holdings})
        
    except Exception as e:
        logger.error(f"Error getting FYERS holdings for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/positions', methods=['GET'])
@login_required
def api_get_fyers_positions():
    """Get FYERS user positions."""
    try:
        fyers_service = get_fyers_service()
        positions = fyers_service.positions(current_user.id)
        return jsonify({'success': True, 'data': positions})
        
    except Exception as e:
        logger.error(f"Error getting FYERS positions for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/orders', methods=['GET'])
@login_required
def api_get_fyers_orders():
    """Get FYERS user orders."""
    try:
        fyers_service = get_fyers_service()
        orders = fyers_service.orderbook(current_user.id)
        return jsonify({'success': True, 'data': orders})
        
    except Exception as e:
        logger.error(f"Error getting FYERS orders for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/trades', methods=['GET'])
@login_required
def api_get_fyers_trades():
    """Get FYERS user trades."""
    try:
        fyers_service = get_fyers_service()
        trades = fyers_service.tradebook(current_user.id)
        return jsonify({'success': True, 'data': trades})
        
    except Exception as e:
        logger.error(f"Error getting FYERS trades for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/quotes', methods=['GET'])
@login_required
def api_get_fyers_quotes():
    """Get FYERS market quotes."""
    try:
        symbols = request.args.get('symbols', '')
        if not symbols:
            return jsonify({'success': False, 'error': 'Symbols parameter required'}), 400
            
        fyers_service = get_fyers_service()
        quotes = fyers_service.quotes(current_user.id, symbols)
        return jsonify({'success': True, 'data': quotes})
        
    except Exception as e:
        logger.error(f"Error getting FYERS quotes for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/profile', methods=['GET'])
@login_required
def api_get_fyers_profile():
    """Get FYERS user profile."""
    try:
        fyers_service = get_fyers_service()
        profile = fyers_service.login(current_user.id)
        return jsonify({'success': True, 'data': profile})
        
    except Exception as e:
        logger.error(f"Error getting FYERS profile for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# Config endpoint removed - using official fyers_apiv3 library

@fyers_bp.route('/api/token/status', methods=['GET'])
@login_required
def api_get_token_status():
    """Get FYERS token status and information."""
    try:
        fyers_service = get_fyers_service()
        token_status = fyers_service.get_token_status(current_user.id)
        return jsonify({'success': True, 'data': token_status})
        
    except Exception as e:
        logger.error(f"Error getting FYERS token status for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/token/auto-refresh/start', methods=['POST'])
@login_required
def api_start_auto_refresh():
    """Start automatic token refresh for the user."""
    try:
        data = request.get_json() or {}
        check_interval = data.get('check_interval_minutes', 30)
        
        fyers_service = get_fyers_service()
        fyers_service.start_auto_refresh(current_user.id, check_interval)
        
        return jsonify({
            'success': True, 
            'message': f'Started auto-refresh with {check_interval} minute intervals'
        })
        
    except Exception as e:
        logger.error(f"Error starting auto-refresh for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/token/auto-refresh/stop', methods=['POST'])
@login_required
def api_stop_auto_refresh():
    """Stop automatic token refresh for the user."""
    try:
        fyers_service = get_fyers_service()
        fyers_service.stop_auto_refresh(current_user.id)
        
        return jsonify({
            'success': True, 
            'message': 'Stopped auto-refresh'
        })
        
    except Exception as e:
        logger.error(f"Error stopping auto-refresh for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/token/cache/invalidate', methods=['POST'])
@login_required
def api_invalidate_token_cache():
    """Invalidate cached token data for the user."""
    try:
        fyers_service = get_fyers_service()
        fyers_service.invalidate_token_cache(current_user.id)
        
        return jsonify({
            'success': True, 
            'message': 'Token cache invalidated'
        })
        
    except Exception as e:
        logger.error(f"Error invalidating token cache for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@fyers_bp.route('/api/stats/detailed', methods=['GET'])
@login_required
def api_get_detailed_stats():
    """Get detailed broker statistics with actual API calls."""
    try:
        fyers_service = get_fyers_service()
        stats = fyers_service.get_detailed_broker_stats(current_user.id)
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        logger.error(f"Error getting detailed FYERS stats for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
