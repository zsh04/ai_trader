"""Loguru configuration helpers for consistent structured logging."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional, Union
from os import PathLike
from pathlib import Path
from loguru import logger

from app.config import settings as app_settings

# Global record factory to provide defaults for missing OTEL fields.
_old_factory = logging.getLogRecordFactory()
def _otel_safe_record_factory(*args, **kwargs):
    record = _old_factory(*args, **kwargs)
    if not hasattr(record, "otelTraceID"):    record.otelTraceID = "-"
    if not hasattr(record, "otelSpanID"):     record.otelSpanID = "-"
    if not hasattr(record, "otelTraceFlags"): record.otelTraceFlags = "-"
    return record
logging.setLogRecordFactory(_otel_safe_record_factory)

PathLikeArg = Union[str, PathLike]  # simple alias

_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
    "req={extra[request_id]} | env={extra[environment]} | "
    "ver={extra[service_version]} | sha={extra[git_sha]} | {message}"
)

OTEL_MISSING = {"otelTraceID": "-", "otelSpanID": "-", "otelTraceFlags": "-"}

def _std_logging_sink(message) -> None:
    record = message.record
    exc = record["exception"]
    exc_info = None
    if exc:
        tb = getattr(exc.traceback, "as_traceback", None)
        std_tb = tb() if callable(tb) else exc.traceback  # fallback
        # If the fallback isn't a real traceback (older Loguru), just pass None to avoid type errors.
        exc_info = (exc.type, exc.value, std_tb) if std_tb else (exc.type, exc.value, None)

    log_record = logging.LogRecord(
        name=record["name"],
        level=record["level"].no,
        pathname=record["file"].path,
        lineno=record["line"],
        msg=record["message"],
        args=(),
        exc_info=exc_info,
        func=record["function"],
    )
    for k, v in record["extra"].items():
        setattr(log_record, k, v)

    # Ensure OTEL attributes are always present on the stdlib record, even if the
    # Loguru message didn't carry them. (The global LogRecordFactory does not run
    # when we construct LogRecord manually.)
    for k, v in OTEL_MISSING.items():
        if not hasattr(log_record, k) or getattr(log_record, k) in (None, ""):
            setattr(log_record, k, v)

    logging.getLogger().handle(log_record)


def setup_logging(*, force: bool = False, level: str | None = None) -> None:
    """Configure Loguru sinks, bridge to stdlib, and attach contextual metadata."""
    if not force and getattr(setup_logging, "_configured", False):
        return

    logger.remove()

    log_level = (level or os.getenv("OTEL_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "INFO").upper()
    environment = os.getenv("ENV", "local")
    git_sha = (
        os.getenv("GIT_SHA")
        or os.getenv("COMMIT_SHA")
        or os.getenv("SOURCE_VERSION")
        or "unknown"
    )

    logger.configure(
        extra={
            "service_version": app_settings.VERSION,
            "environment": environment,
            "git_sha": git_sha,
            "request_id": "-",
        }
    )

    logger.add(
        sys.stdout,
        level=log_level,
        format=_LOG_FORMAT,
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )
    logger.add(
        _std_logging_sink,
        level=log_level,
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )

    std_level = getattr(logging, log_level, logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(std_level)
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler(sys.stdout))
    setup_logging._configured = True  # type: ignore[attr-defined]


def setup_test_logging(
    arg: Optional[Union[str, PathLikeArg]] = None,
    *,
    level: Optional[str] = None,
    file: Optional[PathLikeArg] = None,
    filename: str = "pytest.log",       # default file name when a directory is provided
    parallel_safe: bool = False,        # if True -> pytest-<pid>.log
) -> None:
    """
    Lightweight logging setup for tests.

    Accepts either:
      - a positional path (arg) to write logs to (file or directory), or
      - level="DEBUG"/"INFO", and/or file="/path/to/test.log".
    If a directory is provided, logs will go to <dir>/<filename> (or pytest-<pid>.log if parallel_safe).
    """
    # Interpret the positional arg: prefer path semantics if path-like or looks like a path
    inferred_level: Optional[str] = None
    inferred_path: Optional[Path] = None
    if arg is not None:
        if hasattr(arg, "__fspath__"):
            inferred_path = Path(arg)  # type: ignore[arg-type]
        elif isinstance(arg, str) and ("/" in arg or arg.endswith(".log")):
            inferred_path = Path(arg)
        elif isinstance(arg, str):
            inferred_level = arg

    effective_level = (level or inferred_level or os.getenv("PYTEST_LOGLEVEL") or "INFO").upper()

    # Base setup (stdout sink + stdlib bridge)
    setup_logging(force=True, level=effective_level)

    # Resolve target path preference: explicit `file` wins, then inferred_path
    target = Path(file) if file is not None else (inferred_path if inferred_path is not None else None)
    if target is None:
        return  # no file sink requested; stdout-only is fine

    # If target is a directory, place the file inside it
    if target.exists() and target.is_dir():
        fname = f"pytest-{os.getpid()}.log" if parallel_safe else filename
        target = target / fname
    else:
        # If target has no suffix but points to a non-existent path that looks like a dir,
        # we still respect it as a file path; callers can give explicit dirs to force dir behavior.
        if str(target).endswith(os.sep):
            target = Path(str(target).rstrip(os.sep))
            target.mkdir(parents=True, exist_ok=True)
            fname = f"pytest-{os.getpid()}.log" if parallel_safe else filename
            target = target / fname

    # Ensure parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    # Add file sink
    logger.add(
        str(target),
        level=effective_level,
        format=_LOG_FORMAT,
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )

__all__ = ["setup_logging", "setup_test_logging"]
