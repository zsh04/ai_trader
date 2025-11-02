import logging
from typing import Optional

from .loguru import configure_loguru


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
    configure_loguru()
    return logging.getLogger()


__all__ = ["configure_logging"]
