"""
Database models for restaurant table reservations.
Uses SQLAlchemy ORM with SQLite backend.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()


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


class DatabaseManager:
    """
    Manager class for database operations.
    """
    _instance = None
    _engine = None
    _Session = None

    @classmethod
    def get_instance(cls, database_url: str = None):
        """Get or create singleton database manager instance."""
        if cls._instance is None:
            cls._instance = cls(database_url)
        return cls._instance

    def __init__(self, database_url: str = None):
        """Initialize database connection."""
        if database_url is None:
            database_url = os.getenv('DATABASE_URL', 'sqlite:///restaurant_bookings.db')
        
        self._engine = create_engine(database_url, echo=False)
        self._Session = sessionmaker(bind=self._engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(self._engine)

    def get_session(self):
        """Get a new database session."""
        return self._Session()

    def create_reservation(
        self,
        user_id: str,
        user_name: str,
        phone_number: str,
        number_of_guests: int,
        date_time: datetime,
        time_created: datetime,
        time_slot: float = 2.0
    ) -> Reservation:
        """Create a new reservation."""
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
