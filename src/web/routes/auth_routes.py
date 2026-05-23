"""
Authentication Routes

Handles WebAuthn/Passkey registration and authentication.
"""

import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user, login_user

logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/webauthn/register/begin', methods=['POST'])
@login_required
def webauthn_register_begin():
    """
    Begin WebAuthn passkey registration.

    Returns registration options for the browser's WebAuthn API.
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service

        webauthn_service = get_webauthn_service()

        # Get optional device name from request
        data = request.get_json() or {}
        device_name = data.get('device_name', 'Passkey')

        # Generate registration options
        display_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip()
        if not display_name:
            display_name = current_user.username

        options, _ = webauthn_service.generate_registration_options_for_user(
            user_id=current_user.id,
            username=current_user.username,
            display_name=display_name
        )

        return jsonify({
            'success': True,
            'options': options
        }), 200

    except Exception as e:
        logger.error(f"Error starting passkey registration: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/register/complete', methods=['POST'])
@login_required
def webauthn_register_complete():
    """
    Complete WebAuthn passkey registration.

    Verifies the registration response and stores the credential.
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service

        webauthn_service = get_webauthn_service()

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No registration data provided'
            }), 400

        credential = data.get('credential')
        device_name = data.get('device_name', 'Passkey')

        if not credential:
            return jsonify({
                'success': False,
                'error': 'No credential data provided'
            }), 400

        # Verify and store the credential
        result = webauthn_service.verify_registration(
            user_id=current_user.id,
            credential_json=credential,
            device_name=device_name
        )

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error completing passkey registration: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/authenticate/begin', methods=['POST'])
def webauthn_authenticate_begin():
    """
    Begin WebAuthn passkey authentication.

    Can be called with or without username (for discoverable credentials).
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service

        webauthn_service = get_webauthn_service()

        data = request.get_json() or {}
        username = data.get('username')

        # Generate authentication options
        options, challenge = webauthn_service.generate_authentication_options_for_user(
            username=username
        )

        if options is None:
            return jsonify({
                'success': False,
                'error': 'No passkeys found for this account. Please use password login.'
            }), 404

        return jsonify({
            'success': True,
            'options': options
        }), 200

    except Exception as e:
        logger.error(f"Error starting passkey authentication: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/authenticate/complete', methods=['POST'])
def webauthn_authenticate_complete():
    """
    Complete WebAuthn passkey authentication.

    Verifies the authentication response and logs in the user.
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service
        from src.models.database import get_database_manager
        from src.models.models import User

        webauthn_service = get_webauthn_service()

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No authentication data provided'
            }), 400

        credential = data.get('credential')
        if not credential:
            return jsonify({
                'success': False,
                'error': 'No credential data provided'
            }), 400

        # Verify the authentication
        result = webauthn_service.verify_authentication(
            credential_json=credential
        )

        if not result['success']:
            return jsonify(result), 401

        # Get user and log them in
        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            user = session.query(User).filter(User.id == result['user']['id']).first()
            if user:
                session.expunge(user)
                from flask import session as flask_session
                flask_session.permanent = True
                login_user(user, remember=True)

        return jsonify({
            'success': True,
            'message': 'Authentication successful',
            'user': {
                'id': result['user']['id'],
                'username': result['user']['username']
            }
        }), 200

    except Exception as e:
        logger.error(f"Error completing passkey authentication: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/credentials', methods=['GET'])
@login_required
def list_credentials():
    """
    List all passkey credentials for the current user.
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service

        webauthn_service = get_webauthn_service()
        credentials = webauthn_service.get_user_credentials(current_user.id)

        return jsonify({
            'success': True,
            'credentials': credentials
        }), 200

    except Exception as e:
        logger.error(f"Error listing credentials: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/credentials/<int:credential_id>', methods=['DELETE'])
@login_required
def delete_credential(credential_id):
    """
    Delete a passkey credential.
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service

        webauthn_service = get_webauthn_service()
        result = webauthn_service.delete_credential(current_user.id, credential_id)

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error deleting credential: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/credentials/<int:credential_id>/rename', methods=['POST'])
@login_required
def rename_credential(credential_id):
    """
    Rename a passkey credential.
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service

        webauthn_service = get_webauthn_service()

        data = request.get_json() or {}
        new_name = data.get('name', '').strip()

        if not new_name:
            return jsonify({
                'success': False,
                'error': 'Name is required'
            }), 400

        result = webauthn_service.rename_credential(current_user.id, credential_id, new_name)

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error renaming credential: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/webauthn/check', methods=['GET'])
def check_passkey_support():
    """
    Check if a user has passkeys registered.

    Query params:
        username: Username to check
    """
    try:
        from src.services.auth.webauthn_service import get_webauthn_service
        from src.models.database import get_database_manager
        from src.models.models import User

        username = request.args.get('username')
        if not username:
            return jsonify({
                'success': True,
                'has_passkeys': False
            }), 200

        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                return jsonify({
                    'success': True,
                    'has_passkeys': False
                }), 200

            user_id = user.id

        webauthn_service = get_webauthn_service()
        has_passkeys = webauthn_service.user_has_passkeys(user_id)

        return jsonify({
            'success': True,
            'has_passkeys': has_passkeys
        }), 200

    except Exception as e:
        logger.error(f"Error checking passkey support: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'has_passkeys': False
        }), 200
