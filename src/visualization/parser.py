"""Hierarchical JSON parser for ``real_world_fire_stations.json``.

Defensively reads **all** known key variants for community-level data
(``assigned_communities``, ``assigned_unit``, ``assigned_units``) and
validates the schema, raising :exc:`DataStructureMismatchError` on structural
violations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import DataStructureMismatchError
from .models import StationRecord
from .normalization import strip_political_terms


# ---------------------------------------------------------------------------
# Station-type derivation
# ---------------------------------------------------------------------------

_PS_ID_PREFIXES: tuple[str, ...] = (
    "1os_ps", "2os_ps", "3os_ps", "4os_ps", "5os_ps",
    "6os_ps", "7os_ps", "8os_ps", "9os_ps", "10os_ps", "12os_ps",
)


def _derive_station_type(station_id: str, station_name: str) -> str:
    """Infer the Hellenic Fire Service station type from its ID or name.

    The JSON has no explicit ``"type"`` field, so we infer from naming
    conventions used by the Hellenic Fire Service.

    Parameters
    ----------
    station_id : str
        Unique station identifier as stored in the JSON file.
    station_name : str
        Human-readable Greek station name.

    Returns
    -------
    str
        One of ``"ΠΣ"`` (Πυροσβεστικός Σταθμός), ``"ΠΥ"`` (Πυροσβεστική
        Υπηρεσία), or ``"ΠΚ"`` (Πυροσβεστικό Κλιμάκιο).  Defaults to
        ``"ΠΣ"`` for unknown stations.
    """
    if "ΠΣ" in station_name or station_id.startswith(_PS_ID_PREFIXES):
        return "ΠΣ"
    if "Π.Υ." in station_name or "ΠΥ" in station_name or station_id.startswith("py_"):
        return "ΠΥ"
    if "ΠΚ" in station_name or station_id.startswith("pk_"):
        return "ΠΚ"
    return "ΠΣ"


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

_REQUIRED_STATION_FIELDS: frozenset[str] = frozenset({"id", "name", "lat", "lon"})

_COMMUNITY_KEYS: tuple[str, ...] = (
    "assigned_communities",
    "assigned_unit",
    "assigned_units",
    "communities",
)


def _validate_station_entry(entry: dict[str, Any], index: int) -> None:
    """Raise :exc:`DataStructureMismatchError` if *entry* is malformed.

    Parameters
    ----------
    entry : dict[str, Any]
        A single station object parsed from JSON.
    index : int
        Zero-based position of the entry in the stations array (used in
        error messages).

    Raises
    ------
    DataStructureMismatchError
        If *entry* is not a dict, or if required fields are missing.
    """
    if not isinstance(entry, dict):
        raise DataStructureMismatchError(
            f"Station at index {index} is not a JSON object "
            f"(got {type(entry).__name__}).",
        )
    missing = _REQUIRED_STATION_FIELDS - entry.keys()
    if missing:
        raise DataStructureMismatchError(
            f"Station at index {index} (id={entry.get('id', '?')}) is missing "
            f"required fields: {sorted(missing)}.",
            key=", ".join(sorted(missing)),
            station_id=str(entry.get("id", "")),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class StationDataParser:
    """Parse ``real_world_fire_stations.json`` into typed ``StationRecord`` objects.

    Handles the two-level hierarchical schema:

    * ``assigned_municipalities`` — municipality-level coverage (OSM
      admin_level=7).
    * ``assigned_communities`` / ``assigned_unit`` / ``assigned_units``
      — community-level coverage (OSM admin_level=8).  All known key
      variants are read defensively.

    Parameters
    ----------
    path : Path or str
        Path to ``real_world_fire_stations.json``.

    Attributes
    ----------
    stations : list[StationRecord]
        Most recently parsed station records (empty before :meth:`parse` is
        called).
    metadata : dict[str, str]
        Optional ``"metadata"`` block from the JSON, if present.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._stations: list[StationRecord] = []
        self._raw: dict[str, Any] = {}

    # -- Loading & parsing ---------------------------------------------------

    def parse(self) -> list[StationRecord]:
        """Load the JSON file, validate, and return parsed station records.

        Returns
        -------
        list[StationRecord]
            One record per station, with both municipality and community
            coverage arrays populated.

        Raises
        ------
        DataStructureMismatchError
            If the file structure is invalid or required fields are missing.
        FileNotFoundError
            If the JSON file does not exist at ``self._path``.
        json.JSONDecodeError
            If the file is not valid JSON.
        """
        with open(self._path, encoding="utf-8") as fh:
            self._raw = json.load(fh)

        raw_stations = self._extract_stations_array()

        self._stations = []
        for idx, entry in enumerate(raw_stations):
            _validate_station_entry(entry, idx)
            self._stations.append(self._build_record(entry))

        return self._stations

    def _extract_stations_array(self) -> list[dict[str, Any]]:
        """Extract the stations list from either a nested or flat JSON structure.

        Returns
        -------
        list[dict[str, Any]]
            The raw list of station dicts.

        Raises
        ------
        DataStructureMismatchError
            If the JSON is not a list or dict, or if a dict lacks a
            ``"stations"`` key.
        """
        if isinstance(self._raw, list):
            return self._raw
        if isinstance(self._raw, dict):
            stations = self._raw.get("stations")
            if stations is not None:
                if not isinstance(stations, list):
                    raise DataStructureMismatchError(
                        "Top-level 'stations' key must be a JSON array.",
                        key="stations",
                    )
                return stations
            raise DataStructureMismatchError(
                "JSON object has no 'stations' key.",
                key="stations",
            )
        raise DataStructureMismatchError(
            f"Expected JSON object or array at top level, got "
            f"{type(self._raw).__name__}.",
        )

    @staticmethod
    def _build_record(entry: dict[str, Any]) -> StationRecord:
        """Convert a raw station dict into a typed :class:`StationRecord`.

        Parameters
        ----------
        entry : dict[str, Any]
            A validated station dict from the JSON file.

        Returns
        -------
        StationRecord
            Fully populated record with deduplicated community lists.
        """
        station_id: str = str(entry["id"])
        station_name: str = str(entry["name"])

        municipalities_raw: list[str] = entry.get("assigned_municipalities", [])
        if not isinstance(municipalities_raw, list):
            municipalities_raw = [str(municipalities_raw)]

        communities_raw: list[str] = []
        for key in _COMMUNITY_KEYS:
            val = entry.get(key)
            if val is not None:
                if isinstance(val, list):
                    communities_raw.extend(val)
                elif isinstance(val, str):
                    communities_raw.append(val)

        seen: set[str] = set()
        communities_deduped: list[str] = []
        for c in communities_raw:
            if c not in seen:
                seen.add(c)
                communities_deduped.append(c)

        return StationRecord(
            id=station_id,
            name=station_name,
            lat=float(entry["lat"]),
            lon=float(entry["lon"]),
            station_type=_derive_station_type(station_id, station_name),
            assigned_municipalities=tuple(municipalities_raw),
            assigned_communities=tuple(communities_deduped),
        )

    # -- Lookup table construction -------------------------------------------

    def build_lookup_tables(
        self,
    ) -> tuple[dict[str, StationRecord], dict[str, StationRecord]]:
        """Build normalised name → :class:`StationRecord` lookup tables.

        Calls :meth:`parse` automatically if it has not been called yet.

        Returns
        -------
        tuple[dict[str, StationRecord], dict[str, StationRecord]]
            A two-tuple ``(community_lookup, municipality_lookup)`` where keys
            are the output of :func:`~normalization.strip_political_terms`.
        """
        if not self._stations:
            self.parse()

        community_lookup: dict[str, StationRecord] = {}
        municipality_lookup: dict[str, StationRecord] = {}

        for station in self._stations:
            for community_name in station.assigned_communities:
                key = strip_political_terms(community_name)
                if key:
                    community_lookup[key] = station

            for mun_name in station.assigned_municipalities:
                key = strip_political_terms(mun_name)
                if key:
                    municipality_lookup[key] = station

        return community_lookup, municipality_lookup

    # -- Accessors -----------------------------------------------------------

    @property
    def stations(self) -> list[StationRecord]:
        """Return the most recently parsed station records.

        Returns
        -------
        list[StationRecord]
            A shallow copy of the internal station list.
        """
        return list(self._stations)

    @property
    def metadata(self) -> dict[str, str]:
        """Return the optional ``"metadata"`` block from the JSON, if present.

        Returns
        -------
        dict[str, str]
            The metadata dict, or an empty dict if absent or if the JSON root
            is not an object.
        """
        if isinstance(self._raw, dict):
            return dict(self._raw.get("metadata", {}))
        return {}
