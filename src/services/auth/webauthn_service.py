"""
WebAuthn/Passkey Authentication Service

Provides passwordless authentication using the WebAuthn standard.
Supports passkey registration and authentication flows.
"""

import os
import json
import logging
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import (
    bytes_to_base64url,
    base64url_to_bytes,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AuthenticatorAttachment,
    PublicKeyCredentialDescriptor,
    AuthenticatorTransport,
)

logger = logging.getLogger(__name__)

# Get RP (Relying Party) configuration from environment
RP_ID = os.getenv('WEBAUTHN_RP_ID', 'localhost')
RP_NAME = os.getenv('WEBAUTHN_RP_NAME', 'Trading System')
RP_ORIGIN = os.getenv('WEBAUTHN_RP_ORIGIN', 'http://localhost:5001')


class WebAuthnService:
    """
    WebAuthn service for passkey registration and authentication.

    Flow:
    1. Registration: generate_registration_options -> verify_registration_response
    2. Authentication: generate_authentication_options -> verify_authentication_response
    """

    def __init__(self):
        try:
            from src.models.database import get_database_manager
            self.db_manager = get_database_manager()
        except ImportError:
            from models.database import get_database_manager
            self.db_manager = get_database_manager()

        self.rp_id = RP_ID
        self.rp_name = RP_NAME
        self.rp_origin = RP_ORIGIN

        # In-memory challenge storage (use Redis in production for multi-instance)
        self._challenges: Dict[int, bytes] = {}

    def generate_registration_options_for_user(
        self,
        user_id: int,
        username: str,
        display_name: str
    ) -> Tuple[Dict[str, Any], bytes]:
        """
        Generate WebAuthn registration options for a user.

        Args:
            user_id: Database user ID
            username: Username for WebAuthn
            display_name: Display name shown on authenticator

        Returns:
            Tuple of (options_dict, challenge_bytes)
        """
        try:
            from src.models.models import WebAuthnCredential
        except ImportError:
            from models.models import WebAuthnCredential

        # Get existing credentials to exclude
        existing_credentials = []
        with self.db_manager.get_session() as session:
            credentials = session.query(WebAuthnCredential).filter(
                WebAuthnCredential.user_id == user_id,
                WebAuthnCredential.is_active == True
            ).all()

            for cred in credentials:
                existing_credentials.append(
                    PublicKeyCredentialDescriptor(
                        id=cred.credential_id,
                        transports=self._parse_transports(cred.transports)
                    )
                )

        # Generate registration options
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=str(user_id).encode(),
            user_name=username,
            user_display_name=display_name,
            exclude_credentials=existing_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            timeout=60000,  # 60 seconds
        )

        # Store challenge for verification
        self._challenges[user_id] = options.challenge

        # Convert to JSON-serializable dict
        options_json = json.loads(options_to_json(options))

        logger.info(f"Generated registration options for user {user_id}")
        return options_json, options.challenge

    def verify_registration(
        self,
        user_id: int,
        credential_json: Dict[str, Any],
        device_name: str = "Passkey"
    ) -> Dict[str, Any]:
        """
        Verify WebAuthn registration response and store credential.

        Args:
            user_id: Database user ID
            credential_json: Registration response from browser
            device_name: User-friendly name for the device

        Returns:
            Dict with success status and credential info
        """
        try:
            from src.models.models import WebAuthnCredential
        except ImportError:
            from models.models import WebAuthnCredential

        try:
            # Get stored challenge
            challenge = self._challenges.get(user_id)
            if not challenge:
                return {'success': False, 'error': 'No registration challenge found. Please start again.'}

            # Verify the registration response
            verification = verify_registration_response(
                credential=credential_json,
                expected_challenge=challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.rp_origin,
                require_user_verification=False,  # Don't require for broader compatibility
            )

            # Extract transports if available
            transports = None
            if hasattr(credential_json, 'response') and hasattr(credential_json['response'], 'transports'):
                transports = json.dumps(credential_json['response'].get('transports', []))
            elif isinstance(credential_json, dict) and 'response' in credential_json:
                transports = json.dumps(credential_json['response'].get('transports', []))

            # Store the credential
            with self.db_manager.get_session() as session:
                # Check if credential already exists
                existing = session.query(WebAuthnCredential).filter(
                    WebAuthnCredential.credential_id == verification.credential_id
                ).first()

                if existing:
                    return {'success': False, 'error': 'This passkey is already registered.'}

                credential = WebAuthnCredential(
                    user_id=user_id,
                    credential_id=verification.credential_id,
                    public_key=verification.credential_public_key,
                    sign_count=verification.sign_count,
                    device_name=device_name,
                    transports=transports,
                    aaguid=str(verification.aaguid) if verification.aaguid else None,
                    created_at=datetime.utcnow()
                )
                session.add(credential)
                session.commit()

                credential_id = credential.id

            # Clear the challenge
            del self._challenges[user_id]

            logger.info(f"Registered new passkey for user {user_id}: {device_name}")
            return {
                'success': True,
                'credential_id': credential_id,
                'device_name': device_name,
                'message': 'Passkey registered successfully'
            }

        except Exception as e:
            logger.error(f"Registration verification failed: {e}")
            return {'success': False, 'error': str(e)}

    def generate_authentication_options_for_user(
        self,
        user_id: Optional[int] = None,
        username: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[bytes]]:
        """
        Generate WebAuthn authentication options.

        Args:
            user_id: Optional user ID (for username-first flow)
            username: Optional username to lookup user

        Returns:
            Tuple of (options_dict, challenge_bytes) or (None, None) if no credentials
        """
        try:
            from src.models.models import WebAuthnCredential, User
        except ImportError:
            from models.models import WebAuthnCredential, User

        allowed_credentials = []

        with self.db_manager.get_session() as session:
            # Get user if username provided
            if username and not user_id:
                user = session.query(User).filter(User.username == username).first()
                if user:
                    user_id = user.id

            # Get user's credentials
            if user_id:
                credentials = session.query(WebAuthnCredential).filter(
                    WebAuthnCredential.user_id == user_id,
                    WebAuthnCredential.is_active == True
                ).all()

                if not credentials:
                    return None, None

                for cred in credentials:
                    allowed_credentials.append(
                        PublicKeyCredentialDescriptor(
                            id=cred.credential_id,
                            transports=self._parse_transports(cred.transports)
                        )
                    )

        # Generate authentication options
        options = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=allowed_credentials if allowed_credentials else None,
            user_verification=UserVerificationRequirement.PREFERRED,
            timeout=60000,
        )

        # Store challenge (use user_id or 0 for discoverable credentials)
        challenge_key = user_id if user_id else 0
        self._challenges[challenge_key] = options.challenge

        options_json = json.loads(options_to_json(options))

        logger.info(f"Generated authentication options for user {user_id}")
        return options_json, options.challenge

    def verify_authentication(
        self,
        credential_json: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Verify WebAuthn authentication response.

        Args:
            credential_json: Authentication response from browser
            user_id: Optional user ID (for username-first flow)

        Returns:
            Dict with success status and user info
        """
        try:
            from src.models.models import WebAuthnCredential, User
        except ImportError:
            from models.models import WebAuthnCredential, User

        try:
            # Get credential ID from response
            raw_id = credential_json.get('rawId') or credential_json.get('id')
            if isinstance(raw_id, str):
                credential_id = base64url_to_bytes(raw_id)
            else:
                credential_id = raw_id

            # Find the credential in database
            with self.db_manager.get_session() as session:
                credential = session.query(WebAuthnCredential).filter(
                    WebAuthnCredential.credential_id == credential_id,
                    WebAuthnCredential.is_active == True
                ).first()

                if not credential:
                    return {'success': False, 'error': 'Passkey not found or inactive.'}

                # Get stored challenge
                challenge_key = credential.user_id if user_id is None else user_id
                challenge = self._challenges.get(challenge_key) or self._challenges.get(0)

                if not challenge:
                    return {'success': False, 'error': 'Authentication session expired. Please try again.'}

                # Verify the authentication
                verification = verify_authentication_response(
                    credential=credential_json,
                    expected_challenge=challenge,
                    expected_rp_id=self.rp_id,
                    expected_origin=self.rp_origin,
                    credential_public_key=credential.public_key,
                    credential_current_sign_count=credential.sign_count,
                    require_user_verification=False,
                )

                # Update sign count and last used
                credential.sign_count = verification.new_sign_count
                credential.last_used_at = datetime.utcnow()

                # Get user info
                user = session.query(User).filter(User.id == credential.user_id).first()
                if not user:
                    return {'success': False, 'error': 'User not found.'}

                if not user.is_active:
                    return {'success': False, 'error': 'Account is inactive.'}

                # Update last login
                user.last_login = datetime.utcnow()
                session.commit()

                user_data = {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'is_admin': user.is_admin
                }

            # Clear challenge
            if challenge_key in self._challenges:
                del self._challenges[challenge_key]
            if 0 in self._challenges:
                del self._challenges[0]

            logger.info(f"Successful passkey authentication for user {user_data['username']}")
            return {
                'success': True,
                'user': user_data,
                'message': 'Authentication successful'
            }

        except Exception as e:
            logger.error(f"Authentication verification failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_user_credentials(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all passkey credentials for a user.

        Args:
            user_id: Database user ID

        Returns:
            List of credential info dicts
        """
        try:
            from src.models.models import WebAuthnCredential
        except ImportError:
            from models.models import WebAuthnCredential

        credentials = []
        with self.db_manager.get_session() as session:
            creds = session.query(WebAuthnCredential).filter(
                WebAuthnCredential.user_id == user_id
            ).order_by(WebAuthnCredential.created_at.desc()).all()

            for cred in creds:
                credentials.append({
                    'id': cred.id,
                    'device_name': cred.device_name,
                    'is_active': cred.is_active,
                    'created_at': cred.created_at.isoformat() if cred.created_at else None,
                    'last_used_at': cred.last_used_at.isoformat() if cred.last_used_at else None,
                    'credential_id_preview': bytes_to_base64url(cred.credential_id)[:16] + '...'
                })

        return credentials

    def delete_credential(self, user_id: int, credential_id: int) -> Dict[str, Any]:
        """
        Delete a passkey credential.

        Args:
            user_id: Database user ID
            credential_id: Credential ID to delete

        Returns:
            Dict with success status
        """
        try:
            from src.models.models import WebAuthnCredential
        except ImportError:
            from models.models import WebAuthnCredential

        with self.db_manager.get_session() as session:
            credential = session.query(WebAuthnCredential).filter(
                WebAuthnCredential.id == credential_id,
                WebAuthnCredential.user_id == user_id
            ).first()

            if not credential:
                return {'success': False, 'error': 'Credential not found.'}

            session.delete(credential)
            session.commit()

        logger.info(f"Deleted passkey {credential_id} for user {user_id}")
        return {'success': True, 'message': 'Passkey deleted successfully'}

    def rename_credential(self, user_id: int, credential_id: int, new_name: str) -> Dict[str, Any]:
        """
        Rename a passkey credential.

        Args:
            user_id: Database user ID
            credential_id: Credential ID to rename
            new_name: New device name

        Returns:
            Dict with success status
        """
        try:
            from src.models.models import WebAuthnCredential
        except ImportError:
            from models.models import WebAuthnCredential

        with self.db_manager.get_session() as session:
            credential = session.query(WebAuthnCredential).filter(
                WebAuthnCredential.id == credential_id,
                WebAuthnCredential.user_id == user_id
            ).first()

            if not credential:
                return {'success': False, 'error': 'Credential not found.'}

            credential.device_name = new_name
            session.commit()

        logger.info(f"Renamed passkey {credential_id} to '{new_name}'")
        return {'success': True, 'message': 'Passkey renamed successfully'}

    def user_has_passkeys(self, user_id: int) -> bool:
        """Check if user has any registered passkeys."""
        try:
            from src.models.models import WebAuthnCredential
        except ImportError:
            from models.models import WebAuthnCredential

        with self.db_manager.get_session() as session:
            count = session.query(WebAuthnCredential).filter(
                WebAuthnCredential.user_id == user_id,
                WebAuthnCredential.is_active == True
            ).count()

        return count > 0

    def _parse_transports(self, transports_json: Optional[str]) -> List[AuthenticatorTransport]:
        """Parse transports JSON string to list of AuthenticatorTransport."""
        if not transports_json:
            return []

        try:
            transports = json.loads(transports_json)
            result = []
            transport_map = {
                'usb': AuthenticatorTransport.USB,
                'ble': AuthenticatorTransport.BLE,
                'nfc': AuthenticatorTransport.NFC,
                'internal': AuthenticatorTransport.INTERNAL,
                'hybrid': AuthenticatorTransport.HYBRID,
            }
            for t in transports:
                if t.lower() in transport_map:
                    result.append(transport_map[t.lower()])
            return result
        except:
            return []


# Singleton instance
_webauthn_service = None


def get_webauthn_service() -> WebAuthnService:
    """Get singleton instance of WebAuthnService."""
    global _webauthn_service
    if _webauthn_service is None:
        _webauthn_service = WebAuthnService()
    return _webauthn_service
