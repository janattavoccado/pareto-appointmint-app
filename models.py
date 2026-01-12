"""
Database models for restaurant table reservations.
Uses SQLAlchemy ORM with support for SQLite (local) and PostgreSQL (Heroku).

Version 3.1: Added SessionState model for multi-worker session persistence.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import threading
import logging

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
            
            if 'reservations' not in existing_tables or 'session_states' not in existing_tables:
                # Tables don't exist, create them
                Base.metadata.create_all(self._engine)
                print("Database tables created successfully")
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
