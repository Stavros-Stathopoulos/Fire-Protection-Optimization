"""Typed data models for the visualization pipeline.

Every data structure that flows between pipeline stages is defined here as a
frozen (or regular) dataclass with 100 % type-hint coverage.  This prevents
ad-hoc dicts from propagating through the codebase and makes the
visualisation pipeline genuinely solver-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry.base import BaseGeometry


# ---------------------------------------------------------------------------
# Station ingestion models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StationRecord:
    """A parsed fire station with both municipality- and community-level coverage.

    Populated by :class:`~src.visualization.parser.StationDataParser` from
    ``real_world_fire_stations.json``.

    Parameters
    ----------
    id : str
        Unique ASCII station identifier.
    name : str
        Human-readable Greek name.
    lat : float
        Station latitude in WGS 84 decimal degrees.
    lon : float
        Station longitude in WGS 84 decimal degrees.
    station_type : str
        Hellenic Fire Service category: ``"ΠΣ"`` (Πυροσβεστικός Σταθμός),
        ``"ΠΥ"`` (Πυροσβεστική Υπηρεσία), or ``"ΠΚ"`` (Πυροσβεστικό
        Κλιμάκιο).
    assigned_municipalities : tuple[str, ...]
        Municipality names at OSM admin_level=7 covered by this station.
    assigned_communities : tuple[str, ...]
        Community-unit names at OSM admin_level=8 covered by this station.

    Attributes
    ----------
    all_coverage_names : tuple[str, ...]
        Union of both coverage arrays (municipalities + communities).
    """

    id: str
    name: str
    lat: float
    lon: float
    station_type: str
    assigned_municipalities: tuple[str, ...]
    assigned_communities: tuple[str, ...]

    @property
    def all_coverage_names(self) -> tuple[str, ...]:
        """Return all coverage zone names (municipalities + communities).

        Returns
        -------
        tuple[str, ...]
            Concatenation of ``assigned_municipalities`` and
            ``assigned_communities``.
        """
        return self.assigned_municipalities + self.assigned_communities


# ---------------------------------------------------------------------------
# Coverage matching models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoverageAssignment:
    """Result of matching an OSM spatial unit to a fire station.

    Produced by :class:`~src.visualization.matcher.HybridMatcher` for every
    community unit or municipality polygon in the OSM dataset.

    Parameters
    ----------
    geometry : shapely.geometry.base.BaseGeometry
        The polygon geometry of the administrative unit.
    unit_name : str
        Raw OSM name of the community unit or municipality.
    mun_name : str
        Name of the parent municipality (from spatial join).
    match_method : str
        Human-readable description of which matching tier succeeded
        (e.g. ``"Unit Exact Match"``, ``"Municipal Fallback"``).
    station_name : str
        Name of the matched station, or ``"—"`` if unmatched.
    station_id : str
        ID of the matched station, or ``"unknown"`` if unmatched.
    station_type : str
        Type of the matched station (``"ΠΣ"`` / ``"ΠΥ"`` / ``"ΠΚ"``), or
        ``"?"`` if unmatched.
    """

    geometry: BaseGeometry
    unit_name: str
    mun_name: str
    match_method: str
    station_name: str
    station_id: str
    station_type: str


# ---------------------------------------------------------------------------
# MILP visualizer models (solver-agnostic)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MilpStationStatus:
    """Status of a single station in the MILP solution.

    Intentionally solver-agnostic: contains no PuLP or Gurobi objects.
    Populated from ``OptimizationResult.open_stations`` and
    ``OptimizationResult.firetruck_allocations``.

    Parameters
    ----------
    station_id : str
        Unique ASCII station identifier.
    station_name : str
        Human-readable Greek name.
    lat : float
        Station latitude in WGS 84 decimal degrees.
    lon : float
        Station longitude in WGS 84 decimal degrees.
    is_active : bool
        ``True`` if the solver opened this station (``y_j = 1``).
    apparatus_count : int
        Total firetrucks deployed to this station (``Σ_i v_{ij}``).
    capacity : int
        Maximum firetrucks the station can hold (``s_j``).
    annual_cost : float
        Annual operational cost in EUR (``f_j``).
    region_allocations : tuple[tuple[str, int], ...], optional
        ``((region_id, truck_count), ...)`` pairs for non-zero ``v_{ij}``
        values.  Defaults to an empty tuple.

    Attributes
    ----------
    region_allocations_dict : dict[str, int]
        ``region_allocations`` as a plain dict for easy lookup.
    """

    station_id: str
    station_name: str
    lat: float
    lon: float
    is_active: bool
    apparatus_count: int
    capacity: int
    annual_cost: float
    region_allocations: tuple[tuple[str, int], ...] = ()

    @property
    def region_allocations_dict(self) -> dict[str, int]:
        """Return region_allocations as a plain ``{region_id: truck_count}`` dict.

        Returns
        -------
        dict[str, int]
            Mapping of region IDs to truck counts.
        """
        return dict(self.region_allocations)


@dataclass(frozen=True)
class MilpDistrictAssignment:
    """How a single demand district is served in the MILP solution.

    Parameters
    ----------
    district_id : str
        Stable ASCII identifier (e.g. ``"dist_0"``).
    district_name : str
        Greek municipality name.
    lat : float
        District centroid latitude in WGS 84 decimal degrees.
    lon : float
        District centroid longitude in WGS 84 decimal degrees.
    assigned_station_id : str
        ID of the station that covers this district in the optimal solution.
    response_time_min : float
        Traffic-adjusted response time ``c_{kj}`` in minutes.
    demand : float
        Fire-coverage demand ``d_k``.
    area_km2 : float
        Municipality area in km².
    wildfire_risk : float
        Wildfire risk factor (``1.0`` – ``5.0``).
    """

    district_id: str
    district_name: str
    lat: float
    lon: float
    assigned_station_id: str
    response_time_min: float
    demand: float
    area_km2: float
    wildfire_risk: float


@dataclass
class MilpVisualizationInput:
    """Complete, solver-agnostic input bundle for the MILP visualizer.

    Constructed by the caller from an ``OptimizationResult`` and a
    ``FireProtectionProblem`` without importing any solver library.

    Parameters
    ----------
    station_statuses : list[MilpStationStatus], optional
        One record per candidate station.  Defaults to ``[]``.
    district_assignments : list[MilpDistrictAssignment], optional
        One record per demand district.  Defaults to ``[]``.
    boundaries : object or None, optional
        Optional ``geopandas.GeoDataFrame`` of municipality polygons for the
        choropleth layer.  Kept typed as ``object`` to avoid a hard
        geopandas import at module level.  Defaults to ``None``.
    solver_status : str, optional
        PuLP solver status string.  Defaults to ``"Unknown"``.
    objective_value : float, optional
        Minimised objective value.  Defaults to ``0.0``.
    total_operational_cost : float, optional
        Sum of annual costs for open stations (EUR).  Defaults to ``0.0``.
    avg_response_time_min : float, optional
        Simple average response time across all districts.  Defaults to
        ``0.0``.
    """

    station_statuses: list[MilpStationStatus] = field(default_factory=list)
    district_assignments: list[MilpDistrictAssignment] = field(default_factory=list)
    boundaries: Optional[object] = None
    solver_status: str = "Unknown"
    objective_value: float = 0.0
    total_operational_cost: float = 0.0
    avg_response_time_min: float = 0.0
