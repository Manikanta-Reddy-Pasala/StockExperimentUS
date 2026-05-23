"""
Database Manager for the Automated Trading System
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
import os


class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: str = None):
        """
        Initialize the database manager.
        
        Args:
            database_url (str, optional): Database connection URL
        """
        # First check if DATABASE_URL environment variable is set
        env_database_url = os.environ.get('DATABASE_URL')
        if env_database_url:
            database_url = env_database_url
        elif database_url is None:
            # Default to PostgreSQL with localhost if no environment variable
            database_url = 'postgresql://trader:trader_password@localhost:5432/trading_system'
        
        self.engine = create_engine(database_url, echo=False)
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)
    
    def create_tables(self):
        """Create all tables defined in the models."""
        from .models import Base
        Base.metadata.create_all(self.engine)
    
    def drop_tables(self):
        """Drop all tables."""
        from .models import Base
        Base.metadata.drop_all(self.engine)
    
    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions.
        
        Yields:
            Session: Database session
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Global database manager instance
db_manager = None


def get_database_manager(database_url: str = None) -> DatabaseManager:
    """
    Get the global database manager instance.
    
    Args:
        database_url (str, optional): Database connection URL
        
    Returns:
        DatabaseManager: Database manager instance
    """
    global db_manager
    # Always check for DATABASE_URL environment variable first
    env_database_url = os.environ.get('DATABASE_URL')
    if env_database_url:
        database_url = env_database_url
    
    if db_manager is None:
        db_manager = DatabaseManager(database_url)
    return db_manager