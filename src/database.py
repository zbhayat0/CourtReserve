import deta

from threading import RLock

from .logger import Logger

from datetime import datetime


class Reservation:
    def __init__(self, date: datetime, created_at: datetime = None, key: str = None):
        if isinstance(date, str):
            date = datetime.fromisoformat(date)

        if date.tzinfo is None or date.tzname() is None:
            raise ValueError("Date must have a timezone")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        self.date = date
        self.created_at = created_at or datetime.now()
        self.key = key

    def __repr__(self):
        return f"Reservation(date={self.date}, created_at={self.created_at})"

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "created_at": self.created_at.isoformat(),
        }
    

class Database:
    def __init__(self):
        self.deta = deta.Deta("c0ohpvveq8j_eRdsBCee8K9nNZ5EeiWw4DTkHXM4QkXp")
        self.base = self.deta.Base("courtreserve-key")
        self.logger = Logger('database')
        self.lock = RLock()


    def _get(self, date):
        if isinstance(date, datetime):
            date = date.isoformat()

        res = self.base.fetch({"date": date}).items
        if res:
            # assuming there is only one reservation per date; should be secured by the add logic
            return Reservation(key=res[0]["key"], date=res[0]["date"], created_at=res[0]["created_at"])

    def _add(self, reservation: Reservation):
        try:
            return self.base.insert(reservation.to_dict())
        except Exception as e:
            self.logger.error(f"Error adding reservation: {e}")
            return False

    def get(self, date, key=None):
        with self.lock:
            if key:
                return self.base.get(key)
            
            return self._get(date)
    
    def add(self, reservation: Reservation):
        # base.insert throws an error if the key already exists
        with self.lock:
            return self._add(reservation)

    def delete(self, obj: datetime|Reservation):
        resrv = obj
        if isinstance(obj, datetime):
            resrv = self.get(obj)

        elif isinstance(obj, Reservation):
            if not obj.key:
                resrv = self.get(obj.date)

        if resrv and resrv.key:
            with self.lock:
                self.base.delete(resrv.key)

    def all(self):
        with self.lock:
            items = self.base.fetch().items
        return [Reservation(key=res["key"], date=res["date"], created_at=res["created_at"]) for res in items]


db = Database()
