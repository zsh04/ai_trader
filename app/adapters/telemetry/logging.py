import logging
import os
import sys
from typing import Optional


def _coerce_level(value: str) -> int:
    """
    Coerce a string log-level (e.g., 'info', 'DEBUG', 'warning') to a logging level int.
    Falls back to logging.INFO when unknown.
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
        "TRACE": 5,  # optional custom level; not registered unless user does it elsewhere
    }
    return lut.get(str(value).upper().strip(), logging.INFO)


def configure_logging(
    level: Optional[str] = None, json: Optional[bool] = None
) -> logging.Logger:
    """
    Configure process-wide logging.

    - Level can be passed or read from LOG_LEVEL (default: INFO).
    - Output format defaults to JSON in non-local envs and colored text locally.
      * ENVIRONMENT in {'local', 'dev', 'development'} -> colored console formatter (if colorlog present).
      * Otherwise -> JSON lines formatter to stdout (container/PM2/Azure-friendly).
    - Clears existing handlers to avoid duplicate logs under reloaders.
    - Hooks uvicorn loggers so they propagate to root.

    Returns the configured root logger.
    """
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "local").lower()
    level_name = level or os.getenv("LOG_LEVEL", "INFO")
    log_level = _coerce_level(level_name)

    if json is None:
        json = env not in {"local", "dev", "development"}

    handler = logging.StreamHandler(sys.stdout)

    if json:
        # Structured JSON for production/container logs
        fmt = (
            '{"ts":"%(asctime)s",'
            '"lvl":"%(levelname)s",'
            '"logger":"%(name)s",'
            '"file":"%(module)s","line":%(lineno)d,'
            '"msg":"%(message)s"}'
        )
        formatter = logging.Formatter(fmt)
    else:
        # Developer-friendly colored logs if colorlog is installed; fallback to plain text.
        try:
            from colorlog import ColoredFormatter  # type: ignore

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

    # Avoid double configuration under reloaders
    if getattr(root, "_configured_by_ai_trader", False):
        root.setLevel(log_level)
        return root

    # Reset handlers and attach our stream handler
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
    logging.captureWarnings(True)

    # Let uvicorn loggers propagate to root so we keep a single formatting/level policy
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(log_level)

    # Mark as configured
    root._configured_by_ai_trader = True

    return root


__all__ = ["configure_logging"]
