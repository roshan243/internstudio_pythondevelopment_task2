"""Rotating application log configuration."""

import logging
from logging.handlers import RotatingFileHandler

from reporting.config import LOG_LEVEL, ROOT


def configure_logging() -> logging.Logger:
    directory = ROOT / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("reporting")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        directory / "application.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(logging.StreamHandler())
    return logger


LOGGER = configure_logging()
