"""
FYERS Token Refresh Service - Two-tier automated token generation.

Tier 1: v3 validate-refresh-token API (daily, needs refresh_token + PIN)
Tier 2: Headless TOTP login via vagator APIs (fallback when refresh_token expired)

With both tiers, manual OAuth login is NEVER needed.
"""
import base64
import hashlib
import hmac
import logging
import os
import struct
import time
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

FYERS_REFRESH_TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
FYERS_PIN = os.getenv('FYERS_PIN', '')
FYERS_TOTP_KEY = os.getenv('FYERS_TOTP_KEY', '')
FYERS_LOGIN_ID = os.getenv('FYERS_CLIENT_ID_LOGIN', '')


def _generate_totp(totp_key: str, time_step: int = 30, digits: int = 6) -> str:
    """Generate a TOTP code from the base32 secret key."""
    key = base64.b32decode(totp_key.upper() + "=" * ((8 - len(totp_key)) % 8))
    counter = struct.pack(">Q", int(time.time() / time_step))
    mac = hmac.new(key, counter, "sha1").digest()
    offset = mac[-1] & 0x0F
    binary = struct.unpack(">L", mac[offset: offset + 4])[0] & 0x7FFFFFFF
    return str(binary)[-digits:].zfill(digits)


class FyersTokenRefreshService:
    """Two-tier FYERS token refresh: v3 API first, TOTP headless login as fallback."""

    def __init__(self):
        pass

    def _compute_app_id_hash(self, client_id: str, secret_key: str) -> str:
        """Compute SHA256 hash of client_id:secret_key as required by FYERS API."""
        return hashlib.sha256(f"{client_id}:{secret_key}".encode()).hexdigest()

    def refresh_fyers_token(self, user_id: int, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh FYERS access token. Tries v3 refresh API first,
        falls back to headless TOTP login if refresh_token is missing/expired.
        """
        logger.info(f"Attempting FYERS token refresh for user {user_id}")

        try:
            from src.models.database import get_database_manager
            from src.models.models import BrokerConfiguration

            db_manager = get_database_manager()

            with db_manager.get_session() as session:
                config = session.query(BrokerConfiguration).filter_by(
                    broker_name='fyers', user_id=user_id
                ).first()

                if not config:
                    logger.error(f"FYERS config not found for user {user_id}")
                    return None

                client_id = config.client_id
                secret_key = config.api_secret
                redirect_uri = config.redirect_url
                stored_refresh_token = refresh_token or config.refresh_token
                pin = FYERS_PIN
                login_id = config.api_key or FYERS_LOGIN_ID
                totp_key = FYERS_TOTP_KEY

                if not all([client_id, secret_key]):
                    logger.error(f"Missing app credentials for user {user_id}")
                    self._mark_reauth_required(config, session, "Missing client_id or secret_key")
                    return None

                # Tier 1: Try v3 refresh token API (fast, no login needed)
                if stored_refresh_token and pin:
                    result = self._refresh_via_v3_api(
                        user_id, client_id, secret_key, stored_refresh_token, pin
                    )
                    if result:
                        self._save_tokens(config, session, result)
                        return result
                    logger.warning(f"Tier 1 (v3 refresh) failed for user {user_id}, trying Tier 2...")

                # Tier 2: Headless TOTP login (full re-auth, no browser)
                if login_id and pin and totp_key and redirect_uri:
                    result = self._refresh_via_totp_login(
                        user_id, login_id, pin, totp_key,
                        client_id, secret_key, redirect_uri
                    )
                    if result:
                        self._save_tokens(config, session, result)
                        return result
                    logger.error(f"Tier 2 (TOTP login) also failed for user {user_id}")
                else:
                    missing = []
                    if not login_id: missing.append('FYERS_CLIENT_ID_LOGIN')
                    if not pin: missing.append('FYERS_PIN')
                    if not totp_key: missing.append('FYERS_TOTP_KEY')
                    if not redirect_uri: missing.append('redirect_uri')
                    logger.error(f"Tier 2 skipped - missing: {', '.join(missing)}")

                self._mark_reauth_required(config, session, "Both refresh tiers failed")
                return None

        except Exception as e:
            logger.error(f"Error refreshing FYERS token for user {user_id}: {e}", exc_info=True)
            return None

    def _refresh_via_v3_api(
        self, user_id: int, client_id: str, secret_key: str,
        refresh_token: str, pin: str
    ) -> Optional[Dict[str, Any]]:
        """Tier 1: Use FYERS v3 validate-refresh-token API."""
        try:
            app_id_hash = self._compute_app_id_hash(client_id, secret_key)
            payload = {
                "grant_type": "refresh_token",
                "appIdHash": app_id_hash,
                "refresh_token": refresh_token,
                "pin": pin
            }

            logger.info(f"Tier 1: Calling validate-refresh-token for user {user_id}")
            response = requests.post(
                FYERS_REFRESH_TOKEN_URL,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )

            result = response.json()
            logger.info(f"Tier 1 response: status={result.get('s')}, code={result.get('code')}")

            if result.get('s') == 'ok' and result.get('access_token'):
                return {
                    'access_token': result['access_token'],
                    'refresh_token': result.get('refresh_token', refresh_token),
                    'refreshed_at': datetime.utcnow().isoformat()
                }

            logger.warning(f"Tier 1 failed: {result.get('message', 'Unknown error')}")
            return None

        except Exception as e:
            logger.error(f"Tier 1 error: {e}")
            return None

    def _refresh_via_totp_login(
        self, user_id: int, login_id: str, pin: str, totp_key: str,
        client_id: str, secret_key: str, redirect_uri: str
    ) -> Optional[Dict[str, Any]]:
        """
        Tier 2: Full headless TOTP login via Fyers vagator APIs.
        5-step flow: send_otp → verify_totp → verify_pin → get_auth_code → generate_token
        """
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
        }

        s = requests.Session()
        s.headers.update(headers)

        try:
            # Step 1: Send login OTP
            fy_id_b64 = base64.b64encode(login_id.encode()).decode()
            logger.info(f"Tier 2 Step 1 REQ: fy_id_b64={fy_id_b64[:8]}... raw={login_id} app_id=2")
            r1 = s.post(
                "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",
                json={"fy_id": fy_id_b64, "app_id": "2"},
                timeout=30
            )
            logger.info(f"Tier 2 Step 1 RESP: status={r1.status_code} body={r1.text}")
            if r1.status_code != 200 or r1.json().get('s') == 'error':
                logger.error(f"Step 1 failed: {r1.status_code} {r1.text[:300]}")
                return None
            request_key = r1.json()["request_key"]

            # Step 2: Verify TOTP — try multiple variants to find which Fyers accepts
            otp_code = _generate_totp(totp_key)
            logger.info(f"Tier 2 Step 2 REQ: request_key={request_key[:12]}... otp={otp_code}")

            # Variant A: original (int otp)
            r2 = s.post(
                "https://api-t2.fyers.in/vagator/v2/verify_otp",
                json={"request_key": request_key, "otp": int(otp_code)},
                timeout=30
            )
            logger.info(f"Tier 2 Step 2 RESP variant_A: status={r2.status_code} body={r2.text}")

            if r2.status_code != 200 or r2.json().get('s') == 'error':
                # Don't burn more retries — return diagnostic info
                logger.error(f"Step 2 failed: {r2.status_code} {r2.text[:300]}")
                return None
            request_key = r2.json()["request_key"]

            # Step 3: Verify PIN
            pin_b64 = base64.b64encode(str(pin).encode()).decode()
            logger.info(f"Tier 2 Step 3: Verifying PIN...")
            r3 = s.post(
                "https://api-t2.fyers.in/vagator/v2/verify_pin_v2",
                json={
                    "request_key": request_key,
                    "identity_type": "pin",
                    "identifier": pin_b64
                },
                timeout=30
            )
            if r3.status_code != 200:
                logger.error(f"Step 3 failed: {r3.status_code} {r3.text[:200]}")
                return None
            bearer_token = r3.json()["data"]["access_token"]

            # Step 4: Get authorization code (v3 endpoint)
            # Parse client_id format <APP_ID>-<APPTYPE> e.g. M10LT1T9EH-200
            parts = client_id.split("-")
            app_id = parts[0]
            app_type = parts[1] if len(parts) > 1 else "100"
            logger.info(f"Tier 2 Step 4: Getting auth code (app_id={app_id} appType={app_type})...")
            r4 = s.post(
                "https://api-t1.fyers.in/api/v3/token",
                headers={
                    "authorization": f"Bearer {bearer_token}",
                    "content-type": "application/json; charset=UTF-8",
                },
                json={
                    "fyers_id": login_id,
                    "app_id": app_id,
                    "redirect_uri": redirect_uri,
                    "appType": app_type,
                    "code_challenge": "",
                    "state": "None",
                    "scope": "",
                    "nonce": "",
                    "response_type": "code",
                    "create_cookie": True,
                },
                timeout=30,
                allow_redirects=False
            )
            if r4.status_code not in (200, 308):
                logger.error(f"Step 4 failed: {r4.status_code} {r4.text[:200]}")
                return None

            url_with_code = r4.json().get("Url", "")
            parsed = urlparse(url_with_code)
            auth_code = parse_qs(parsed.query).get("auth_code", [None])[0]

            if not auth_code:
                logger.error(f"Step 4: No auth_code in URL: {url_with_code[:100]}")
                return None

            # Step 5: Exchange auth code for access token
            from fyers_apiv3 import fyersModel
            session_model = fyersModel.SessionModel(
                client_id=client_id,
                secret_key=secret_key,
                redirect_uri=redirect_uri,
                response_type="code",
                grant_type="authorization_code",
            )
            session_model.set_token(auth_code)
            response = session_model.generate_token()

            if response.get('s') == 'ok' or response.get('access_token'):
                logger.info(f"Tier 2: Access token generated successfully for user {user_id}")
                return {
                    'access_token': response['access_token'],
                    'refresh_token': response.get('refresh_token', ''),
                    'refreshed_at': datetime.utcnow().isoformat()
                }

            logger.error(f"Step 5 failed: {response}")
            return None

        except Exception as e:
            logger.error(f"Tier 2 TOTP login error: {e}", exc_info=True)
            return None

    def _save_tokens(self, config, session, token_result: Dict[str, Any]):
        """Save refreshed tokens to database."""
        config.access_token = token_result['access_token']
        if token_result.get('refresh_token'):
            config.refresh_token = token_result['refresh_token']
        config.is_connected = True
        config.connection_status = 'connected'
        config.error_message = None
        config.updated_at = datetime.utcnow()
        session.commit()
        logger.info(f"Saved new tokens for user {config.user_id}")

    def _mark_reauth_required(self, config, session, reason: str):
        """Mark broker config as requiring re-authentication."""
        config.connection_status = 'reauth_required'
        config.is_connected = False
        config.error_message = reason
        config.updated_at = datetime.utcnow()
        session.commit()
        logger.warning(f"Marked user {config.user_id} as reauth_required: {reason}")

    def check_token_validity(self, access_token: str) -> Dict[str, Any]:
        """Check if a FYERS token is valid by making a test API call."""
        try:
            response = requests.get(
                "https://api-t1.fyers.in/api/v3/profile",
                headers={'Authorization': access_token, 'Content-Type': 'application/json'},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('s') == 'ok':
                    return {'is_valid': True, 'message': 'Token is valid'}
                return {
                    'is_valid': False,
                    'message': f"API Error: {data.get('message', 'Unknown error')}",
                    'error_code': data.get('code')
                }
            return {
                'is_valid': False,
                'message': f"HTTP {response.status_code}",
                'status_code': response.status_code
            }

        except Exception as e:
            return {'is_valid': False, 'message': str(e)}

    def get_token_info(self, access_token: str) -> Dict[str, Any]:
        """Get expiration info from a FYERS JWT token."""
        try:
            import jwt
            decoded = jwt.decode(access_token, options={"verify_signature": False})

            exp_timestamp = decoded.get('exp', 0)
            iat_timestamp = decoded.get('iat', 0)
            exp_datetime = datetime.fromtimestamp(exp_timestamp) if exp_timestamp else None
            iat_datetime = datetime.fromtimestamp(iat_timestamp) if iat_timestamp else None
            current_time = datetime.now()
            is_expired = exp_datetime and current_time >= exp_datetime

            return {
                'issued_at': iat_datetime.isoformat() if iat_datetime else None,
                'expires_at': exp_datetime.isoformat() if exp_datetime else None,
                'is_expired': is_expired,
                'time_until_expiry': str(exp_datetime - current_time) if exp_datetime else None,
                'client_id': decoded.get('client_id', ''),
                'user_id': decoded.get('user_id', '')
            }

        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return {'error': str(e), 'is_expired': True}


def register_fyers_refresh_callback():
    """Register FYERS token refresh callback with the token manager."""
    try:
        from ..utils.token_manager_service import get_token_manager

        token_manager = get_token_manager()
        fyers_refresh_service = FyersTokenRefreshService()

        token_manager.register_refresh_callback(
            'fyers',
            fyers_refresh_service.refresh_fyers_token
        )

        logger.info("Registered FYERS two-tier token refresh callback")

    except Exception as e:
        logger.error(f"Error registering FYERS refresh callback: {e}")


# Auto-register on import
register_fyers_refresh_callback()
