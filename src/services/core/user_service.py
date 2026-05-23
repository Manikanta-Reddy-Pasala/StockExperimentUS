"""
Service for user management and authentication.
"""
from datetime import datetime
from src.models.database import get_database_manager
from src.models.models import User

class UserService:
    def __init__(self, db_manager, bcrypt):
        self.db_manager = db_manager
        self.bcrypt = bcrypt

    def register_user(self, username, email, password):
        """Registers a new user."""
        with self.db_manager.get_session() as db_session:
            existing_user = db_session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            if existing_user:
                if existing_user.username == username:
                    raise ValueError('Username already exists.')
                else:
                    raise ValueError('Email already registered.')

            password_hash = self.bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                is_active=True,
                is_admin=False,
                created_at=datetime.now()
            )
            db_session.add(new_user)
            db_session.commit()
            # Refresh the user object to ensure all attributes are loaded
            db_session.refresh(new_user)
            # Detach the user from the session to avoid DetachedInstanceError
            db_session.expunge(new_user)
            return new_user

    def login_user(self, username, password):
        """Authenticates a user."""
        with self.db_manager.get_session() as db_session:
            user = db_session.query(User).filter_by(username=username).first()
            if user and self.bcrypt.check_password_hash(user.password_hash, password):
                if user.is_active:
                    user.last_login = datetime.utcnow()
                    db_session.commit()
                    # Refresh the user object to ensure all attributes are loaded
                    db_session.refresh(user)
                    # Detach the user from the session to avoid DetachedInstanceError
                    db_session.expunge(user)
                    return user
                else:
                    raise ValueError('Your account has been deactivated.')
            else:
                raise ValueError('Invalid username or password.')

    def get_all_users(self):
        """Gets all users for admin management."""
        with self.db_manager.get_session() as session:
            users = session.query(User).all()
            return [{
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            } for user in users]

    def create_user(self, data):
        """Creates a new user by an admin."""
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not all([username, email, password]):
            raise ValueError('Username, email, and password are required')

        with self.db_manager.get_session() as session:
            existing_user = session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            if existing_user:
                raise ValueError('Username or email already exists')

            password_hash = self.bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                is_active=True,
                is_admin=data.get('is_admin', False),
                created_at=datetime.now()
            )
            session.add(new_user)
            session.commit()
            return {
                'id': new_user.id,
                'username': new_user.username,
                'email': new_user.email,
                'first_name': new_user.first_name,
                'last_name': new_user.last_name,
                'is_active': new_user.is_active,
                'is_admin': new_user.is_admin
            }

    def update_user(self, user_id, data):
        """Updates a user."""
        with self.db_manager.get_session() as session:
            user = session.query(User).get(user_id)
            if not user:
                raise ValueError('User not found')

            if 'username' in data:
                user.username = data['username']
            if 'email' in data:
                user.email = data['email']
            if 'first_name' in data:
                user.first_name = data['first_name']
            if 'last_name' in data:
                user.last_name = data['last_name']
            if 'is_active' in data:
                user.is_active = data['is_active']
            if 'is_admin' in data:
                user.is_admin = data['is_admin']
            if 'password' in data and data['password']:
                user.password_hash = self.bcrypt.generate_password_hash(data['password']).decode('utf-8')

            session.commit()
            return {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'is_admin': user.is_admin
            }

    def delete_user(self, user_id_to_delete, current_user_id):
        """Deletes a user."""
        if user_id_to_delete == current_user_id:
            raise ValueError('Cannot delete your own account')

        with self.db_manager.get_session() as session:
            user = session.query(User).get(user_id_to_delete)
            if not user:
                raise ValueError('User not found')

            session.delete(user)
            session.commit()
            return True
    
    def get_or_create_demo_user(self):
        """Gets or creates a demo user for demonstration purposes."""
        demo_username = 'demo_user'
        demo_email = 'demo@trading-system.com'
        demo_password = 'demo123'
        
        try:
            with self.db_manager.get_session() as session:
                # Try to find existing demo user
                demo_user = session.query(User).filter_by(username=demo_username).first()
                
                if demo_user:
                    # Update last login and return existing user
                    demo_user.last_login = datetime.utcnow()
                    session.commit()
                    session.refresh(demo_user)
                    session.expunge(demo_user)
                    return demo_user
                
                # Create new demo user
                password_hash = self.bcrypt.generate_password_hash(demo_password).decode('utf-8')
                new_demo_user = User(
                    username=demo_username,
                    email=demo_email,
                    password_hash=password_hash,
                    first_name='Demo',
                    last_name='User',
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.now(),
                    last_login=datetime.utcnow()
                )
                session.add(new_demo_user)
                session.commit()
                session.refresh(new_demo_user)
                session.expunge(new_demo_user)
                return new_demo_user
                
        except Exception as e:
            # If there's any error, return None to fall back to demo mode
            print(f"Error creating/getting demo user: {e}")
            return None

_user_service = None

def get_user_service(db_manager=None, bcrypt=None):
    """Singleton factory for UserService."""
    global _user_service
    if _user_service is None:
        if db_manager is None or bcrypt is None:
            raise ValueError("db_manager and bcrypt must be provided for the first call")
        _user_service = UserService(db_manager, bcrypt)
    return _user_service
