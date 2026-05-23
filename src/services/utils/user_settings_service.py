"""
User Settings Service
Handles user-specific settings storage and retrieval
"""
import json
from typing import Dict, Any, Optional
from src.models.database import DatabaseManager
from src.models.models import Configuration
from sqlalchemy.orm import sessionmaker


class UserSettingsService:
    """Service for managing user settings."""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get all settings for a user."""
        with self.db_manager.get_session() as db_session:
            # Get all configurations for the user
            configs = db_session.query(Configuration).filter(
                Configuration.user_id == user_id
            ).all()
            
            # Convert to dictionary
            settings = {}
            for config in configs:
                # Try to parse JSON values, fallback to string
                try:
                    settings[config.key] = json.loads(config.value) if config.value else None
                except (json.JSONDecodeError, TypeError):
                    settings[config.key] = config.value
            
            # Set defaults for missing settings
            default_settings = {
                'trading_mode': 'development',
                'max_capital_per_trade': 1.00,
                'stop_loss_percentage': 2.0,
                'take_profit_percentage': 5.0,
                'primary_data_source': 'fyers',
                'backup_data_source': 'fyers',
                'broker_provider': 'fyers',
                'email_notifications': True,
                'sms_notifications': False,
                'notification_email': 'trader@example.com'
            }
            
            # Merge with defaults
            for key, default_value in default_settings.items():
                if key not in settings:
                    settings[key] = default_value
            
            return settings
    
    def save_user_settings(self, user_id: int, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Save user settings to database."""
        with self.db_manager.get_session() as db_session:
            for key, value in settings.items():
                # Convert value to JSON string if it's not a string
                if isinstance(value, (dict, list, bool)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value) if value is not None else None
                
                # Check if configuration exists
                existing_config = db_session.query(Configuration).filter(
                    Configuration.user_id == user_id,
                    Configuration.key == key
                ).first()
                
                if existing_config:
                    # Update existing configuration
                    existing_config.value = value_str
                else:
                    # Create new configuration
                    new_config = Configuration(
                        user_id=user_id,
                        key=key,
                        value=value_str
                    )
                    db_session.add(new_config)
            
            db_session.commit()
            return self.get_user_settings(user_id)
    
    def get_broker_provider(self, user_id: int) -> str:
        """Get the broker provider for a user."""
        settings = self.get_user_settings(user_id)
        return settings.get('broker_provider', 'fyers')
    
    def set_broker_provider(self, user_id: int, broker_provider: str) -> bool:
        """Set the broker provider for a user."""
        try:
            settings = self.get_user_settings(user_id)
            settings['broker_provider'] = broker_provider
            self.save_user_settings(user_id, settings)
            return True
        except Exception:
            return False
    
    def get_setting(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get a specific setting for a user."""
        settings = self.get_user_settings(user_id)
        return settings.get(key, default)
    
    def set_setting(self, user_id: int, key: str, value: Any) -> bool:
        """Set a specific setting for a user."""
        try:
            settings = self.get_user_settings(user_id)
            settings[key] = value
            self.save_user_settings(user_id, settings)
            return True
        except Exception:
            return False


# Global instance
_user_settings_service = None

def get_user_settings_service() -> UserSettingsService:
    """Get the global user settings service instance."""
    global _user_settings_service
    if _user_settings_service is None:
        _user_settings_service = UserSettingsService()
    return _user_settings_service
