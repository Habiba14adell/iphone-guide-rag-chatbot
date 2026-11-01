"""Shared daily logging for the application and ingestion scripts."""

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


CAIRO_TIME = ZoneInfo("Africa/Cairo")
LOGS_PATH = Path(__file__).resolve().parents[3] / "logs"


class CairoFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        timestamp = datetime.fromtimestamp(record.created, CAIRO_TIME)
        return timestamp.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


class DailyFileHandler(logging.FileHandler):
    """Choose the day's file for every entry, including after midnight."""

    def __init__(self, logs_path):
        self.logs_path = Path(logs_path).resolve()
        self.logs_path.mkdir(parents=True, exist_ok=True)
        today = datetime.now(CAIRO_TIME).strftime("%Y-%m-%d")
        super().__init__(self.logs_path / f"{today}.log", mode="a", encoding="utf-8", delay=True)

    def emit(self, record):
        log_date = datetime.fromtimestamp(record.created, CAIRO_TIME).strftime("%Y-%m-%d")
        filename = str(self.logs_path / f"{log_date}.log")
        if filename != self.baseFilename:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            self.baseFilename = filename
        super().emit(record)


def setup_logging(logs_path=LOGS_PATH):
    """Configure shared logging without adding duplicate daily handlers."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if any(isinstance(handler, DailyFileHandler) for handler in logger.handlers):
        return

    handler = DailyFileHandler(logs_path)
    handler.setLevel(logging.INFO)
    handler.setFormatter(CairoFormatter(
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    ))
    logger.addHandler(handler)
