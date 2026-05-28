"""CLI entry point for the ``dataHandlers`` package.

Invoked as::

    python -m utils.dataHandlers <file> [--no-validate]

Loads the specified ODS file, optionally validates its column schema, and
prints a brief summary (shape, column list, first rows) to stdout.
"""

import argparse
import sys

from utils.logger.logger import get_logger

from .ods_loader import OdsLoader

logger = get_logger(__name__)


def main() -> None:
    """Parse CLI arguments, load the ODS file, and log a summary.

    Exits with code ``1`` if the file is not found or fails column
    validation.

    Parameters
    ----------
    None
        Arguments are read directly from ``sys.argv`` via
        :mod:`argparse`.
    """
    parser = argparse.ArgumentParser(
        description="Load and validate an ODS fire incident data file."
    )
    parser.add_argument("file", help="ODS filename inside the data/ directory")
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip column validation"
    )
    args = parser.parse_args()

    loader = OdsLoader(args.file)

    try:
        df = loader.load_data()
    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

    if not args.no_validate:
        try:
            loader.check_data_format(df)
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            sys.exit(1)

    logger.info(f"Shape:   {df.shape}")
    logger.info(f"Columns: {df.columns.tolist()}")
    logger.debug(df.head())


if __name__ == "__main__":
    main()
