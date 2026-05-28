"""Runtime environment configuration.

Reads settings from environment variables so behaviour can be changed
without editing source files.  All variables have safe defaults that are
appropriate for local development.

Environment Variables
---------------------
APP_DEBUG : str, optional
    Set to ``'true'`` (case-insensitive) to enable debug mode.
    Defaults to ``'false'``.
APP_LOG_LEVEL : str, optional
    Logging level passed to the standard :mod:`logging` module
    (e.g. ``'DEBUG'``, ``'INFO'``, ``'WARNING'``, ``'ERROR'``).
    Defaults to ``'INFO'``.
"""

import os

DEBUG     = os.environ.get('APP_DEBUG', 'false').lower() == 'true'
LOG_LEVEL = os.environ.get('APP_LOG_LEVEL', 'INFO').upper()
