"""
Flask Web Application for the Automated Trading System with Swagger Documentation
"""
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
import uuid
from datetime import datetime
try:
    # Try relative imports first (for normal usage)
    from ..models.database import get_database_manager
    from ..models.models import Log, Order, Trade, Position, User, Strategy, SuggestedStock, Configuration, BrokerConfiguration
    from ..integrations.db_charts import DatabaseCharts
    from ..integrations.multi_user_trading_engine import get_trading_engine
    from ..services.core.user_service import get_user_service
    from ..services.core.broker_service import get_broker_service
    from ..services.core.dashboard_service import get_dashboard_service
    from ..services.portfolio.portfolio_service import get_portfolio_service
    from ..utils.api_logger import APILogger, log_flask_route
except ImportError:
    # Fall back to absolute imports (for testing)
    from models.database import get_database_manager
    from models.models import Log, Order, Trade, Position, User, Strategy, SuggestedStock, Configuration, BrokerConfiguration
    from integrations.db_charts import DatabaseCharts
    from integrations.multi_user_trading_engine import get_trading_engine
    from services.core.user_service import get_user_service
    from services.core.broker_service import get_broker_service
    from services.core.dashboard_service import get_dashboard_service
    from services.portfolio.portfolio_service import get_portfolio_service
    from utils.api_logger import APILogger, log_flask_route
from datetime import datetime
import secrets
import sys
import os

# Configure logging
from ..config.logging_config import setup_logging
setup_logging()


def create_app():
    """Create Flask application."""
    app = Flask(__name__)
    
    # SECRET_KEY resolution — MUST be stable across restarts/deploys or
    # every signed session + remember-me cookie is invalidated and users
    # are force-logged-out on each deploy. Resolution order:
    #   1. SECRET_KEY env var (preferred — set in .env on the host)
    #   2. Persisted file on a mounted volume (survives image rebuilds
    #      because /app/logs is bind-mounted to the host, not baked in)
    #   3. Generate once + persist to that file (self-healing)
    def _resolve_secret_key() -> str:
        env_key = os.environ.get('SECRET_KEY')
        if env_key:
            return env_key
        # /app/logs is bind-mounted (see docker-compose) so a key written
        # here outlives `docker compose build && up -d`.
        key_path = os.path.join(os.path.dirname(__file__), '..', '..',
                                'logs', '.flask_secret_key')
        key_path = os.path.abspath(key_path)
        try:
            if os.path.exists(key_path):
                with open(key_path) as f:
                    k = f.read().strip()
                if k:
                    return k
            k = secrets.token_hex(32)
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, 'w') as f:
                f.write(k)
            os.chmod(key_path, 0o600)
            print(f"SECRET_KEY generated + persisted to {key_path}")
            return k
        except Exception as e:
            print(f"WARNING: could not persist SECRET_KEY ({e}) — "
                  f"sessions will reset on restart")
            return secrets.token_hex(32)

    app.secret_key = _resolve_secret_key()

    # Session + remember-me cookies long-lived so a deploy doesn't log
    # users out. 30-day rolling window.
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    # Secure cookies only when served over HTTPS (prod). Allow override
    # for local http dev via SECURE_COOKIES=false.
    _secure = os.environ.get('SECURE_COOKIES', 'true').lower() == 'true'
    app.config['REMEMBER_COOKIE_SECURE'] = _secure
    app.config['SESSION_COOKIE_SECURE'] = _secure
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Force template auto-reload so Jinja re-reads files on each request
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Disable browser cache on HTML responses so template/JS changes deploy
    # immediately without users needing to hard-refresh. Static assets
    # (.js/.css/.png) keep their default cache headers.
    @app.after_request
    def add_no_cache_for_html(response):
        ct = response.headers.get('Content-Type', '')
        if ct.startswith('text/html'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # Request/response logging middleware removed for clean console output
    print("🔇 Console logging optimized - Only essential logs will be shown")
    
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.unauthorized_handler
    def handle_unauthorized():
        # Return JSON for API requests instead of redirecting to HTML
        try:
            path = request.path or ''
            accepts_json = 'application/json' in (request.headers.get('Accept') or '')
            is_api_request = path.startswith('/api') or '/api/' in path or path.startswith('/brokers/') and '/api/' in path
            if is_api_request or accepts_json:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        except Exception:
            pass
        return redirect(url_for('login'))
    
    # Initialize Flask-Bcrypt
    bcrypt = Bcrypt(app)
    
    # Initialize database
    db_manager = get_database_manager()
    
    # Create database tables if they don't exist
    try:
        app.logger.info("🗄️ Creating database tables...")
        db_manager.create_tables()
        app.logger.info("✅ Database tables created successfully!")
    except Exception as e:
        app.logger.warning(f"⚠️ Could not create database tables: {e}")

    # Audit: record app boot
    try:
        from src.services.audit_service import write_system_event
        write_system_event("BOOT", "trading_system",
                           metadata={"pid": os.getpid()})
    except Exception as _e:
        app.logger.debug(f"audit BOOT failed: {_e}")

    # Seed per-model ledger rows (idempotent)
    try:
        from ..services.trading.model_ledger_service import ensure_models_seeded
        ensure_models_seeded()
        app.logger.info("✅ Model ledgers seeded")
    except Exception as e:
        app.logger.warning(f"⚠️ Could not seed model ledgers: {e}")

    # Initialize services
    user_service = get_user_service(db_manager, bcrypt)
    broker_service = get_broker_service()
    dashboard_service = get_dashboard_service()
    portfolio_service = get_portfolio_service()
    
    # Initialize new services
    from ..services.utils.cache_service import get_cache_service
    from ..services.utils.token_manager_service import get_token_manager

    cache_service = get_cache_service()
    token_manager = get_token_manager()

    # IBKR uses TWS/Gateway-managed auth — no in-app token refresh callback needed.

    # Token refresh is owned SOLELY by data_scheduler cron at 03:30 IST.
    # In-process daemon removed to keep a single source of truth — see
    # commit ec231858 reverted. Manual CLI + /api endpoint remain as
    # escape hatches but are not auto-triggered.

    # Technical indicators system - no ML models needed
    app.logger.info("📊 Using technical indicator system (RS Rating + Wave Indicators)")

    # Run pipeline saga in background thread (only if data is stale)
    try:
        import threading
        def run_complete_stock_initialization():
            try:
                # Check if startup pipeline is disabled via env var
                if os.environ.get('SKIP_STARTUP_PIPELINE', '').lower() in ('true', '1', 'yes'):
                    app.logger.info("⏭️ Startup pipeline SKIPPED (SKIP_STARTUP_PIPELINE=true)")
                    return

                # Check data freshness - only run if data is more than 2 days old
                from sqlalchemy import text
                from datetime import timedelta
                with db_manager.get_session() as session:
                    result = session.execute(text(
                        "SELECT MAX(date) as latest_date FROM historical_data"
                    )).fetchone()
                    if result and result.latest_date:
                        from datetime import date
                        days_old = (date.today() - result.latest_date).days
                        if days_old <= 2:
                            app.logger.info(f"⏭️ Startup pipeline SKIPPED - data is fresh ({days_old} day(s) old)")
                            return
                        app.logger.info(f"📊 Data is {days_old} days old - running pipeline to refresh")

                app.logger.info("🚀 Running COMPLETE system initialization...")
                app.logger.info("📊 This includes: Symbol Master → Stocks → Historical Data → Technical Indicators → Volatility")

                # Use the new pipeline saga instead of old service
                from src.services.data.pipeline_saga import get_pipeline_saga
                pipeline_saga = get_pipeline_saga()
                results = pipeline_saga.run_pipeline()

                if results.get('success'):
                    app.logger.info("✅ Complete system initialization succeeded!")
                    app.logger.info(f"⏱️ Total duration: {results.get('total_duration', 0):.1f}s")
                    app.logger.info(f"📊 Steps completed: {len(results.get('steps_completed', []))}")
                    app.logger.info(f"📊 Total records processed: {results.get('total_records_processed', 0)}")

                    # Log individual step results with proper counts
                    from src.services.data.pipeline_saga import get_pipeline_saga
                    saga = get_pipeline_saga()
                    status = saga.get_pipeline_status()

                    # ML training removed - now using technical indicators instead
                    # Technical indicators are calculated by scheduler.py at 10:00 PM
                    app.logger.info("✅ Pipeline complete. Technical indicators will be calculated by scheduler.")
                    
                    for step, info in status.items():
                        records = info.get('records_processed', 0)
                        if step == 'COMPREHENSIVE_METRICS':
                            app.logger.info(f"📈 Comprehensive Metrics: {records} stocks")
                        elif step == 'HISTORICAL_DATA':
                            app.logger.info(f"📈 Historical: {records} records")
                        elif step == 'TECHNICAL_INDICATORS':
                            app.logger.info(f"📊 Indicators: {records} records")
                        elif step == 'STOCKS':
                            app.logger.info(f"📊 Stocks: {records} synced")
                        elif step == 'SYMBOL_MASTER':
                            app.logger.info(f"📊 Symbol Master: {records} records")
                        elif step == 'PIPELINE_VALIDATION':
                            # Show validation results
                            validation_results = info.get('validation_results', {})
                            app.logger.info(f"📊 Validation: {validation_results.get('symbol_master_count', 0)} symbols, {validation_results.get('stocks_count', 0)} stocks, {validation_results.get('historical_data_count', 0)} historical, {validation_results.get('technical_indicators_count', 0)} indicators, {validation_results.get('volatility_calculated_count', 0)} volatility")
                        else:
                            app.logger.info(f"📊 {step}: {records} records")

                else:
                    app.logger.error(f"❌ Complete system initialization failed: {results.get('error', 'Unknown error')}")

            except Exception as e:
                app.logger.error(f"❌ Complete system initialization failed: {e}")
                import traceback
                app.logger.error(f"Stack trace: {traceback.format_exc()}")

        # Start initialization in background thread
        startup_thread = threading.Thread(target=run_complete_stock_initialization, daemon=True)
        startup_thread.start()
        app.logger.info("🚀 Complete stock system initialization launched in background")

    except Exception as e:
        app.logger.warning(f"Could not initialize stock system: {e}")

    # Initialize charting
    charts = DatabaseCharts(db_manager)
    
    # Initialize API with all namespaces
    # from .api import create_api
    # api = create_api(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login."""
        with db_manager.get_session() as session:
            user = session.query(User).get(int(user_id))
            if user:
                # Detach the user from the session to avoid issues
                session.expunge(user)
            return user
    
    # Authentication routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login page."""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            remember = bool(request.form.get('remember'))
            
            if not username or not password:
                flash('Please fill in all fields.', 'error')
                return render_template('login.html')

            try:
                user = user_service.login_user(username, password)
                # Mark session permanent so it honors the 30-day lifetime
                # (otherwise it's a session cookie that dies on browser close).
                from flask import session as _flask_session
                _flask_session.permanent = True
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('dashboard'))
            except ValueError as e:
                flash(str(e), 'error')
        
        return render_template('login.html')
    
    
    @app.route('/logout')
    @login_required
    def logout():
        """Logout user."""
        logout_user()
        flash('You have been logged out successfully.', 'info')
        return redirect(url_for('login'))
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """Register new user."""
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            if not all([username, email, password, confirm_password]):
                flash('Please fill in all fields.', 'error')
                return render_template('login.html')
            
            if password != confirm_password:
                flash('Passwords do not match.', 'error')
                return render_template('login.html')
            
            if len(password) < 6:
                flash('Password must be at least 6 characters long.', 'error')
                return render_template('login.html')

            try:
                user_service.register_user(username, email, password)
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('login'))
            except ValueError as e:
                flash(str(e), 'error')
                return render_template('login.html')
        
        return render_template('login.html')
    
    @app.route('/health')
    def health():
        """Health check endpoint."""
        return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


    
    # Primary UI routes (v2 templates)
    @app.route('/')
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """Dashboard page."""
        return render_template('v2/dashboard.html')

    # PWA: serve manifest + service worker from root so SW can claim '/' scope.
    @app.route('/manifest.json')
    def pwa_manifest():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory('static', 'manifest.json',
                                                  mimetype='application/manifest+json'))
        # Manifest must bypass HTTP cache so icon updates show up
        # without forcing user to clear browser data.
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    @app.route('/sw.js')
    def pwa_service_worker():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory('static', 'sw.js',
                                                 mimetype='application/javascript'))
        # SW updates must bypass cache so version bumps are picked up.
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    @app.route('/picks')
    @login_required
    def picks():
        """Today's Picks page."""
        return render_template('v2/picks.html')

    @app.route('/picks/<model_key>/signals')
    @login_required
    def model_signals(model_key):
        """Per-model signal history (scheduled emissions only)."""
        return render_template('v2/model_signals.html', model_key=model_key)

    @app.route('/portfolio')
    @login_required
    def portfolio():
        """Portfolio page."""
        return render_template('v2/portfolio.html')

    @app.route('/history')
    @login_required
    def history():
        """Trade History page."""
        return render_template('v2/history.html')

    @app.route('/settings')
    @login_required
    def settings():
        """Settings page."""
        return render_template('v2/settings.html')

    # Keep /v2/ paths as aliases for bookmarks
    @app.route('/v2/')
    @login_required
    def v2_dashboard():
        return redirect(url_for('dashboard'))

    @app.route('/v2/picks')
    @login_required
    def v2_picks():
        return redirect(url_for('picks'))

    @app.route('/v2/portfolio')
    @login_required
    def v2_portfolio():
        return redirect(url_for('portfolio'))

    @app.route('/v2/history')
    @login_required
    def v2_history():
        return redirect(url_for('history'))

    @app.route('/v2/settings')
    @login_required
    def v2_settings():
        return redirect(url_for('settings'))

    # Admin routes
    @app.route('/admin/users')
    @login_required
    def admin_users():
        """Admin page for managing users."""
        if not current_user.is_admin:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('dashboard'))
        return render_template('admin/users.html')
    
    # API Routes for User Management
    @app.route('/api/admin/users', methods=['GET'])
    @login_required
    def api_get_users():
        """Get all users for admin management."""
        if not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        try:
            users_data = user_service.get_all_users()
            return jsonify({'users': users_data})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/admin/users', methods=['POST'])
    @login_required
    def api_create_user():
        """Create a new user."""
        if not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        try:
            data = request.get_json()
            new_user = user_service.create_user(data)
            return jsonify({
                'message': 'User created successfully',
                'user': new_user
            }), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
    @login_required
    def api_update_user(user_id):
        """Update a user."""
        if not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        try:
            data = request.get_json()
            updated_user = user_service.update_user(user_id, data)
            return jsonify({
                'message': 'User updated successfully',
                'user': updated_user
            })
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
    @login_required
    def api_delete_user(user_id):
        """Delete a user."""
        if not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        try:
            user_service.delete_user(user_id, current_user.id)
            return jsonify({'message': 'User deleted successfully'})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    # Broker API Routes
    @app.route('/api/brokers/fyers', methods=['GET'])
    @login_required
    def api_get_fyers_info():
        """Get FYERS broker information."""
        try:
            app.logger.info(f"Fetching FYERS broker info for user {current_user.id}")
            config = broker_service.get_broker_config('fyers', current_user.id)
            
            if not config:
                app.logger.info("No FYERS configuration found for user")
                return jsonify({
                    'success': True, 'client_id': '', 'access_token': False, 'connected': False, 'last_updated': '-',
                    'stats': {'total_orders': 0, 'successful_orders': 0, 'pending_orders': 0, 'failed_orders': 0, 'last_order_time': '-', 'api_response_time': '-'}
                })

            stats = broker_service.get_broker_stats('fyers', current_user.id)
            config['access_token'] = bool(config.get('access_token'))
            
            return jsonify({'success': True, **config, 'stats': stats})
        except Exception as e:
            app.logger.error(f"Error getting FYERS broker info for user {current_user.id}: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/test', methods=['POST'])
    @login_required
    def api_test_fyers_connection():
        """Test FYERS broker connection."""
        try:
            app.logger.info(f"Testing FYERS broker connection for user {current_user.id}")
            result = broker_service.test_fyers_connection(current_user.id)
            return jsonify(result)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error testing FYERS connection for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/brokers/fyers/config', methods=['POST'])
    @login_required
    def api_save_fyers_config():
        """Save FYERS broker configuration."""
        try:
            app.logger.info(f"Saving FYERS configuration for user {current_user.id}")
            data = request.get_json()
            if not data.get('client_id'):
                return jsonify({'success': False, 'error': 'Client ID is required'}), 400

            config = broker_service.save_broker_config('fyers', data, current_user.id)
            
            response_data = {'success': True, 'message': 'FYERS configuration saved successfully', 'config': config}

            if data.get('secret_key'):
                try:
                    auth_url = broker_service.generate_fyers_auth_url(current_user.id)
                    response_data['auth_url'] = auth_url
                    response_data['message'] = 'FYERS configuration saved successfully. OAuth2 authorization URL generated automatically.'
                except Exception as e:
                    app.logger.error(f"Error auto-generating OAuth2 auth URL for user {current_user.id}: {str(e)}")

            return jsonify(response_data)
        except Exception as e:
            app.logger.error(f"Error saving FYERS configuration for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/config', methods=['PUT'])
    @login_required
    def api_update_fyers_config():
        """Update FYERS broker configuration."""
        try:
            app.logger.info(f"Updating FYERS configuration for user {current_user.id}")
            data = request.get_json()
            config = broker_service.save_broker_config('fyers', data, current_user.id)
            return jsonify({'success': True, 'message': 'FYERS configuration updated successfully', 'config': config})
        except Exception as e:
            app.logger.error(f"Error updating FYERS configuration for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/brokers/fyers/refresh-token', methods=['POST'])
    @login_required
    def api_refresh_fyers_token():
        """Refresh FYERS access token."""
        try:
            app.logger.info(f"Refreshing FYERS token for user {current_user.id}")
            auth_url = broker_service.generate_fyers_auth_url(current_user.id)
            return jsonify({
                'success': True,
                'message': 'Re-authentication required. Please complete the authorization process.',
                'auth_url': auth_url
            })
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error refreshing FYERS token for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/brokers/fyers/auth-url', methods=['POST'])
    @login_required
    def api_generate_fyers_auth_url():
        """Generate FYERS OAuth2 authorization URL using database configuration."""
        try:
            app.logger.info(f"Generating FYERS auth URL for user {current_user.id}")
            auth_url = broker_service.generate_fyers_auth_url(current_user.id)
            return jsonify({
                'success': True,
                'auth_url': auth_url,
                'message': 'Authorization URL generated successfully.'
            })
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error generating FYERS auth URL for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/exchange-token', methods=['POST'])
    @login_required
    def api_exchange_fyers_auth_code():
        """Exchange FYERS authorization code for access token."""
        try:
            app.logger.info(f"Exchanging FYERS auth code for user {current_user.id}")
            data = request.get_json()
            auth_code = data.get('auth_code')
            if not auth_code:
                return jsonify({'success': False, 'error': 'Auth Code is required'}), 400
            
            result = broker_service.exchange_fyers_auth_code(current_user.id, auth_code)
            
            return jsonify({
                'success': True,
                'message': 'Access token obtained and saved successfully',
                'access_token': result['access_token'][:20] + '...'
            })
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error exchanging FYERS auth code for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/funds', methods=['GET'])
    @login_required
    def api_get_fyers_funds():
        """Get FYERS user funds."""
        try:
            app.logger.info(f"Fetching FYERS funds for user {current_user.id}")
            result = broker_service.get_fyers_funds(current_user.id)
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS funds for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/holdings', methods=['GET'])
    @login_required
    def api_get_fyers_holdings():
        """Get FYERS user holdings."""
        try:
            app.logger.info(f"Fetching FYERS holdings for user {current_user.id}")
            result = broker_service.get_fyers_holdings(current_user.id)
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS holdings for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/positions', methods=['GET'])
    @login_required
    def api_get_fyers_positions():
        """Get FYERS user positions."""
        try:
            app.logger.info(f"Fetching FYERS positions for user {current_user.id}")
            result = broker_service.get_fyers_positions(current_user.id)
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS positions for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/orderbook', methods=['GET'])
    @login_required
    def api_get_fyers_orderbook():
        """Get FYERS user orderbook."""
        try:
            app.logger.info(f"Fetching FYERS orderbook for user {current_user.id}")
            result = broker_service.get_fyers_orderbook(current_user.id)
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS orderbook for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/tradebook', methods=['GET'])
    @login_required
    def api_get_fyers_tradebook():
        """Get FYERS user tradebook."""
        try:
            app.logger.info(f"Fetching FYERS tradebook for user {current_user.id}")
            result = broker_service.get_fyers_tradebook(current_user.id)
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS tradebook for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/quotes', methods=['GET'])
    @login_required
    @log_flask_route("get_fyers_quotes")
    def api_get_fyers_quotes():
        """Get FYERS market quotes."""
        try:
            symbols = request.args.get('symbols', '')
            app.logger.info(f"Fetching FYERS quotes for symbols: {symbols} for user {current_user.id}")
            
            # Log API call to broker service
            APILogger.log_request(
                service_name="BrokerService",
                method_name="get_fyers_quotes",
                request_data={'symbols': symbols},
                user_id=current_user.id
            )
            
            result = broker_service.get_fyers_quotes(current_user.id, symbols)
            
            # Log response from broker service
            APILogger.log_response(
                service_name="BrokerService",
                method_name="get_fyers_quotes",
                response_data=result,
                user_id=current_user.id
            )
            
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            APILogger.log_error(
                service_name="FlaskAPI",
                method_name="get_fyers_quotes",
                error=e,
                user_id=current_user.id if current_user else None
            )
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS quotes for user {current_user.id}: {str(e)}")
            APILogger.log_error(
                service_name="FlaskAPI",
                method_name="get_fyers_quotes",
                error=e,
                user_id=current_user.id if current_user else None
            )
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/fyers/history', methods=['GET'])
    @login_required
    def api_get_fyers_history():
        """Get FYERS historical data."""
        try:
            symbol = request.args.get('symbol', '')
            resolution = request.args.get('resolution', 'D')
            range_from = request.args.get('range_from')
            range_to = request.args.get('range_to')
            app.logger.info(f"Fetching FYERS historical data for symbol: {symbol} for user {current_user.id}")
            result = broker_service.get_fyers_history(current_user.id, symbol, resolution, range_from, range_to)
            if 'error' in result:
                return jsonify({'success': False, 'error': result['error']}), 400
            return jsonify({'success': True, 'data': result})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error getting FYERS historical data for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500
    
    # Portfolio API Routes (Legacy - keeping for backward compatibility)
    @app.route('/api/portfolio/holdings', methods=['GET'])
    @login_required
    def api_get_portfolio_holdings_legacy():
        """Get portfolio holdings using FYERS API (Legacy endpoint)."""
        try:
            app.logger.info(f"Fetching portfolio holdings for user {current_user.id}")
            result = portfolio_service.get_portfolio_holdings(current_user.id)
            return jsonify(result)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error fetching portfolio holdings for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/portfolio/positions', methods=['GET'])
    @login_required
    def api_get_portfolio_positions():
        """Get portfolio positions using FYERS API."""
        try:
            app.logger.info(f"Fetching portfolio positions for user {current_user.id}")
            result = portfolio_service.get_portfolio_positions(current_user.id)
            return jsonify(result)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error fetching portfolio positions for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    # Orders API Routes
    @app.route('/api/orders/history', methods=['GET'])
    @login_required
    def api_get_orders_history():
        """Get orders history using FYERS API."""
        try:
            app.logger.info(f"Fetching orders history for user {current_user.id}")
            orderbook_data = broker_service.get_fyers_orderbook(current_user.id)

            if orderbook_data.get('success') and orderbook_data.get('data'):
                orders = orderbook_data['data'].get('orderBook', [])
                processed_orders = [
                    {
                        'id': o.get('id', ''), 'symbol': o.get('symbol', ''), 'side': o.get('side', ''),
                        'type': o.get('type', ''), 'quantity': o.get('qty', 0), 'price': o.get('limitPrice', 0),
                        'status': o.get('status', ''), 'order_time': o.get('orderDateTime', ''),
                        'filled_quantity': o.get('filledQty', 0), 'remaining_quantity': o.get('remainingQty', 0),
                        'product': o.get('product', '')
                    } for o in orders
                ]
                return jsonify({'success': True, 'data': processed_orders, 'last_updated': datetime.now().isoformat()})
            else:
                return jsonify({'success': False, 'error': 'Failed to fetch orders data from FYERS'}), 400
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error fetching orders history for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/orders/trades', methods=['GET'])
    @login_required
    def api_get_trades_history():
        """Get trades history using FYERS API."""
        try:
            app.logger.info(f"Fetching trades history for user {current_user.id}")
            tradebook_data = broker_service.get_fyers_tradebook(current_user.id)

            if tradebook_data.get('success') and tradebook_data.get('data'):
                trades = tradebook_data['data'].get('tradeBook', [])
                processed_trades = [
                    {
                        'id': t.get('id', ''), 'symbol': t.get('symbol', ''), 'side': t.get('side', ''),
                        'quantity': t.get('qty', 0), 'price': t.get('tradedPrice', 0),
                        'trade_time': t.get('tradeDateTime', ''), 'order_id': t.get('orderNumber', ''),
                        'product': t.get('product', ''), 'pnl': t.get('pnl', 0)
                    } for t in trades
                ]
                return jsonify({'success': True, 'data': processed_trades, 'last_updated': datetime.now().isoformat()})
            else:
                return jsonify({'success': False, 'error': 'Failed to fetch trades data from FYERS'}), 400
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error fetching trades history for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    # Market Data API Routes
    @app.route('/api/market/quotes', methods=['GET'])
    @login_required
    def api_get_market_quotes():
        """Get market quotes using FYERS API."""
        try:
            app.logger.info(f"Fetching market quotes for user {current_user.id}")
            symbols = request.args.get('symbols', 'NSE:NIFTY50-INDEX,NSE:SENSEX-INDEX,NSE:NIFTYBANK-INDEX,NSE:NIFTYIT-INDEX')
            quotes_data = broker_service.get_fyers_quotes(current_user.id, symbols)
            
            if quotes_data.get('success') and quotes_data.get('data'):
                # Processing can be moved to a service if it becomes more complex
                processed_quotes = []
                for symbol, quote in quotes_data['data'].items():
                    if quote.get('v'):
                        processed_quotes.append({
                            'symbol': symbol,
                            'price': quote['v'].get('lp', 0),
                            'change': quote['v'].get('ch', 0),
                            'change_percent': quote['v'].get('chp', 0),
                            'volume': quote['v'].get('volume', 0),
                            'high': quote['v'].get('h', 0),
                            'low': quote['v'].get('l', 0),
                            'open': quote['v'].get('open_price', 0),
                            'close': quote['v'].get('prev_close_price', 0)
                        })
                return jsonify({'success': True, 'data': processed_quotes, 'last_updated': datetime.now().isoformat()})
            else:
                return jsonify({'success': False, 'error': 'Failed to fetch quotes data from FYERS'}), 400
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error fetching market quotes for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/market/historical', methods=['GET'])
    @login_required
    def api_get_historical_data():
        """Get historical data using FYERS API."""
        try:
            app.logger.info(f"Fetching historical data for user {current_user.id}")
            symbol = request.args.get('symbol', 'NSE:NIFTY50-INDEX')
            resolution = request.args.get('resolution', 'D')
            range_from = request.args.get('from')
            range_to = request.args.get('to')

            historical_data = broker_service.get_fyers_history(current_user.id, symbol, resolution, range_from, range_to)

            if historical_data.get('success') and historical_data.get('data'):
                # This processing can also be moved to a service
                processed_data = []
                for candle in historical_data['data'].get('candles', []):
                    processed_data.append({
                        'timestamp': candle[0], 'open': candle[1], 'high': candle[2],
                        'low': candle[3], 'close': candle[4], 'volume': candle[5] if len(candle) > 5 else 0
                    })
                return jsonify({'success': True, 'data': processed_data, 'symbol': symbol, 'resolution': resolution, 'last_updated': datetime.now().isoformat()})
            else:
                return jsonify({'success': False, 'error': 'Failed to fetch historical data from FYERS'}), 400
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"Error fetching historical data for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/market/overview', methods=['GET'])
    @login_required
    def api_get_market_overview():
        """Get market overview for NIFTY indices using live API or cached database data."""
        user_id = current_user.id
        try:
            app.logger.info(f"Fetching market overview for user {user_id}")

            # NIFTY indices symbols mapping
            symbols_map = {
                'NIFTY 50': 'NSE:NIFTY50-INDEX',
                'BANK NIFTY': 'NSE:NIFTYBANK-INDEX',
                'MIDCAP 150': 'NSE:NIFTYMIDCAP150-INDEX',
                'SMALLCAP 250': 'NSE:NIFTYSMLCAP250-INDEX'
            }

            # Try to get live data from broker service first
            symbols = ','.join(symbols_map.values())
            quotes_data = broker_service.get_fyers_quotes(user_id, symbols)

            # Check if we got valid live data
            has_valid_data = False
            if quotes_data and isinstance(quotes_data, dict):
                if (quotes_data.get('success') == True or
                    quotes_data.get('s') == 'ok' or
                    quotes_data.get('status') == 'success' or
                    (quotes_data.get('data') and not quotes_data.get('error')) or
                    quotes_data.get('d')):
                    has_valid_data = True

            market = {}

            if has_valid_data:
                app.logger.info("Using live market data from API")
                # Support both SDK shapes: {'data': {...}} or {'d': [...]}
                payload = quotes_data.get('data') or quotes_data.get('d') or {}

                # Handle payload either as dict keyed by symbol or list under 'd'
                if isinstance(payload, dict):
                    for symbol, quote in payload.items():
                        for name, fy_symbol in symbols_map.items():
                            if symbol == fy_symbol:
                                v = quote.get('v', quote)
                                # Skip error payloads
                                if isinstance(v, dict) and (v.get('s') == 'error' or v.get('errmsg')):
                                    continue
                                lp = float(v.get('lp', 0))
                                pc = float(v.get('prev_close_price', v.get('pc', lp)))
                                chp = float(v.get('chp', ((lp - pc) / pc * 100) if pc > 0 else 0))
                                market[name] = {
                                    'current_price': round(lp, 2),
                                    'change_percent': round(chp, 2),
                                    'is_positive': chp >= 0
                                }
                elif isinstance(payload, list):
                    for item in payload:
                        symbol = item.get('symbol') or item.get('n')
                        for name, fy_symbol in symbols_map.items():
                            if symbol == fy_symbol:
                                v = item.get('v', item)
                                # Skip error payloads
                                if isinstance(v, dict) and (v.get('s') == 'error' or v.get('errmsg')):
                                    continue
                                lp = float(v.get('lp', 0))
                                pc = float(v.get('prev_close_price', v.get('pc', lp)))
                                chp = float(v.get('chp', ((lp - pc) / pc * 100) if pc > 0 else 0))
                                market[name] = {
                                    'current_price': round(lp, 2),
                                    'change_percent': round(chp, 2),
                                    'is_positive': chp >= 0
                                }

                if market:  # Only return if we got actual market data
                    return jsonify({
                        'success': True,
                        'data': market,
                        'last_updated': datetime.now().isoformat(),
                        'source': 'live_api'
                    })

            # If live API failed, try to get cached data from database
            app.logger.warning(f"Live API unavailable, attempting to retrieve cached market data")

            try:
                from sqlalchemy import text

                # Get the most recent market data from database for these indices
                with db_manager.get_session() as session:
                    # Try to get latest cached market overview data
                    symbol_list = list(symbols_map.values())
                    placeholders = ','.join([f"'{symbol}'" for symbol in symbol_list])

                    cache_result = session.execute(text(f"""
                        SELECT symbol, close, date
                        FROM historical_data
                        WHERE symbol IN ({placeholders})
                        AND date >= CURRENT_DATE - INTERVAL '7 days'
                        ORDER BY symbol, date DESC
                    """)).fetchall()

                    if cache_result:
                        app.logger.info(f"Found {len(cache_result)} cached market data records")

                        # Group by symbol and get latest for each
                        symbol_data = {}
                        for row in cache_result:
                            symbol, close_price, date = row
                            if symbol not in symbol_data:
                                symbol_data[symbol] = {'price': close_price, 'date': date}

                        # Convert to market format
                        for name, fy_symbol in symbols_map.items():
                            if fy_symbol in symbol_data:
                                market[name] = {
                                    'current_price': round(float(symbol_data[fy_symbol]['price']), 2),
                                    'change_percent': 0.0,  # Can't calculate without previous close
                                    'is_positive': True,
                                    'is_cached': True,
                                    'cache_date': symbol_data[fy_symbol]['date'].isoformat()
                                }

                        if market:
                            return jsonify({
                                'success': True,
                                'data': market,
                                'last_updated': datetime.now().isoformat(),
                                'source': 'database_cache',
                                'note': 'Live API unavailable, showing cached data'
                            })

            except Exception as db_error:
                app.logger.error(f"Error retrieving cached market data: {db_error}")

            # If both live API and database cache fail, return error
            error_msg = (quotes_data or {}).get('message', 'Market data unavailable')
            app.logger.error(f"Market overview completely unavailable: {error_msg}")

            return jsonify({
                'success': False,
                'error': 'Market data temporarily unavailable. Please check API authentication or try again later.',
                'data': {},
                'source': 'error'
            }), 503  # Service Unavailable

        except Exception as e:
            app.logger.error(f"Error in market overview: {e}")
            return jsonify({
                'success': False,
                'error': 'Internal server error while fetching market data',
                'data': {},
                'source': 'exception'
            }), 500

    # Settings API Routes
    @app.route('/api/settings', methods=['GET'])
    @login_required
    def api_get_settings():
        """Get user settings."""
        try:
            from ..services.utils.user_settings_service import get_user_settings_service
            user_settings_service = get_user_settings_service()
            settings = user_settings_service.get_user_settings(current_user.id)
            return jsonify({'success': True, 'settings': settings})
        except Exception as e:
            app.logger.error(f"Error getting settings for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/settings', methods=['POST'])
    @login_required
    def api_save_settings():
        """Save user settings."""
        try:
            data = request.get_json()
            from ..services.utils.user_settings_service import get_user_settings_service
            user_settings_service = get_user_settings_service()

            # Save settings to database
            saved_settings = user_settings_service.save_user_settings(current_user.id, data)

            app.logger.info(f"Settings saved for user {current_user.id}: {data}")
            return jsonify({'success': True, 'message': 'Settings saved successfully', 'settings': saved_settings})
        except Exception as e:
            app.logger.error(f"Error saving settings for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    # Broker Selection API
    @app.route('/api/brokers/current', methods=['GET'])
    @login_required
    def api_get_current_broker():
        """Get the currently selected broker."""
        try:
            from ..services.utils.user_settings_service import get_user_settings_service
            user_settings_service = get_user_settings_service()
            broker_provider = user_settings_service.get_broker_provider(current_user.id)
            return jsonify({'success': True, 'broker': broker_provider})
        except Exception as e:
            app.logger.error(f"Error getting current broker for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/api/brokers/current', methods=['POST'])
    @login_required
    def api_set_current_broker():
        """Set the currently selected broker."""
        try:
            data = request.get_json()
            broker = data.get('broker', 'fyers')
            from ..services.utils.user_settings_service import get_user_settings_service
            user_settings_service = get_user_settings_service()
            
            # Save broker provider to user settings
            success = user_settings_service.set_broker_provider(current_user.id, broker)
            
            if success:
                app.logger.info(f"Setting current broker to {broker} for user {current_user.id}")
                return jsonify({'success': True, 'message': f'Broker set to {broker}'})
            else:
                return jsonify({'success': False, 'error': 'Failed to save broker setting'}), 500
        except Exception as e:
            app.logger.error(f"Error setting current broker for user {current_user.id}: {str(e)}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

    # Broker-specific blueprints: IBKR uses TWS/Gateway (no OAuth web flow), so no
    # broker auth blueprint is registered here (Fyers blueprint removed).

    # Register admin routes for manual triggers
    try:
        from .admin_routes import admin_bp
        app.register_blueprint(admin_bp)
        app.logger.info("Admin routes registered successfully")
    except ImportError as e:
        app.logger.warning(f"Admin routes not available: {e}")
        app.logger.warning("Admin dashboard functionality will be disabled")

    # Register momentum rotation live-trading dashboard
    try:
        from .momrot_routes import momrot_bp
        app.register_blueprint(momrot_bp)
        app.logger.info("Momentum rotation routes registered successfully")
    except ImportError as e:
        app.logger.warning(f"Momentum rotation routes not available: {e}")


    # Register WebAuthn/Passkey authentication routes
    try:
        from .routes.auth_routes import auth_bp
        app.register_blueprint(auth_bp)
        app.logger.info("WebAuthn authentication routes registered successfully")
    except ImportError as e:
        app.logger.warning(f"WebAuthn routes not available: {e}")

    # On-demand backtest (single stock + date range)
    try:
        from .routes.backtest_routes import backtest_bp
        app.register_blueprint(backtest_bp)
        app.logger.info("Backtest routes registered successfully")
    except ImportError as e:
        app.logger.warning(f"Backtest routes not available: {e}")

    # Individual broker page routes
    @app.route('/brokers/fyers')
    @login_required
    def brokers_fyers():
        """FYERS broker page."""
        return render_template('brokers/fyers.html')



    # Add missing API endpoints that frontend expects
    @app.route('/api/portfolio', methods=['GET'])
    def api_get_portfolio():
        """Get portfolio data using portfolio sync service with real Fyers data."""
        try:
            # Get user_id - default to 1 for testing (same pattern as orders API)
            user_id = getattr(current_user, 'id', None) if current_user and current_user.is_authenticated else 1

            from src.services.data.portfolio_sync_service import get_portfolio_sync_service
            portfolio_sync_service = get_portfolio_sync_service()

            force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
            portfolio_data = portfolio_sync_service.get_portfolio_data(user_id, force_refresh=force_refresh)

            # Convert to format expected by frontend
            positions = portfolio_data.get('positions', [])
            holdings = portfolio_data.get('holdings', [])

            # Combine positions and holdings for the portfolio view
            combined_portfolio = []

            # Add positions
            for position in positions:
                combined_portfolio.append({
                    'symbol': position['symbol'],
                    'quantity': position['quantity'],
                    'avg_price': position['avg_price'],
                    'last_price': position['last_price'],
                    'pnl': position['pnl'],
                    'pnl_percentage': position['pnl_percentage'],
                    'current_value': position['current_value'],
                    'investment_value': position['investment_value'],
                    'type': 'position'
                })

            # Add holdings
            for holding in holdings:
                combined_portfolio.append({
                    'symbol': holding['symbol'],
                    'quantity': holding['quantity'],
                    'avg_price': holding['avg_price'],
                    'last_price': holding['last_price'],
                    'pnl': holding['pnl'],
                    'pnl_percentage': holding['pnl_percentage'],
                    'current_value': holding['market_value'],
                    'investment_value': holding['invested_value'],
                    'type': 'holding'
                })

            return jsonify(combined_portfolio)

        except Exception as e:
            app.logger.error(f"Error fetching portfolio with sync service: {e}", exc_info=True)
            return jsonify([]), 500

    @app.route('/api/orders', methods=['GET'])
    def api_get_orders_no_slash():
        """Get comprehensive orders data for Orders page using efficient caching."""
        try:
            # Get authenticated user or use default user_id = 1 for testing
            user_id = getattr(current_user, 'id', None) if current_user and current_user.is_authenticated else 1

            app.logger.info(f"Fetching orders data for user {user_id} with caching")

            # Use order sync service for efficient data retrieval
            from src.services.data.order_sync_service import get_order_sync_service
            order_sync_service = get_order_sync_service()

            # Check if force refresh is requested
            force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'

            # Get orders using sync service (handles caching automatically)
            orders = order_sync_service.get_user_orders(user_id, force_refresh=force_refresh)

            app.logger.info(f"Retrieved {len(orders)} orders for user {user_id}")
            return jsonify(orders)

        except Exception as e:
            app.logger.error(f"Error fetching orders with sync service: {e}", exc_info=True)
            return jsonify([]), 500

    @app.route('/api/orders/sync-broker', methods=['POST'])
    def api_sync_orders_from_broker():
        """Force sync orders from broker API for debugging."""
        try:
            user_id = getattr(current_user, 'id', None) if current_user and current_user.is_authenticated else 1

            app.logger.info(f"Manual broker sync requested for user {user_id}")

            from src.services.data.order_sync_service import get_order_sync_service
            order_sync_service = get_order_sync_service()

            # Force refresh from broker
            orders = order_sync_service.get_user_orders(user_id, force_refresh=True)

            # Also test broker API directly
            from src.services.core.broker_service import get_broker_service
            broker_service = get_broker_service()

            broker_orders = broker_service.get_fyers_orderbook(user_id)
            broker_trades = broker_service.get_fyers_tradebook(user_id)

            return jsonify({
                'success': True,
                'synced_orders_count': len(orders),
                'broker_orders_response': broker_orders,
                'broker_trades_response': broker_trades,
                'orders_sample': orders[:2] if orders else []
            })

        except Exception as e:
            app.logger.error(f"Error during broker sync: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/alerts', methods=['GET'])
    @login_required
    def api_get_alerts():
        """Get user alerts data."""
        try:
            # Return a simple alerts structure for now
            alerts = [
                {
                    'id': 1,
                    'type': 'info',
                    'title': 'Market Update',
                    'message': 'Markets are performing well today',
                    'timestamp': datetime.now().isoformat(),
                    'read': False
                }
            ]
            return jsonify({
                'success': True,
                'alerts': alerts,
                'total': len(alerts)
            })

        except Exception as e:
            app.logger.error(f"Error fetching alerts: {e}")
            return jsonify({
                'success': False,
                'alerts': [],
                'total': 0,
                'error': str(e)
            }), 500


    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5001)
