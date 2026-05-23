"""
FYERS Automated Token Refresh using Playwright
Automates the Fyers OAuth flow for token refresh.
"""
import logging
import time
import os
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration from environment or defaults
FYERS_CLIENT_ID_LOGIN = os.getenv('FYERS_CLIENT_ID_LOGIN', '')  # Your Fyers login ID (mobile/email)
FYERS_PIN = os.getenv('FYERS_PIN', '9884')  # TOTP PIN as specified


class FyersPlaywrightRefreshService:
    """Service for automated Fyers token refresh using Playwright."""

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    def refresh_token_for_user(self, user_id: int, pin: str = None) -> Dict[str, Any]:
        """
        Refresh Fyers token for a user using Playwright automation.

        Args:
            user_id: Database user ID
            pin: TOTP PIN for Fyers authentication (defaults to env var FYERS_PIN)

        Returns:
            Dict with success status and message
        """
        from src.services.brokers.fyers_service import get_fyers_service

        pin = pin or FYERS_PIN

        if not pin:
            logger.error("Fyers PIN not configured. Set FYERS_PIN environment variable.")
            return {
                'success': False,
                'error': 'Fyers PIN not configured'
            }

        try:
            # Get the auth URL
            fyers_service = get_fyers_service()
            auth_url = fyers_service.generate_auth_url(user_id)

            logger.info(f"Starting automated Fyers token refresh for user {user_id}")
            logger.info(f"Auth URL: {auth_url[:50]}...")

            # Run the Playwright automation
            result = self._automate_fyers_login(auth_url, pin, user_id)

            return result

        except Exception as e:
            logger.error(f"Error in Fyers token refresh: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def _automate_fyers_login(self, auth_url: str, pin: str, user_id: int) -> Dict[str, Any]:
        """
        Automate the Fyers login flow using Playwright.

        The Fyers OAuth flow has these steps:
        1. Enter mobile number/client ID
        2. Request OTP (or if TOTP is set up, use that)
        3. Enter TOTP PIN
        4. Grant access

        Args:
            auth_url: Fyers OAuth authorization URL
            pin: TOTP PIN
            user_id: User ID for callback handling

        Returns:
            Dict with result status
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return {
                'success': False,
                'error': 'Playwright not installed'
            }

        # Get login credentials from database
        from src.models.database import get_database_manager
        from src.models.models import BrokerConfiguration

        db_manager = get_database_manager()
        fyers_login_id = None

        with db_manager.get_session() as session:
            config = session.query(BrokerConfiguration).filter_by(
                broker_name='fyers',
                user_id=user_id
            ).first()

            if config:
                # The client_id in broker config is typically the app client ID
                # We need the user's login ID (mobile/email) which might be stored separately
                # For now, try to extract from client_id or use environment variable
                fyers_login_id = FYERS_CLIENT_ID_LOGIN or os.getenv('FYERS_LOGIN_ID', '')

        if not fyers_login_id:
            logger.error("Fyers login ID not configured. Set FYERS_CLIENT_ID_LOGIN environment variable.")
            return {
                'success': False,
                'error': 'Fyers login ID not configured. Set FYERS_CLIENT_ID_LOGIN env var.'
            }

        try:
            with sync_playwright() as p:
                # Launch browser (headless for server environment)
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )

                context = browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )

                page = context.new_page()

                try:
                    # Navigate to auth URL
                    logger.info("Navigating to Fyers auth URL...")
                    page.goto(auth_url, wait_until='networkidle', timeout=60000)
                    time.sleep(3)

                    # Take screenshot for debugging
                    page.screenshot(path=f"/tmp/fyers_step1_{user_id}.png")

                    # Step 1: Enter mobile number/client ID
                    logger.info("Looking for mobile/client ID input...")
                    mobile_input = page.locator('input[type="tel"], input[type="text"][placeholder*="mobile"], input[placeholder*="Mobile"], input#mobileNumberInput, input[name="mobile"], input[autocomplete="tel"]')

                    if mobile_input.count() > 0:
                        logger.info(f"Found mobile input, entering login ID: {fyers_login_id[:4]}***")
                        mobile_input.first.fill(fyers_login_id)
                        time.sleep(1)

                        # Click submit/continue button
                        submit_btn = page.locator('button[type="submit"]:not([disabled]), button:has-text("Continue"):not([disabled]), button:has-text("Submit"):not([disabled]), button#mobileNumberSubmit:not([disabled])')

                        # Wait for button to be enabled
                        logger.info("Waiting for submit button to be enabled...")
                        page.wait_for_selector('button[type="submit"]:not([disabled]), button#mobileNumberSubmit:not([disabled])', timeout=10000)

                        submit_btn = page.locator('button[type="submit"]:not([disabled]), button#mobileNumberSubmit:not([disabled])')
                        if submit_btn.count() > 0:
                            logger.info("Clicking submit button...")
                            submit_btn.first.click()
                            time.sleep(3)

                    page.screenshot(path=f"/tmp/fyers_step2_{user_id}.png")

                    # Step 2: Look for TOTP/PIN input
                    # Fyers might show OTP input or TOTP input depending on account setup
                    logger.info("Looking for PIN/OTP input...")

                    # Wait for the next step to load
                    time.sleep(2)

                    # Look for TOTP/PIN input field
                    pin_selectors = [
                        'input[type="tel"][placeholder*="PIN"]',
                        'input[type="password"]',
                        'input[placeholder*="TOTP"]',
                        'input[placeholder*="OTP"]',
                        'input#totp',
                        'input#pin',
                        'input[name="pin"]',
                        'input[name="totp"]',
                        'input[maxlength="4"]',
                        'input[maxlength="6"]'
                    ]

                    pin_input = None
                    for selector in pin_selectors:
                        try:
                            pin_input = page.locator(selector)
                            if pin_input.count() > 0:
                                logger.info(f"Found PIN input with selector: {selector}")
                                break
                        except:
                            continue

                    if pin_input and pin_input.count() > 0:
                        logger.info("Entering TOTP PIN...")
                        pin_input.first.fill(pin)
                        time.sleep(1)

                        # Click verify/submit button
                        verify_btn = page.locator('button[type="submit"]:not([disabled]), button:has-text("Verify"):not([disabled]), button:has-text("Submit"):not([disabled])')
                        if verify_btn.count() > 0:
                            logger.info("Clicking verify button...")
                            verify_btn.first.click()
                            time.sleep(3)
                    else:
                        logger.warning("Could not find PIN input field")
                        page.screenshot(path=f"/tmp/fyers_no_pin_{user_id}.png")

                    page.screenshot(path=f"/tmp/fyers_step3_{user_id}.png")

                    # Step 3: Grant access (if prompted)
                    # Look for any "Allow" or "Grant Access" buttons
                    grant_btn = page.locator('button:has-text("Allow"), button:has-text("Grant"), button:has-text("Authorize"), button:has-text("Approve")')
                    if grant_btn.count() > 0:
                        logger.info("Clicking grant access button...")
                        grant_btn.first.click()
                        time.sleep(3)

                    # Wait for redirect to callback URL
                    logger.info("Waiting for callback redirect...")
                    try:
                        page.wait_for_url('**/callback**', timeout=30000)
                    except:
                        # Try waiting for auth_code in URL
                        page.wait_for_url('**auth_code=**', timeout=30000)

                    # Extract auth code from URL
                    current_url = page.url
                    logger.info(f"Redirected to: {current_url[:100]}...")

                    # Parse auth code from URL
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(current_url)
                    params = parse_qs(parsed.query)

                    auth_code = params.get('auth_code', [None])[0]

                    if auth_code:
                        logger.info("Successfully obtained auth code, exchanging for token...")

                        # Exchange auth code for token
                        from src.services.brokers.fyers_service import get_fyers_service
                        fyers_service = get_fyers_service()
                        result = fyers_service.exchange_auth_code(user_id, auth_code)

                        if result.get('success'):
                            logger.info(f"Successfully refreshed Fyers token for user {user_id}")
                            return {
                                'success': True,
                                'message': 'Token refreshed successfully'
                            }
                        else:
                            logger.error(f"Failed to exchange auth code: {result}")
                            return {
                                'success': False,
                                'error': 'Failed to exchange auth code'
                            }
                    else:
                        logger.error("No auth code found in redirect URL")
                        page.screenshot(path=f"/tmp/fyers_no_authcode_{user_id}.png")
                        return {
                            'success': False,
                            'error': f'No auth code in redirect. URL: {current_url[:100]}'
                        }

                except Exception as e:
                    logger.error(f"Error during Fyers login automation: {e}")

                    # Take screenshot for debugging
                    try:
                        screenshot_path = f"/tmp/fyers_error_{user_id}_{int(time.time())}.png"
                        page.screenshot(path=screenshot_path)
                        logger.info(f"Screenshot saved to: {screenshot_path}")
                    except:
                        pass

                    return {
                        'success': False,
                        'error': str(e)
                    }
                finally:
                    browser.close()

        except Exception as e:
            logger.error(f"Playwright browser error: {e}")
            return {
                'success': False,
                'error': str(e)
            }


def refresh_all_user_tokens():
    """Refresh tokens for all users with Fyers configuration."""
    from src.models.database import get_database_manager
    from src.models.models import BrokerConfiguration

    logger.info("=" * 80)
    logger.info("Starting Automated Fyers Token Refresh")
    logger.info("=" * 80)

    try:
        db_manager = get_database_manager()
        refresh_service = FyersPlaywrightRefreshService()

        with db_manager.get_session() as session:
            # Get all Fyers configurations
            fyers_configs = session.query(BrokerConfiguration).filter_by(
                broker_name='fyers'
            ).all()

            if not fyers_configs:
                logger.info("No Fyers configurations found")
                return

            for config in fyers_configs:
                user_id = config.user_id or 1

                # Check if token needs refresh
                from src.services.utils.token_manager_service import get_token_manager
                token_manager = get_token_manager()
                status = token_manager.get_token_status(user_id, 'fyers')

                if not status.get('has_token') or status.get('is_expired'):
                    logger.info(f"Token needs refresh for user {user_id}")
                    result = refresh_service.refresh_token_for_user(user_id)

                    if result.get('success'):
                        logger.info(f"Successfully refreshed token for user {user_id}")
                    else:
                        logger.error(f"Failed to refresh token for user {user_id}: {result.get('error')}")
                else:
                    # Check if expiring soon (within 6 hours)
                    if status.get('expires_at'):
                        expiry_time = datetime.fromisoformat(status['expires_at'])
                        time_until_expiry = expiry_time - datetime.now()
                        hours_until_expiry = time_until_expiry.total_seconds() / 3600

                        if hours_until_expiry < 6:
                            logger.info(f"Token expiring soon for user {user_id} ({hours_until_expiry:.1f} hours), refreshing...")
                            result = refresh_service.refresh_token_for_user(user_id)

                            if result.get('success'):
                                logger.info(f"Successfully refreshed token for user {user_id}")
                            else:
                                logger.error(f"Failed to refresh token for user {user_id}: {result.get('error')}")
                        else:
                            logger.info(f"Token still valid for user {user_id} ({hours_until_expiry:.1f} hours remaining)")

    except Exception as e:
        logger.error(f"Error in automated token refresh: {e}", exc_info=True)


# Singleton instance
_refresh_service: Optional[FyersPlaywrightRefreshService] = None


def get_playwright_refresh_service() -> FyersPlaywrightRefreshService:
    """Get singleton instance of FyersPlaywrightRefreshService."""
    global _refresh_service
    if _refresh_service is None:
        _refresh_service = FyersPlaywrightRefreshService()
    return _refresh_service
