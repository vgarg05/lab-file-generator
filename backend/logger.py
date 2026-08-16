"""
logger.py — Centralized structured logging for Lab File Generator.
Logs to stdout (Render / console) and writes to logs/app.log.
"""

import logging
import sys
from pathlib import Path

# Create logs directory at project root
PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# Formatter with timestamp, level, module name, message
FORMATTER = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Console / Stdout handler (Render captures this)
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(FORMATTER)

# File handler for local persistent logging
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(FORMATTER)


def get_logger(name: str = "labgen") -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger module name (e.g. 'labgen.main', 'labgen.executor').

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.addHandler(_console_handler)
        logger.addHandler(_file_handler)
        logger.propagate = False
    return logger
