"""Custom exception hierarchy for the visualization pipeline.

All exceptions inherit from :exc:`VisualizationError` so callers can catch
the entire family with a single ``except VisualizationError`` handler while
still distinguishing specific failure modes when necessary.
"""


class VisualizationError(Exception):
    """Base exception for all visualization pipeline errors.

    Raised by any module in ``src/visualization/`` to signal a recoverable or
    non-recoverable pipeline failure.  Catching this base class is sufficient
    for callers that do not need to distinguish sub-types.
    """


class DataStructureMismatchError(VisualizationError):
    """Raised when a JSON schema does not match the expected structure.

    Common triggers:

    * Missing top-level ``"stations"`` key in ``real_world_fire_stations.json``.
    * A station entry lacks required fields (``id``, ``name``, ``lat``,
      ``lon``).
    * Neither ``assigned_municipalities`` nor ``assigned_communities`` is
      present on a station record.

    Parameters
    ----------
    message : str
        Human-readable description of the mismatch.
    key : str, optional
        The JSON key that is absent or malformed.  Defaults to ``""``.
    station_id : str, optional
        The ``id`` of the offending station, when applicable.  Defaults to
        ``""``.

    Attributes
    ----------
    key : str
        The JSON key that triggered the error.
    station_id : str
        The station ID associated with the error, or ``""`` if not
        applicable.
    """

    def __init__(self, message: str, *, key: str = "", station_id: str = "") -> None:
        self.key = key
        self.station_id = station_id
        super().__init__(message)


class CoverageResolutionError(VisualizationError):
    """Raised when a spatial entity cannot be matched to any fire station.

    Carries diagnostic details so the caller can log which entities failed
    and why.

    Parameters
    ----------
    message : str
        Human-readable description of the resolution failure.
    unit_name : str, optional
        Name of the OSM administrative unit that could not be matched.
        Defaults to ``""``.
    municipality_name : str, optional
        Name of the parent municipality, if known.  Defaults to ``""``.

    Attributes
    ----------
    unit_name : str
        The unmatched OSM unit name.
    municipality_name : str
        The parent municipality name, or ``""`` if unknown.
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

    Parameters
    ----------
    message : str
        Human-readable description of the projection failure.
    source_crs : str, optional
        The CRS the data was in before the failed conversion.  Defaults to
        ``""``.
    target_crs : str, optional
        The CRS the conversion was targeting.  Defaults to ``""``.

    Attributes
    ----------
    source_crs : str
        Source CRS string (e.g. ``"EPSG:4326"``).
    target_crs : str
        Target CRS string (e.g. ``"EPSG:2100"``).
    """

    def __init__(self, message: str, *, source_crs: str = "", target_crs: str = "") -> None:
        self.source_crs = source_crs
        self.target_crs = target_crs
        super().__init__(message)
