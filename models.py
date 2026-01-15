"""
Database models for restaurant table reservations.
Uses SQLAlchemy ORM with support for SQLite (local) and PostgreSQL (Heroku).

Version 4.0: Complete models with AdminUser, SessionState, UserMemory, and all methods.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
import threading
import logging

Base = declarative_base()

# Lock for thread-safe database initialization
_db_init_lock = threading.Lock()

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# Database Models
# ============================================================================

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
    status = Column(String(50), default='confirmed')  # pending, confirmed, arrived, seated, completed, cancelled, no_show
    special_requests = Column(Text, nullable=True)  # Special requests/notes
    table_number = Column(String(20), nullable=True)  # Assigned table

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
            'date': self.date_time.strftime('%Y-%m-%d') if self.date_time else None,
            'time': self.date_time.strftime('%H:%M') if self.date_time else None,
            'time_slot': self.time_slot,
            'time_created': self.time_created.strftime('%Y-%m-%d %H:%M:%S') if self.time_created else None,
            'status': self.status,
            'special_requests': self.special_requests,
            'table_number': self.table_number
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


class UserMemory(Base):
    """
    Model for storing user memory/preferences.
    Allows the booking agent to remember returning guests.
    """
    __tablename__ = 'user_memories'

    user_id = Column(String(255), primary_key=True)
    user_name = Column(String(200), nullable=True)
    phone_number = Column(String(50), nullable=True)
    preferences = Column(Text, nullable=True)  # JSON string of preferences
    last_visit = Column(DateTime, nullable=True)
    visit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UserMemory(user_id='{self.user_id}', user_name='{self.user_name}')>"

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'user_name': self.user_name,
            'phone_number': self.phone_number,
            'preferences': self.preferences,
            'last_visit': self.last_visit.isoformat() if self.last_visit else None,
            'visit_count': self.visit_count
        }


class AdminUser(Base):
    """
    Model for admin dashboard users.
    """
    __tablename__ = 'admin_users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    role = Column(String(50), default='admin')  # admin, superadmin, staff
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username='{self.username}', role='{self.role}')>"

    def set_password(self, password):
        """Hash and set the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if the provided password matches the hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


# ============================================================================
# Database URL Helper
# ============================================================================

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


# ============================================================================
# Database Manager
# ============================================================================

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
            
            required_tables = ['reservations', 'session_states', 'user_memories', 'admin_users']
            missing_tables = [t for t in required_tables if t not in existing_tables]
            
            if missing_tables:
                # Tables don't exist, create them
                Base.metadata.create_all(self._engine)
                print(f"Database tables created: {missing_tables}")
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
        time_slot: float = 2.0,
        special_requests: str = None
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
                status='confirmed',
                special_requests=special_requests
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
                Reservation.date_time <= end_of_day
            ).order_by(Reservation.date_time).all()
        finally:
            session.close()

    def get_reservations_by_date_range(self, start_date: datetime, end_date: datetime) -> list:
        """Get all reservations within a date range."""
        session = self.get_session()
        try:
            return session.query(Reservation).filter(
                Reservation.date_time >= start_date,
                Reservation.date_time <= end_date
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

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation:
        """Update reservation status."""
        return self.update_reservation(reservation_id, status=status)

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

    def get_upcoming_reservations(self, limit: int = 10) -> list:
        """Get upcoming reservations from now."""
        session = self.get_session()
        try:
            now = datetime.now()
            return session.query(Reservation).filter(
                Reservation.date_time >= now,
                Reservation.status.in_(['confirmed', 'pending'])
            ).order_by(Reservation.date_time).limit(limit).all()
        finally:
            session.close()

    def search_reservations(self, query: str) -> list:
        """Search reservations by name or phone number."""
        session = self.get_session()
        try:
            search_term = f"%{query}%"
            return session.query(Reservation).filter(
                (Reservation.user_name.ilike(search_term)) |
                (Reservation.phone_number.ilike(search_term))
            ).order_by(Reservation.date_time.desc()).all()
        finally:
            session.close()

    def get_reservation_stats(self, date: datetime = None) -> dict:
        """Get reservation statistics for a date (defaults to today)."""
        if date is None:
            date = datetime.now()
        
        session = self.get_session()
        try:
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            reservations = session.query(Reservation).filter(
                Reservation.date_time >= start_of_day,
                Reservation.date_time <= end_of_day
            ).all()
            
            stats = {
                'total': len(reservations),
                'pending': sum(1 for r in reservations if r.status == 'pending'),
                'confirmed': sum(1 for r in reservations if r.status == 'confirmed'),
                'arrived': sum(1 for r in reservations if r.status == 'arrived'),
                'seated': sum(1 for r in reservations if r.status == 'seated'),
                'completed': sum(1 for r in reservations if r.status == 'completed'),
                'cancelled': sum(1 for r in reservations if r.status == 'cancelled'),
                'no_show': sum(1 for r in reservations if r.status == 'no_show'),
                'total_guests': sum(r.number_of_guests for r in reservations if r.status not in ['cancelled', 'no_show'])
            }
            
            return stats
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
    # User Memory Methods
    # =========================================================================

    def get_user_memory(self, user_id: str) -> UserMemory:
        """Get user memory by user_id."""
        session = self.get_session()
        try:
            return session.query(UserMemory).filter(UserMemory.user_id == user_id).first()
        finally:
            session.close()

    def save_user_memory(self, user_id: str, user_name: str = None, phone_number: str = None, preferences: str = None) -> bool:
        """Save or update user memory."""
        session = self.get_session()
        try:
            existing = session.query(UserMemory).filter(UserMemory.user_id == user_id).first()
            if existing:
                if user_name:
                    existing.user_name = user_name
                if phone_number:
                    existing.phone_number = phone_number
                if preferences:
                    existing.preferences = preferences
                existing.updated_at = datetime.utcnow()
            else:
                new_memory = UserMemory(
                    user_id=user_id,
                    user_name=user_name,
                    phone_number=phone_number,
                    preferences=preferences
                )
                session.add(new_memory)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving user memory: {e}")
            return False
        finally:
            session.close()

    # =========================================================================
    # Admin User Methods
    # =========================================================================

    def get_admin_user_by_username(self, username: str) -> AdminUser:
        """Get admin user by username."""
        session = self.get_session()
        try:
            return session.query(AdminUser).filter(AdminUser.username == username).first()
        finally:
            session.close()

    def get_admin_user_by_id(self, user_id: int) -> AdminUser:
        """Get admin user by ID."""
        session = self.get_session()
        try:
            return session.query(AdminUser).filter(AdminUser.id == user_id).first()
        finally:
            session.close()

    def get_all_admin_users(self) -> list:
        """Get all admin users."""
        session = self.get_session()
        try:
            return session.query(AdminUser).order_by(AdminUser.created_at.desc()).all()
        finally:
            session.close()

    def create_admin_user(self, username: str, email: str, password: str, full_name: str = None, role: str = 'admin') -> AdminUser:
        """Create a new admin user."""
        session = self.get_session()
        try:
            user = AdminUser(
                username=username,
                email=email,
                full_name=full_name,
                role=role
            )
            user.set_password(password)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_admin_user(self, user_id: int, **kwargs) -> AdminUser:
        """Update an admin user."""
        session = self.get_session()
        try:
            user = session.query(AdminUser).filter(AdminUser.id == user_id).first()
            if user:
                for key, value in kwargs.items():
                    if key == 'password':
                        user.set_password(value)
                    elif hasattr(user, key) and value is not None:
                        setattr(user, key, value)
                session.commit()
                session.refresh(user)
                return user
            return None
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def delete_admin_user(self, user_id: int) -> bool:
        """Delete an admin user."""
        session = self.get_session()
        try:
            user = session.query(AdminUser).filter(AdminUser.id == user_id).first()
            if user:
                session.delete(user)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_admin_last_login(self, user_id: int) -> bool:
        """Update the last login timestamp for an admin user."""
        session = self.get_session()
        try:
            user = session.query(AdminUser).filter(AdminUser.id == user_id).first()
            if user:
                user.last_login = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            return False
        finally:
            session.close()

    def authenticate_admin(self, username: str, password: str) -> AdminUser:
        """Authenticate an admin user and return the user if successful."""
        session = self.get_session()
        try:
            user = session.query(AdminUser).filter(
                AdminUser.username == username,
                AdminUser.is_active == True
            ).first()
            if user and user.check_password(password):
                user.last_login = datetime.utcnow()
                session.commit()
                return user
            return None
        except Exception as e:
            session.rollback()
            return None
        finally:
            session.close()

    def create_default_admin(self) -> bool:
        """Create a default admin user if none exists."""
        session = self.get_session()
        try:
            existing = session.query(AdminUser).first()
            if not existing:
                admin = AdminUser(
                    username='admin',
                    email='admin@restaurant.com',
                    full_name='Administrator',
                    role='superadmin'
                )
                admin.set_password('admin123')
                session.add(admin)
                session.commit()
                logger.info("Default admin user created: admin / admin123")
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating default admin: {e}")
            return False
        finally:
            session.close()
