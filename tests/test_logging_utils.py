from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest
from loguru import logger

from app.config import settings
from app.logging_utils import setup_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    setup_logging(force=True, level="INFO")
    yield
    setup_logging(force=True, level="INFO")


@contextmanager
def capture_records(level=logging.INFO):
    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = ListHandler()
    handler.setLevel(level)
    root = logging.getLogger()
    prev_level = root.level
    root.setLevel(level)
    root.addHandler(handler)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)


def test_setup_logging_attaches_metadata(monkeypatch):
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("GIT_SHA", "abc123")

    setup_logging(force=True, level="INFO")

    with capture_records() as records:
        logger.info("hello world")

    record = records[-1]
    assert record.environment == "staging"
    assert record.git_sha == "abc123"
    assert record.service_version == settings.VERSION
    assert record.request_id == "-"


def test_contextual_request_id():
    with capture_records() as records:
        with logger.contextualize(request_id="req-1"):
            logger.info("with request id")

    record = records[-1]
    assert record.request_id == "req-1"
