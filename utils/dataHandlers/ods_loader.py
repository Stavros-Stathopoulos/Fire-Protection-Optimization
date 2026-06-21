"""ODS file loader and validator for fire-incident datasets.

Provides :class:`OdsLoader`, which wraps :func:`pandas.read_excel` with an
ODF engine and enforces the column contract defined in
``config.data_config.REQUIRED_COLUMNS``.
"""

import os

import pandas as pd

from config.data_config import ODS_PATH, REQUIRED_COLUMNS
from utils.logger import get_logger

logger = get_logger(__name__)


class OdsLoader:
    """Load and validate a single ODS fire-incident data file.

    The loader constructs the absolute file path from ``ODS_PATH`` and the
    supplied filename so callers never need to know the on-disk layout.

    Parameters
    ----------
    file_path : str
        Filename (not full path) of the ODS file located inside
        ``config.data_config.ODS_PATH`` (``data/data/``).

    Attributes
    ----------
    file_path : str
        Absolute path assembled from ``ODS_PATH`` and the supplied filename.

    Examples
    --------
    >>> loader = OdsLoader("Stoixeia_Symvantwn.ods")
    >>> df = loader.load_data()
    >>> loader.check_data_format(df)
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = os.path.join(ODS_PATH, file_path)

    def load_data(self) -> pd.DataFrame:
        """Read the ODS file into a ``DataFrame``.

        Returns
        -------
        pandas.DataFrame
            All rows and columns from the ODS file with no transformation
            applied.

        Raises
        ------
        FileNotFoundError
            If ``self.file_path`` does not exist on disk.
        """
        if not self.check_file_exists():
            raise FileNotFoundError(f"The file {self.file_path} does not exist.")
        return pd.read_excel(self.file_path, engine="odf")

    def check_file_exists(self) -> bool:
        """Check whether the target ODS file exists on disk.

        Returns
        -------
        bool
            ``True`` if ``self.file_path`` resolves to an existing file,
            ``False`` otherwise.
        """
        return os.path.exists(self.file_path)

    def check_data_format(self, data: pd.DataFrame) -> bool:
        """Validate that *data* contains all required columns.

        Parameters
        ----------
        data : pandas.DataFrame
            ``DataFrame`` returned by :meth:`load_data`.

        Returns
        -------
        bool
            ``True`` when every column in
            ``config.data_config.REQUIRED_COLUMNS`` is present.

        Raises
        ------
        ValueError
            If one or more required columns are absent, with their names
            listed in the exception message.
        """
        missing = [col for col in REQUIRED_COLUMNS if col not in data.columns]

        if missing:
            raise ValueError(
                f"[{os.path.basename(self.file_path)}] Missing columns: {missing}"
            )

        logger.debug(f"[{os.path.basename(self.file_path)}] All required columns present")
        return True
