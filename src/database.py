from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from src.logger import Logger
from datetime import datetime
from threading import RLock, Thread

import os
import json

Base = declarative_base()

class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    court_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acc = Column(String, nullable=True)

    def __init__(self, date: datetime, court_id: str, created_at: datetime = None, acc: str = None):
        if isinstance(date, str):
            date = datetime.fromisoformat(date)

        if date.tzinfo is None or date.tzname() is None:
            raise ValueError("Date must have a timezone")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        self.date = date
        self.court_id = court_id
        self.created_at = created_at or datetime.utcnow()
        self.acc = acc

    def __repr__(self):
        return f"Reservation(date={self.date}, court_id={self.court_id}, created_at={self.created_at}, acc={self.acc})"

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "court_id": self.court_id,
            "created_at": self.created_at.isoformat(),
            "acc": self.acc
        }

    @staticmethod
    def get(id: int) -> "Reservation":
        with db.session() as session:
            return session.query(Reservation).filter_by(id=id).first()

    @staticmethod
    def add(reservation: "Reservation"):
        with db.session() as session:
            existing_res = session.query(Reservation).filter(
                Reservation.date == reservation.date,
                Reservation.court_id == reservation.court_id
            ).first()
            if existing_res:
                return False
            session.add(reservation)
            return True

    @staticmethod
    def all() -> list["Reservation"]:
        with db.session() as session:
            return session.query(Reservation).all()
        
    @staticmethod
    def delete(reservation: "Reservation"):
        with db.session() as session:
            if reservation.id:
                session.query(Reservation).filter_by(id=reservation.id).delete()
            else:
                session.query(Reservation).filter(
                    Reservation.date == reservation.date,
                    Reservation.court_id == reservation.court_id,
                    Reservation.acc == reservation.acc
                ).delete()

class CredStates(Base):
    zafar = {
        'ReturnUrl': '',
        'Origin': '',
        'PageId': '',
        'Username': 'zbhayat0@gmail.com',
        'Password': 'Password123!',
        'RememberMe': 'false'
    }
    mike = {
        'ReturnUrl': '',
        'Origin': '',
        'PageId': '',
        'Username': 'michaelbuffolino1@gmail.com',
        'Password': 'ColinMikey20',
        'RememberMe': 'false'
    }

    __tablename__ = 'cred_states'

    id = Column(Integer, primary_key=True, autoincrement=True)
    acc = Column(String, nullable=False)
    data = Column(JSON, nullable=True)
    age = Column(DateTime, nullable=False, default=datetime.now)

    def __init__(self, acc: str, data: dict, age: datetime = None):
        self.acc = acc
        self.data = data
        self.age = age or datetime.now()

    def __repr__(self):
        return f"CredStates(acc={self.acc}, age={self.age})"
    
    @staticmethod
    def get(acc):
        with db.session() as session:
            data = session.query(CredStates).filter_by(acc=acc).first()
        if getattr(data, "age", None) and (datetime.now() - data.age).days <= 4:
            return data
    
    @staticmethod
    def update(acc, data: dict):
        with db.session() as session:
            obj = session.query(CredStates).filter_by(acc=acc).first()
            
            if obj:
                obj.data = data
                obj.age = datetime.now()

def load_credentials(acc):
    # Try to load from environment variable first
    creds_json = os.getenv('CREDS')
    if creds_json:
        try:
            creds = json.loads(creds_json)
            return creds.get(acc, {})
        except:
            pass
    
    # Fallback to file if environment variable is not set
    with open(f"creds/{acc}.json") as f:
        return json.load(f)

class Database:
    def __init__(self, uri="sqlite:///data/database.db"):
        os.makedirs("data", exist_ok=True)
        self.engine = create_engine(uri, pool_size=50, max_overflow=15)
        self.SessionMaker = sessionmaker(bind=self.engine, expire_on_commit=False, autocommit=False, autoflush=False)

        self.logger = Logger('database')
        self.lock = RLock()

    @contextmanager
    def session(self):
        """
        Creates a context with an open SQLAlchemy session.
        """
        try:
            session: Session = scoped_session(self.SessionMaker)
            yield session
            session.commit()
        except Exception as _e:
            from traceback import format_exc
            self.logger.error(f"Database error: {format_exc()}")
            session.rollback()
        finally:
            session.close()

    def create_database(self):
        Base.metadata.create_all(self.engine)


db = Database()
db.create_database()
