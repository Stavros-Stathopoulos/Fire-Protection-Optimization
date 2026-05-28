"""Data-handler utilities for loading and validating ODS datasets.

Exposes ``OdsLoader`` as the primary public API.  Import pattern::

    from utils.dataHandlers import OdsLoader
"""

from .ods_loader import OdsLoader

__all__ = ["OdsLoader"]
