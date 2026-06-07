"""Colour-aware logging factory for the project.

Provides a single ``get_logger`` factory that returns a ``logging.Logger``
pre-configured with a ``StreamHandler`` whose formatter applies per-level
ANSI colours and the fixed message structure::

    HH:MM:SS | <script> | <LEVEL>   | <message>
"""

import io
import logging
import os
import sys


class _Colour:
    """ANSI escape codes used by ``_ColourFormatter``."""

    RESET    = '\033[0m'
    GREY     = '\033[38;5;245m'
    CYAN     = '\033[36m'
    YELLOW   = '\033[33m'
    RED      = '\033[31m'
    BOLD_RED = '\033[1;31m'


_LEVEL_COLOURS = {
    logging.DEBUG:    _Colour.GREY,
    logging.INFO:     _Colour.CYAN,
    logging.WARNING:  _Colour.YELLOW,
    logging.ERROR:    _Colour.RED,
    logging.CRITICAL: _Colour.BOLD_RED,
}


class _ColourFormatter(logging.Formatter):
    """``logging.Formatter`` subclass that injects ANSI colour per log level.

    The formatted line follows the project-wide structure::

        HH:MM:SS | <script> | <LEVEL>   | <message>

    where ``<script>`` is derived from ``record.pathname`` (stem only) and
    ``<LEVEL>`` is left-padded to seven characters for column alignment.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* as a colour-annotated log line.

        Parameters
        ----------
        record : logging.LogRecord
            The log record emitted by the calling logger.

        Returns
        -------
        str
            A single formatted log line with ANSI colour escapes applied to
            the level token.
        """
        colour = _LEVEL_COLOURS.get(record.levelno, _Colour.RESET)
        level  = f'{colour}{record.levelname:<7}{_Colour.RESET}'
        time   = self.formatTime(record, '%H:%M:%S')
        script = os.path.splitext(os.path.basename(record.pathname))[0]
        return f'{time} | {script} | {level} | {record.getMessage()}'


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a project logger configured with colour output.

    Calling this function multiple times with the same *name* returns the
    same ``Logger`` instance (Python's logging module is a singleton
    registry).  The handler and formatter are attached only once, guarded
    by ``logger.handlers``.

    Parameters
    ----------
    name : str or None, optional
        Logger name.  Pass ``__name__`` from the calling module so the
        script-name column in every log line reflects the real source file.
        Defaults to ``'app'`` when ``None``.

    Returns
    -------
    logging.Logger
        A ``Logger`` set to ``DEBUG`` level with a colour ``StreamHandler``
        writing to *stdout* and propagation disabled.

    Examples
    --------
    >>> from utils.logger import get_logger
    >>> log = get_logger(__name__)
    >>> log.info("data loaded")
    """
    logger = logging.getLogger(name or 'app')

    if logger.handlers:
        return logger

    # Use UTF-8 so Greek/non-ASCII log messages don't crash on Windows consoles
    utf8_stdout = (
        io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stdout, "buffer")
        else sys.stdout
    )
    handler = logging.StreamHandler(utf8_stdout)
    handler.setFormatter(_ColourFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    return logger
