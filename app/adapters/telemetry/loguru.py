import logging
import sys
from pathlib import Path

from loguru import logger


class PropagateHandler(logging.Handler):
    def emit(self, record):
        logging.getLogger(record.name).handle(record)


def configure_loguru():
    logger.remove()
    logger.add(sys.stdout, colorize=True, level="INFO")
    logger.add(PropagateHandler(), format="{message}")


def configure_test_logging(log_path: Path):
    log_path.mkdir(parents=True, exist_ok=True)
    logger.add(log_path / "test.log", rotation="10 MB", retention="10 days")
