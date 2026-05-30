"""Centralized logging helper for the application."""
import logging

_logger = logging.getLogger('geosquare')


def debug(msg: str):
    """Log a debug message."""
    _logger.debug(msg)


def info(msg: str):
    """Log an info message."""
    _logger.info(msg)


def warning(msg: str):
    """Log a warning message."""
    _logger.warning(msg)


def error(msg: str):
    """Log an error message."""
    _logger.error(msg)
