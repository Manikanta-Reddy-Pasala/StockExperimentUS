"""
Logging Configuration for the Trading System

This module configures comprehensive logging for all API calls, services, and operations.
"""

import logging
import logging.config
import os
from datetime import datetime

def setup_logging():
    """Setup comprehensive logging configuration."""
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Logging configuration
    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            },
            'detailed': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            },
            'json': {
                'format': '%(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'detailed',
                'filename': os.path.join(log_dir, 'trading_system.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            },
            'api_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'INFO',
                'formatter': 'json',
                'filename': os.path.join(log_dir, 'api_calls.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            },
            'error_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'ERROR',
                'formatter': 'detailed',
                'filename': os.path.join(log_dir, 'errors.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False
            },
            'api_calls': {  # API calls logger - CONSOLE DISABLED
                'handlers': ['api_file'],  # Only log to file, not console
                'level': 'INFO',
                'propagate': False
            },
            'src': {  # All src modules
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': False
            },
            'src.services': {  # Services
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': False
            },
            'src.web': {  # Web routes
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': False
            },
            'src.services.brokers': {  # Broker services - CONSOLE WARNING ONLY
                'handlers': ['file'],  # Only log to file, not console
                'level': 'DEBUG',
                'propagate': False
            },
            'src.services.brokers.fyers.api': {  # Fyers API - CONSOLE DISABLED
                'handlers': ['file'],  # Only log to file, not console
                'level': 'DEBUG',
                'propagate': False
            },
            'src.services.core.broker_service': {  # Core broker service - CONSOLE DISABLED
                'handlers': ['file'],  # Only log to file, not console
                'level': 'DEBUG',
                'propagate': False
            },
            'src.services.portfolio.portfolio_service': {  # Portfolio service - CONSOLE DISABLED
                'handlers': ['file'],  # Only log to file, not console
                'level': 'DEBUG',
                'propagate': False
            },
            'src.services.ml': {  # ML services
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': False
            },
            'werkzeug': {  # Flask development server
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            },
            'urllib3': {  # HTTP requests
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            }
        }
    }
    
    # Apply configuration
    logging.config.dictConfig(logging_config)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized successfully")
    logger.info(f"Log files will be written to: {log_dir}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def log_api_summary():
    """Log a summary of API logging configuration."""
    logger = logging.getLogger('api_calls')
    logger.info("=" * 80)
    logger.info("API LOGGING CONFIGURATION SUMMARY")
    logger.info("=" * 80)
    logger.info("All API calls will be logged with the following information:")
    logger.info("- Request details (method, URL, headers, body)")
    logger.info("- Response details (status, data)")
    logger.info("- User ID and session information")
    logger.info("- Request/response timing")
    logger.info("- Error details with stack traces")
    logger.info("- Sensitive data will be redacted automatically")
    logger.info("=" * 80)
