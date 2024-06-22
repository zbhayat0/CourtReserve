import deta

from threading import RLock, Thread

from .logger import Logger

from datetime import datetime
from time import time


class Reservation:
    def __init__(self, date: datetime, court_id: str, created_at: datetime = None, key: str = None, acc: str = None):
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
    

class Database:
    def __init__(self):
        self.deta = deta.Deta("c0ohpvveq8j_eRdsBCee8K9nNZ5EeiWw4DTkHXM4QkXp")
        self.base = self.deta.Base("courtreserve-key")
        self.base_age = time()

        self.logger = Logger('database')
        self.lock = RLock()

    def _base(self):
        if self.base_age + 5*60 < time():
            self.base_age = time()
            self.base = self.deta.Base("courtreserve-key")

    def _fetch(self, date: datetime, court_id: str, acc: str = ''):
        self._base()
        if isinstance(date, datetime):
            date = date.isoformat()

        if acc:
            res = self.base.fetch({"date": date, "court_id": court_id, "acc": acc}).items
        else:
            res = self.base.fetch({"date": date, "court_id": court_id}).items

        if res:
            # assuming there is only one reservation per date; should be secured by the add logic
            return Reservation(key=res[0]["key"], date=res[0]["date"], court_id=res[0]["court_id"], created_at=res[0]["created_at"])

    def _get(self, key: str):
        self._base()
        res = self.base.get(key)
        if res:
            return Reservation(key=res["key"], date=res["date"], court_id=res["court_id"], created_at=res["created_at"])

    def _add(self, reservation: Reservation):
        self._base()
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

    def fetch(self, date:datetime, court_id:str, acc: str):
        with self.lock:
            return self._fetch(date, court_id, acc)
    
    def add(self, reservation: Reservation):
        # base.insert throws an error if the key already exists
        with self.lock:
            return self._add(reservation)

    def _delete(self, obj: Reservation):
        self._base()
        if isinstance(obj, Reservation):
            if not obj.key:
                obj = self.fetch(obj.date, obj.court_id, obj.acc)

        if obj and obj.key:
            with self.lock:
                self.base.delete(obj.key)

    def delete(self, obj: Reservation):
        Thread(target=self._delete, args=(obj,), daemon=True).start()

    def all(self):
        self._base()
        with self.lock:
            items = self.base.fetch().items
        return [Reservation(**res) for res in items]


class Cred:
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
        'Password': 'Mjb743349$',
        'RememberMe': 'false'
    }
    def __init__(self):
        self.deta = deta.Deta("c0ohpvveq8j_eRdsBCee8K9nNZ5EeiWw4DTkHXM4QkXp")
        self.base = self.deta.Base("courtreserve-creds")

    def get(self, acc):
        data = self.base.get(acc)
        if data and (time() - data.get('age', 1e15)) < 5*24*60*60:
            try:
                del data['age']
            except:
                pass
            return data
    
    def add(self, data: dict, acc: str):
        data['age'] = time()
        return self.base.put(data, acc)


db = Database()
creds_manager = Cred()
