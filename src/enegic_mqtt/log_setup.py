import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOG_FILE = os.getenv("ENEGIC_LOG_FILE", "/logs/enegic_mqtt.log")
_MAX_BYTES = int(os.getenv("ENEGIC_LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
_BACKUP_COUNT = int(os.getenv("ENEGIC_LOG_BACKUPS", "5"))
_LOG_LEVEL = os.getenv("ENEGIC_LOG_LEVEL", "INFO").upper()

_FMT = "%(asctime)s %(levelname)-8s %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("enegic_mqtt")
    if logger.handlers:
        return logger

    logger.setLevel(_LOG_LEVEL)
    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    try:
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        file_handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        logger.warning("Cannot open log file %s — logging to stdout only", _LOG_FILE)

    return logger
