"""
Configuration management for the trading system
"""
import os
from pathlib import Path
import logging

# Base paths
BASE_DIR = Path(__file__).parent
SRC_DIR = BASE_DIR / "src"
DATA_DIR = SRC_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"

# Database configuration (SQLite removed)
# Require PostgreSQL URL via env; provide sensible Postgres default
POSTGRES_URL = os.environ.get('POSTGRES_URL', 'postgresql://postgres:password@localhost/stockexperiment')
DATABASE_URL = os.environ.get('DATABASE_URL', POSTGRES_URL)

# Dragonfly configuration
DRAGONFLY_URL = os.environ.get('DRAGONFLY_URL', 'redis://localhost:6379/0')
DRAGONFLY_HOST = os.environ.get('DRAGONFLY_HOST', 'localhost')
DRAGONFLY_PORT = int(os.environ.get('DRAGONFLY_PORT', '6379'))
DRAGONFLY_DB = int(os.environ.get('DRAGONFLY_DB', '0'))
DRAGONFLY_PASSWORD = os.environ.get('DRAGONFLY_PASSWORD', None)

# Email configuration
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD', '')

# Trading configuration
DEFAULT_EXCHANGE = 'NSE'
DEFAULT_PRODUCT = 'CNC'
DEFAULT_ORDER_TYPE = 'MARKET'

# Risk management
MAX_POSITION_SIZE = float(os.environ.get('MAX_POSITION_SIZE', '100000'))
MAX_DAILY_LOSS = float(os.environ.get('MAX_DAILY_LOSS', '5000'))
STOP_LOSS_PERCENTAGE = float(os.environ.get('STOP_LOSS_PERCENTAGE', '2.0'))

# Logging configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Configure logging
logging_handlers = [logging.StreamHandler()]

# Try to add file handler if logs directory exists and is writable
if LOGS_DIR.exists():
    try:
        # Try to create a test file to check if the directory is writable
        test_file = LOGS_DIR / ".test_write_access"
        test_file.touch()
        test_file.unlink()
        
        # If we can write, add the file handler
        logging_handlers.append(logging.FileHandler(LOGS_DIR / "trading_system.log"))
    except (OSError, IOError) as e:
        # If we can't write to the logs directory, just use stream handler
        pass

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=logging_handlers
)

# Web configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '5001'))
