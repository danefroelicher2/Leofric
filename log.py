"""
log.py — one place to configure logging for the whole system.

Every module gets its logger with logging.getLogger(__name__); this module wires
up where those logs go: the console and a rotating file in logs/. The rotation
matters on a Pi — an always-on process must never fill the SD card with logs.
Call setup_logging() once at process start.
"""

import logging
from logging.handlers import RotatingFileHandler

import config


def setup_logging(level=logging.INFO):
    config.LOGS_DIR.mkdir(exist_ok=True)
    logfile = config.LOGS_DIR / "leofric.log"

    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:  # already configured — don't add duplicate handlers
        return

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Roll over at ~5 MB, keep 3 old files — bounded disk use, always-on safe.
    file_handler = RotatingFileHandler(logfile, maxBytes=5_000_000, backupCount=3)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
