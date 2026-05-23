#!/usr/bin/env python3
"""
Main Trading System Entry Point
"""
import argparse
import sys
import os

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Try relative imports first (for normal usage when run as module)
    from .web.app import create_app
    from config import DEBUG, HOST, PORT
except ImportError:
    # Fall back to absolute imports (for direct execution)
    import sys
    import os
    # Add parent directory to path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.web.app import create_app
    from config import DEBUG, HOST, PORT

def main():
    """Main entry point for the trading system."""
    parser = argparse.ArgumentParser(description='Automated Trading System')
    parser.add_argument(
        '--multi-user',
        action='store_true',
        default=True,
        help='Enable multi-user mode (default: True)'
    )
    parser.add_argument(
        '--single-user',
        action='store_true',
        help='Disable multi-user mode (use single-user mode)'
    )
    parser.add_argument(
        '--dev',
        action='store_true',
        help='Enable development mode with auto-reloading'
    )
    
    args = parser.parse_args()
    
    try:
        # Create and run the Flask app
        app = create_app()
        
        print(f"🚀 Starting Trading System")
        print(f"📍 Host: {HOST}")
        print(f"🔌 Port: {PORT}")
        print(f"🐛 Debug: {DEBUG}")
        print(f"👥 Multi-user: {args.multi_user and not args.single_user}")
        print(f"🔧 Dev mode: {args.dev}")
        print("=" * 50)
        
        app.run(
            debug=DEBUG or args.dev,
            host=HOST,
            port=PORT
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Trading System stopped by user.")
    except Exception as e:
        print(f"❌ Error running trading system: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
