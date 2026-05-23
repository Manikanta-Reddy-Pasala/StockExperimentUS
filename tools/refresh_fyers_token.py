#!/usr/bin/env python3
"""
Manual FYERS token refresh using the v3 API.
Run this to test API-based refresh before deploying.

Usage:
    python tools/refresh_fyers_token.py [--user-id 1]
    docker exec trading_system_app python tools/refresh_fyers_token.py
"""
import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Refresh FYERS token via API')
    parser.add_argument('--user-id', type=int, default=1, help='User ID (default: 1)')
    parser.add_argument('--force', action='store_true', help='Force refresh even if token is valid')
    args = parser.parse_args()

    from src.models.database import get_database_manager
    from src.models.models import BrokerConfiguration
    from src.services.brokers.fyers_token_refresh import FyersTokenRefreshService

    db_manager = get_database_manager()
    refresh_service = FyersTokenRefreshService()

    with db_manager.get_session() as session:
        config = session.query(BrokerConfiguration).filter_by(
            broker_name='fyers',
            user_id=args.user_id
        ).first()

        if not config:
            print(f"No FYERS config found for user {args.user_id}")
            sys.exit(1)

        print(f"User ID: {args.user_id}")
        print(f"Client ID: {config.client_id}")
        print(f"Has access_token: {bool(config.access_token)}")
        print(f"Has refresh_token: {bool(config.refresh_token)}")
        print(f"Connection status: {config.connection_status}")
        print(f"FYERS_PIN set: {bool(os.getenv('FYERS_PIN'))}")
        print()

        if not config.refresh_token:
            print("ERROR: No refresh_token stored. You need to do one manual OAuth login first.")
            print("After logging in, the refresh_token will be saved and future refreshes will be automatic.")
            sys.exit(1)

        # Check current token
        if config.access_token and not args.force:
            token_info = refresh_service.get_token_info(config.access_token)
            if not token_info.get('is_expired'):
                print(f"Current token still valid. Expires at: {token_info.get('expires_at')}")
                print(f"Time until expiry: {token_info.get('time_until_expiry')}")
                print("Use --force to refresh anyway.")
                sys.exit(0)

        print("Attempting API-based token refresh...")
        result = refresh_service.refresh_fyers_token(args.user_id, config.refresh_token)

        if result:
            print(f"\nSUCCESS! Token refreshed at {result.get('refreshed_at')}")
            print(f"New access_token: {result['access_token'][:20]}...")
            print(f"New refresh_token: {result.get('refresh_token', 'unchanged')[:20]}...")
        else:
            print("\nFAILED! Check logs for details.")
            print("You may need to do a manual OAuth login to get a fresh refresh_token.")
            sys.exit(1)


if __name__ == '__main__':
    main()
