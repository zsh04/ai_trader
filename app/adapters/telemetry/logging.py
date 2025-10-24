import logging
import sys


def configure_logging(level: str = "INFO"):
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
