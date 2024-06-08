from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from src.database import db
from src.logger import Logger
from src.courtreserve import ReserveBot
from src.config import START_HOUR
from traceback import format_exc
from time import sleep
from telebot import TeleBot
from pytz import timezone


class Worker:
    def __init__(self, bot: TeleBot, logger: Logger):
        self.bot = bot
        self.logger = logger

        self.zone = timezone("UTC")
        if (now:=datetime.now(tz=self.zone)).hour < START_HOUR:
            # minus 1 hour because we want to run the worker slightly before the actual time (minutes are 59)
            self.next_run = now.replace(hour=START_HOUR-1, minute=59, second=30, microsecond=0)
        else:
            self.next_run = now.replace(hour=START_HOUR-1, minute=59, second=30, microsecond=0) + timedelta(days=1)


    def _worker(self):
        now = datetime.now(tz=self.zone)
        active_resbot = {}

        reservations = db.all()
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix="account-wise") as executor:
            for reservation in reservations:
                bot_instance = active_resbot.get(reservation.acc, None)
                if bot_instance is None:
                    bot_instance = active_resbot[reservation.acc] = ReserveBot(reservation, self.logger, self.bot)
                executor.submit(bot_instance.reserve_worker, now)
            
        self.logger.info("reserver bot worker is done", True)
        

    def worker(self):
        try:
            self._worker()
        except Exception:
            self.logger.error(format_exc())


    def run(self, non_blocking=True):
        # run worker every day at 11:00:00 UTC; only once a day
        def _func():
            self.logger.info(f"Next run at {self.next_run} i.e. after {self.next_run - datetime.now(tz=self.zone)}", True)
            while True:
                if datetime.now(tz=self.zone) >= self.next_run:
                    self.logger.info("reserver bot worker is running...", True)
                    self.worker()
                    self.next_run = datetime.now(tz=self.zone).replace(hour=START_HOUR-1, minute=59, second=30, microsecond=0) + timedelta(days=1)
                    self.logger.info(f"Next run at {self.next_run}", True)

                sleep(0.01)
        
        if non_blocking:
            from threading import Thread
            Thread(target=_func, daemon=True, name="main-worker-thread").start()
        else:
            _func()



if __name__ == "__main__":
    logger = Logger("worker")
    bot = TeleBot("7021449655:AAGt6LG48rqtV6nCefane06878wJLYynCvk")

    worker = Worker(bot, logger)
    worker.run(False)
