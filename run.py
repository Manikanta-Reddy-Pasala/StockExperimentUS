#!/usr/bin/env python3
"""
Application Runner Script
"""
import argparse
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import main as trading_system_main


def main():
    """Main entry point for the application runner."""
    parser = argparse.ArgumentParser(description='Automated Trading System Runner')
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
    
    # Run the main trading system
    try:
        # Pass the arguments to the main function
        import src.main
        # Create a mock args object to pass to main
        class MockArgs:
            def __init__(self, multi_user=True, dev=False):
                self.multi_user = multi_user
                self.dev = dev
        
        # Create args object with parsed values
        mock_args = MockArgs(
            multi_user=args.multi_user and not args.single_user,
            dev=args.dev
        )
        
        # Temporarily replace sys.argv to pass args to main
        original_argv = sys.argv
        sys.argv = ['run.py']
        if mock_args.multi_user:
            sys.argv.append('--multi-user')
        if mock_args.dev:
            sys.argv.append('--dev')
            
        src.main.main()
        
        # Restore original argv
        sys.argv = original_argv
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
    except Exception as e:
        print(f"Error running application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()