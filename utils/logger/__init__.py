"""Logging utilities package.

Exposes ``get_logger``, the single entry point for obtaining a project-wide
colour logger.  Import pattern::

    from utils.logger import get_logger
    log = get_logger(__name__)
"""

from .logger import get_logger

__all__ = ["get_logger"]
