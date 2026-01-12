"""
Database models for restaurant table reservations.
Uses SQLAlchemy ORM with support for SQLite (local) and PostgreSQL (Heroku).

Version 4.0: Added AdminUser model for database-based authentication.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import threading
import logging
import hashlib
import secrets

Base = declarative_base()

# Lock for thread-safe database initialization
_db_init_lock = threading.Lock()

# Configure logging
logger = logging.getLogger(__name__)


class Reservation(Base):
    """
    Model for storing restaurant table reservations.
    """
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    user_name = Column(String(200), nullable=False)
    phone_number = Column(String(50), nullable=False)
    number_of_guests = Column(Integer, nullable=False)
    date_time = Column(DateTime, nullable=False)
    time_slot = Column(Float, default=2.0)  # Default 2 hours
    time_created = Column(DateTime, nullable=False)
    status = Column(String(50), default='confirmed')  # confirmed, cancelled, completed

    def __repr__(self):
        return f"<Reservation(id={self.id}, user_name='{self.user_name}', date_time='{self.date_time}')>"

    def to_dict(self):
        """Convert reservation to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'phone_number': self.phone_number,
            'number_of_guests': self.number_of_guests,
            'date_time': self.date_time.strftime('%Y-%m-%d %H:%M') if self.date_time else None,
            'time_slot': self.time_slot,
            'time_created': self.time_created.strftime('%Y-%m-%d %H:%M:%S') if self.time_created else None,
            'status': self.status
        }


class SessionState(Base):
    """
    Model for storing conversation session state.
    Enables multi-worker support by persisting state in the database.
    """
    __tablename__ = 'session_states'

    user_id = Column(String(255), primary_key=True)
    state_json = Column(Text, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SessionState(user_id='{self.user_id}', last_updated='{self.last_updated}')>"


class AdminUser(Base):
    """
    Model for storing admin users with secure password hashing.
    """
    __tablename__ = 'admin_users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    full_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username='{self.username}')>"

    def set_password(self, password: str):
        """Hash and set the password with a random salt."""
        self.salt = secrets.token_hex(32)
        self.password_hash = self._hash_password(password, self.salt)

    def check_password(self, password: str) -> bool:
        """Verify the password against the stored hash."""
        return self.password_hash == self._hash_password(password, self.salt)

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Create a secure hash of the password with salt."""
        # Using SHA-256 with salt (consider using bcrypt for production)
        return hashlib.sha256((password + salt).encode()).hexdigest()

    def to_dict(self):
        """Convert admin user to dictionary (excluding sensitive fields)."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'is_active': self.is_active,
            'is_superadmin': self.is_superadmin,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else None
        }


def get_database_url():
    """
    Get the database URL from environment variables.
    Handles Heroku's DATABASE_URL format which uses 'postgres://' instead of 'postgresql://'.
    """
    database_url = os.getenv('DATABASE_URL')
    
    if database_url is None:
        # Default to SQLite for local development
        return 'sqlite:///restaurant_bookings.db'
    
    # Heroku uses 'postgres://' but SQLAlchemy 1.4+ requires 'postgresql://'
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url


class DatabaseManager:
    """
    Manager class for database operations.
    Supports both SQLite (local development) and PostgreSQL (Heroku production).
    """
    _instance = None
    _engine = None
    _Session = None
    _initialized = False

    @classmethod
    def get_instance(cls, database_url: str = None):
        """Get or create singleton database manager instance."""
        with _db_init_lock:
            if cls._instance is None:
                cls._instance = cls(database_url)
            return cls._instance

    def __init__(self, database_url: str = None):
        """Initialize database connection."""
        if database_url is None:
            database_url = get_database_url()
        
        # Configure engine based on database type
        if database_url.startswith('sqlite'):
            # SQLite configuration
            self._engine = create_engine(
                database_url,
                echo=False,
                connect_args={'check_same_thread': False}
            )
        else:
            # PostgreSQL configuration
            self._engine = create_engine(
                database_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True  # Verify connections before using
            )
        
        self._Session = sessionmaker(bind=self._engine)
        
        # Create tables if they don't exist (with error handling for race conditions)
        self._create_tables_safe()
        
        db_type = 'PostgreSQL' if 'postgresql' in database_url else 'SQLite'
        print(f"Database initialized: {db_type}")

    def _create_tables_safe(self):
        """
        Safely create tables, handling race conditions when multiple workers start.
        """
        try:
            # Check if tables already exist
            inspector = inspect(self._engine)
            existing_tables = inspector.get_table_names()
            
            tables_needed = ['reservations', 'session_states', 'admin_users']
            missing_tables = [t for t in tables_needed if t not in existing_tables]
            
            if missing_tables:
                # Tables don't exist, create them
                Base.metadata.create_all(self._engine)
                print(f"Database tables created: {missing_tables}")
                
                # Create default admin user if admin_users table was just created
                if 'admin_users' in missing_tables:
                    self._create_default_admin()
            else:
                print("Database tables already exist")
        except Exception as e:
            # If there's a race condition error, tables were likely created by another worker
            error_str = str(e).lower()
            if 'already exists' in error_str or 'duplicate' in error_str:
                print("Database tables already exist (created by another worker)")
            else:
                # Re-raise unexpected errors
                raise e

    def _create_default_admin(self):
        """Create a default admin user if none exists."""
        session = self.get_session()
        try:
            existing = session.query(AdminUser).first()
            if not existing:
                admin = AdminUser(
                    username='admin',
                    email='admin@restaurant.com',
                    full_name='Default Administrator',
                    is_active=True,
                    is_superadmin=True
                )
                admin.set_password('admin123')  # Default password - CHANGE THIS!
                session.add(admin)
                session.commit()
                print("Default admin user created (username: admin, password: admin123)")
                print("WARNING: Please change the default admin password immediately!")
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating default admin: {e}")
        finally:
            session.close()

    def get_session(self):
        """Get a new database session."""
        return self._Session()

    # =========================================================================
    # Reservation Methods
    # =========================================================================

    def create_reservation(
        self,
        user_id: str,
        user_name: str,
        phone_number: str,
        number_of_guests: int,
        date_time: datetime,
        time_created: datetime = None,
        time_slot: float = 2.0
    ) -> Reservation:
        """Create a new reservation."""
        if time_created is None:
            time_created = datetime.utcnow()
        
        session = self.get_session()
        try:
            reservation = Reservation(
                user_id=user_id,
                user_name=user_name,
                phone_number=phone_number,
                number_of_guests=number_of_guests,
                date_time=date_time,
                time_slot=time_slot,
                time_created=time_created,
                status='confirmed'
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_reservation_by_id(self, reservation_id: int) -> Reservation:
        """Get reservation by ID."""
        session = self.get_session()
        try:
            return session.query(Reservation).filter(Reservation.id == reservation_id).first()
        finally:
            session.close()

    def get_reservations_by_user(self, user_id: str) -> list:
        """Get all reservations for a user."""
        session = self.get_session()
        try:
            return session.query(Reservation).filter(
                Reservation.user_id == user_id,
                Reservation.status != 'cancelled'
            ).order_by(Reservation.date_time.desc()).all()
        finally:
            session.close()

    def get_reservations_by_date(self, date: datetime) -> list:
        """Get all reservations for a specific date."""
        session = self.get_session()
        try:
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            return session.query(Reservation).filter(
                Reservation.date_time >= start_of_day,
                Reservation.date_time <= end_of_day,
                Reservation.status == 'confirmed'
            ).order_by(Reservation.date_time).all()
        finally:
            session.close()

    def cancel_reservation(self, reservation_id: int) -> bool:
        """Cancel a reservation by ID."""
        session = self.get_session()
        try:
            reservation = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if reservation:
                reservation.status = 'cancelled'
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_reservation(
        self,
        reservation_id: int,
        **kwargs
    ) -> Reservation:
        """Update a reservation."""
        session = self.get_session()
        try:
            reservation = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if reservation:
                for key, value in kwargs.items():
                    if hasattr(reservation, key) and value is not None:
                        setattr(reservation, key, value)
                session.commit()
                session.refresh(reservation)
                return reservation
            return None
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_all_reservations(self, include_cancelled: bool = False) -> list:
        """Get all reservations."""
        session = self.get_session()
        try:
            query = session.query(Reservation)
            if not include_cancelled:
                query = query.filter(Reservation.status != 'cancelled')
            return query.order_by(Reservation.date_time.desc()).all()
        finally:
            session.close()

    # =========================================================================
    # Session State Methods (for multi-worker support)
    # =========================================================================

    def get_session_state(self, user_id: str) -> str:
        """Get session state JSON for a user."""
        session = self.get_session()
        try:
            state = session.query(SessionState).filter(SessionState.user_id == user_id).first()
            return state.state_json if state else None
        except Exception as e:
            logger.error(f"Error getting session state: {e}")
            return None
        finally:
            session.close()

    def save_session_state(self, user_id: str, state_json: str) -> bool:
        """Save session state JSON for a user."""
        session = self.get_session()
        try:
            existing = session.query(SessionState).filter(SessionState.user_id == user_id).first()
            if existing:
                existing.state_json = state_json
                existing.last_updated = datetime.utcnow()
            else:
                new_state = SessionState(
                    user_id=user_id,
                    state_json=state_json,
                    last_updated=datetime.utcnow()
                )
                session.add(new_state)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving session state: {e}")
            return False
        finally:
            session.close()

    def delete_session_state(self, user_id: str) -> bool:
        """Delete session state for a user."""
        session = self.get_session()
        try:
            session.query(SessionState).filter(SessionState.user_id == user_id).delete()
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting session state: {e}")
            return False
        finally:
            session.close()

    def cleanup_old_sessions(self, hours: int = 24) -> int:
        """Delete session states older than specified hours."""
        from datetime import timedelta
        session = self.get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            deleted = session.query(SessionState).filter(SessionState.last_updated < cutoff).delete()
            session.commit()
            return deleted
        except Exception as e:
            session.rollback()
            logger.error(f"Error cleaning up old sessions: {e}")
            return 0
        finally:
            session.close()

    # =========================================================================
    # Admin User Methods
    # =========================================================================

    def authenticate_admin(self, username: str, password: str) -> AdminUser:
        """Authenticate an admin user and return the user if successful."""
        session = self.get_session()
        try:
            admin = session.query(AdminUser).filter(
                AdminUser.username == username,
                AdminUser.is_active == True
            ).first()
            
            if admin and admin.check_password(password):
                # Update last login time
                admin.last_login = datetime.utcnow()
                session.commit()
                session.refresh(admin)
                return admin
            return None
        except Exception as e:
            session.rollback()
            logger.error(f"Error authenticating admin: {e}")
            return None
        finally:
            session.close()

    def get_admin_by_id(self, admin_id: int) -> AdminUser:
        """Get admin user by ID."""
        session = self.get_session()
        try:
            return session.query(AdminUser).filter(AdminUser.id == admin_id).first()
        finally:
            session.close()

    def get_admin_by_username(self, username: str) -> AdminUser:
        """Get admin user by username."""
        session = self.get_session()
        try:
            return session.query(AdminUser).filter(AdminUser.username == username).first()
        finally:
            session.close()

    def get_all_admins(self) -> list:
        """Get all admin users."""
        session = self.get_session()
        try:
            return session.query(AdminUser).order_by(AdminUser.created_at.desc()).all()
        finally:
            session.close()

    def create_admin(
        self,
        username: str,
        password: str,
        email: str = None,
        full_name: str = None,
        is_superadmin: bool = False
    ) -> AdminUser:
        """Create a new admin user."""
        session = self.get_session()
        try:
            # Check if username already exists
            existing = session.query(AdminUser).filter(AdminUser.username == username).first()
            if existing:
                raise ValueError(f"Username '{username}' already exists")
            
            admin = AdminUser(
                username=username,
                email=email,
                full_name=full_name,
                is_active=True,
                is_superadmin=is_superadmin
            )
            admin.set_password(password)
            session.add(admin)
            session.commit()
            session.refresh(admin)
            return admin
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_admin(self, admin_id: int, **kwargs) -> AdminUser:
        """Update an admin user."""
        session = self.get_session()
        try:
            admin = session.query(AdminUser).filter(AdminUser.id == admin_id).first()
            if admin:
                # Handle password separately
                if 'password' in kwargs and kwargs['password']:
                    admin.set_password(kwargs.pop('password'))
                elif 'password' in kwargs:
                    kwargs.pop('password')  # Remove empty password
                
                for key, value in kwargs.items():
                    if hasattr(admin, key) and value is not None:
                        setattr(admin, key, value)
                session.commit()
                session.refresh(admin)
                return admin
            return None
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def delete_admin(self, admin_id: int) -> bool:
        """Delete an admin user."""
        session = self.get_session()
        try:
            admin = session.query(AdminUser).filter(AdminUser.id == admin_id).first()
            if admin:
                # Prevent deleting the last superadmin
                if admin.is_superadmin:
                    superadmin_count = session.query(AdminUser).filter(
                        AdminUser.is_superadmin == True,
                        AdminUser.is_active == True
                    ).count()
                    if superadmin_count <= 1:
                        raise ValueError("Cannot delete the last superadmin")
                
                session.delete(admin)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def change_admin_password(self, admin_id: int, new_password: str) -> bool:
        """Change an admin user's password."""
        session = self.get_session()
        try:
            admin = session.query(AdminUser).filter(AdminUser.id == admin_id).first()
            if admin:
                admin.set_password(new_password)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error changing admin password: {e}")
            return False
        finally:
            session.close()
