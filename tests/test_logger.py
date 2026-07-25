import logging

from src.logger import get_logger


def test_get_logger_returns_logger_with_name():
    logger = get_logger("test.module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_get_logger_sets_info_level():
    logger = get_logger("test.level")
    assert logger.level == logging.INFO


def test_get_logger_does_not_duplicate_handlers():
    logger = get_logger("test.duplicate")
    handler_count = len(logger.handlers)
    logger = get_logger("test.duplicate")
    assert len(logger.handlers) == handler_count
