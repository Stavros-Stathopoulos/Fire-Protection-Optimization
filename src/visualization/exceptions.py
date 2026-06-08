"""Custom exception hierarchy for the visualization pipeline.

All exceptions inherit from ``VisualizationError`` so callers can catch
the entire family with a single handler while still distinguishing
specific failure modes when necessary.
"""


class VisualizationError(Exception):
    """Base exception for all visualization pipeline errors."""


class DataStructureMismatchError(VisualizationError):
    """Raised when JSON schema does not match the expected structure.

    Examples:
        * Missing top-level ``"stations"`` key.
        * A station entry lacks required fields (``id``, ``name``, ``lat``, ``lon``).
        * Neither ``assigned_municipalities`` nor ``assigned_communities``
          is present on a station record.
    """

    def __init__(self, message: str, *, key: str = "", station_id: str = "") -> None:
        self.key = key
        self.station_id = station_id
        super().__init__(message)


class CoverageResolutionError(VisualizationError):
    """Raised when a spatial entity cannot be matched to any fire station.

    Carries diagnostic details so the caller can log which entities failed
    and why.
    """

    def __init__(
        self,
        message: str,
        *,
        unit_name: str = "",
        municipality_name: str = "",
    ) -> None:
        self.unit_name = unit_name
        self.municipality_name = municipality_name
        super().__init__(message)


class ProjectionError(VisualizationError):
    """Raised on CRS conversion or spatial-join failures.

    Wraps the underlying GDAL / pyproj exception with context about which
    layer or geometry triggered the error.
    """

    def __init__(self, message: str, *, source_crs: str = "", target_crs: str = "") -> None:
        self.source_crs = source_crs
        self.target_crs = target_crs
        super().__init__(message)
