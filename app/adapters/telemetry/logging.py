import logging
import os
import sys
from typing import Optional


def _coerce_level(value: str) -> int:
    """
    Coerces a string log level to a logging level integer.

    Args:
        value (str): The string log level.

    Returns:
        int: The logging level integer.
    """
    if not value:
        return logging.INFO
    lut = {
        "CRITICAL": logging.CRITICAL,
        "FATAL": logging.FATAL,
        "ERROR": logging.ERROR,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
        "TRACE": 5,
    }
    return lut.get(str(value).upper().strip(), logging.INFO)


def configure_logging(
    level: Optional[str] = None, json: Optional[bool] = None
) -> logging.Logger:
    """
    Configures process-wide logging.

    Args:
        level (Optional[str]): The log level.
        json (Optional[bool]): Whether to use JSON formatting.

    Returns:
        logging.Logger: The configured root logger.
    """
    env = (os.getenv("APP_ENVIRONMENT") or os.getenv("APP_ENV") or "local").lower()
    level_name = level or os.getenv("LOG_LEVEL", "INFO")
    log_level = _coerce_level(level_name)

    if json is None:
        json = env not in {"local", "dev", "development"}

    handler = logging.StreamHandler(sys.stdout)

    if json:
        fmt = (
            '{"ts":"%(asctime)s",'
            '"lvl":"%(levelname)s",'
            '"logger":"%(name)s",'
            '"file":"%(module)s","line":%(lineno)d,'
            '"msg":"%(message)s"}'
        )
        formatter = logging.Formatter(fmt)
    else:
        try:
            from colorlog import ColoredFormatter

            formatter = ColoredFormatter(
                "%(log_color)s%(levelname)-8s%(reset)s %(asctime)s "
                "[%(name)s] %(message)s (%(module)s:%(lineno)d)",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold_red",
                },
            )
        except Exception:
            formatter = logging.Formatter(
                "%(levelname)-8s %(asctime)s [%(name)s] %(message)s (%(module)s:%(lineno)d)"
            )

    handler.setFormatter(formatter)

    root = logging.getLogger()

    if getattr(root, "_configured_by_ai_trader", False):
        root.setLevel(log_level)
        return root

    #root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
    logging.captureWarnings(True)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(log_level)

    root._configured_by_ai_trader = True

    return root


__all__ = ["configure_logging"]
