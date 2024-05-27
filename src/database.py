import deta

from threading import RLock

from .logger import Logger

from datetime import datetime


class Reservation:
    def __init__(self, date: datetime, court_id: str, created_at: datetime = None, key: str = None):
        if isinstance(date, str):
            date = datetime.fromisoformat(date)

        if date.tzinfo is None or date.tzname() is None:
            raise ValueError("Date must have a timezone")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        self.date = date
        self.court_id = court_id
        self.created_at = created_at or datetime.now()
        self.key = key

    def __repr__(self):
        return f"Reservation(date={self.date}, court_id={self.court_id}, created_at={self.created_at})"

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "court_id": self.court_id,
            "created_at": self.created_at.isoformat(),
        }
    

class Database:
    def __init__(self):
        self.deta = deta.Deta("c0ohpvveq8j_eRdsBCee8K9nNZ5EeiWw4DTkHXM4QkXp")
        self.base = self.deta.Base("courtreserve-key")
        self.logger = Logger('database')
        self.lock = RLock()

    def _fetch(self, date: datetime, court_id: str):
        if isinstance(date, datetime):
            date = date.isoformat()

        res = self.base.fetch({"date": date, "court_id": court_id}).items
        if res:
            # assuming there is only one reservation per date; should be secured by the add logic
            return Reservation(key=res[0]["key"], date=res[0]["date"], court_id=res[0]["court_id"], created_at=res[0]["created_at"])

    def _get(self, key: str):
        res = self.base.get(key)
        if res:
            return Reservation(key=res["key"], date=res["date"], court_id=res["court_id"], created_at=res["created_at"])

    def _add(self, reservation: Reservation):
        try:
            # although insert throws an error if the key already exists, we still check if the key exists
            # to avoid adding the same reservation twice

            res = self._fetch(reservation.date, reservation.court_id)
            if res:
                return False

            return self.base.insert(reservation.to_dict())
        except Exception as e:
            self.logger.error(f"Error adding reservation: {e}")
            return False

    def get(self, key: str):
        with self.lock:
            return self._get(key)

    def fetch(self, date:datetime, court_id:str):
        with self.lock:
            return self._fetch(date, court_id)
    
    def add(self, reservation: Reservation):
        # base.insert throws an error if the key already exists
        with self.lock:
            return self._add(reservation)

    def delete(self, obj: Reservation):
        if isinstance(obj, Reservation):
            if not obj.key:
                obj = self.fetch(obj.date)

        if obj and obj.key:
            with self.lock:
                self.base.delete(obj.key)

    def all(self):
        with self.lock:
            items = self.base.fetch().items
        return [Reservation(key=res["key"], date=res["date"], court_id=res["court_id"], created_at=res["created_at"]) for res in items]


db = Database()
