"""Hierarchical JSON parser for ``real_world_fire_stations.json``.

Fixes the original ``test2.py`` bug where the code read
``station.get("assigned_units", [])`` but the JSON used the singular key
``"assigned_unit"``, causing the community-level lookup table to be
permanently empty.

This parser defensively reads **all** known key variants for community-level
data (``assigned_communities``, ``assigned_unit``, ``assigned_units``) and
validates the schema, raising ``DataStructureMismatchError`` on structural
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
    """Derive ΠΣ / ΠΥ / ΠΚ from station name or id.

    The JSON has no explicit ``"type"`` field, so we infer from naming
    conventions used by the Hellenic Fire Service.

    Returns
    -------
    str
        One of ``"ΠΣ"``, ``"ΠΥ"``, ``"ΠΚ"``.
    """
    if "ΠΣ" in station_name or station_id.startswith(_PS_ID_PREFIXES):
        return "ΠΣ"
    if "Π.Υ." in station_name or "ΠΥ" in station_name or station_id.startswith("py_"):
        return "ΠΥ"
    if "ΠΚ" in station_name or station_id.startswith("pk_"):
        return "ΠΚ"
    return "ΠΣ"  # sensible default for unnamed/unknown


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

_REQUIRED_STATION_FIELDS: frozenset[str] = frozenset({"id", "name", "lat", "lon"})

# All keys the JSON might use for community-level (Δ.Ε.) assignments.
# The original schema used "assigned_unit" (singular); the normalised
# schema uses "assigned_communities"; we accept all variants defensively.
_COMMUNITY_KEYS: tuple[str, ...] = (
    "assigned_communities",
    "assigned_unit",
    "assigned_units",
    "communities",
)


def _validate_station_entry(entry: dict[str, Any], index: int) -> None:
    """Raise ``DataStructureMismatchError`` if *entry* is malformed."""
    if not isinstance(entry, dict):
        raise DataStructureMismatchError(
            f"Station at index {index} is not a JSON object (got {type(entry).__name__}).",
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
    """Parses ``real_world_fire_stations.json`` into typed ``StationRecord`` objects.

    Handles the two-level hierarchical schema:
      * ``assigned_municipalities`` — municipality-level (OSM admin_level=7)
      * ``assigned_communities`` / ``assigned_unit`` / ``assigned_units``
        — community-level (OSM admin_level=8)
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
            If the JSON file does not exist.
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
        """Extract the stations list from either nested or flat JSON."""
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
            f"Expected JSON object or array at top level, got {type(self._raw).__name__}.",
        )

    @staticmethod
    def _build_record(entry: dict[str, Any]) -> StationRecord:
        """Convert a raw dict into a typed ``StationRecord``."""
        station_id: str = str(entry["id"])
        station_name: str = str(entry["name"])

        # Municipality-level coverage
        municipalities_raw: list[str] = entry.get("assigned_municipalities", [])
        if not isinstance(municipalities_raw, list):
            municipalities_raw = [str(municipalities_raw)]

        # Community-level coverage — read ALL known key variants (THE FIX)
        communities_raw: list[str] = []
        for key in _COMMUNITY_KEYS:
            val = entry.get(key)
            if val is not None:
                if isinstance(val, list):
                    communities_raw.extend(val)
                elif isinstance(val, str):
                    communities_raw.append(val)

        # Deduplicate while preserving order
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
        """Build normalised name → StationRecord lookup tables.

        Returns
        -------
        tuple[dict, dict]
            ``(community_lookup, municipality_lookup)`` where keys are the
            output of ``strip_political_terms()``.
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
        """Return the most recently parsed station records."""
        return list(self._stations)

    @property
    def metadata(self) -> dict[str, str]:
        """Return the optional ``"metadata"`` block from the JSON, if present."""
        if isinstance(self._raw, dict):
            return dict(self._raw.get("metadata", {}))
        return {}
