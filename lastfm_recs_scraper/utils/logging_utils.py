import logging
import time
from typing import Optional

# TODO: add sensitive data filtering for api creds: https://dev.to/camillehe1992/mask-sensitive-data-using-python-built-in-logging-module-45fa

# For custom color output of logging library: https://stackoverflow.com/a/56944256
class CustomLoggingFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "[%(asctime)s] %(levelname)s: %(message)s"
    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%m/%d/%Y %H:%M:%S")
        formatter.converter = time.gmtime
        return formatter.format(record)


# create console handler with a higher log level 
# For custom color output of logging library: https://stackoverflow.com/a/56944256
def get_custom_logger(src: str, log_level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(src)
    logger.setLevel(log_level)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(CustomLoggingFormatter())
    logger.addHandler(ch)
    return logger
