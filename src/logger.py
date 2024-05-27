import logging.handlers
import os
from telebot import TeleBot

import rich.logging


class Logger:
    def __init__(self, logging_service, max_size=int(3e6)):
        self.logger = logging.getLogger(f"{logging_service}_logger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        if os.path.exists("logs") is False: 
            os.mkdir("logs")
        
        fh = logging.handlers.RotatingFileHandler(f"logs/{logging_service}.log", maxBytes=max_size, backupCount=5)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        # logging to console
        sh = rich.logging.RichHandler(markup=False, rich_tracebacks=True)
        sh.setLevel(logging.INFO)
        self.logger.addHandler(sh)

    def _log(self, message, level="info", notification=True, **kwargs):
        if level in ["info", "warning", "error", "debug"]:
            getattr(self.logger, level)(message)

        if notification:
            TeleBot("7021449655:AAGt6LG48rqtV6nCefane06878wJLYynCvk").send_message(942683545, message, parse_mode="HTML")

    def info(self, message, notification=False, **kwargs):
        self._log(message, "info", notification,**kwargs)

    def warning(self, message, notification=True, **kwargs):
        self._log(message, "warning", notification,**kwargs)

    def error(self, message, notification=True, **kwargs):
        self._log(message, "error", notification,**kwargs)

    def debug(self, message, notification=True, **kwargs):
        self._log(message, "debug", notification,**kwargs)
