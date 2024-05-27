import functools
import traceback
from .logger import Logger

SUDO = [6874076639, 942683545]


def errorsWrapper(logger: Logger=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if args[0].from_user.id in SUDO:
                    return func(*args, **kwargs)

            except:
                err = str(traceback.format_exc()).replace("<", "&lt;").replace(">", "&gt;")
                if logger:
                    logger.error(err)
                else:
                    print(f"Error: {err}")
        return wrapper
    return decorator