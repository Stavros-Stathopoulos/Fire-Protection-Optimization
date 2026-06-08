"""Typed data models for the visualization pipeline.

Every data structure that flows between pipeline stages is defined here
as a frozen (or regular) dataclass with 100 % type-hint coverage.
This prevents ad-hoc dicts from propagating through the codebase.
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
    """A parsed fire station with both municipality- and community-level coverage."""

    id: str
    name: str
    lat: float
    lon: float
    station_type: str  # "ΠΣ" | "ΠΥ" | "ΠΚ"
    assigned_municipalities: tuple[str, ...]
    assigned_communities: tuple[str, ...]  # Δ.Ε.-level (admin_level=8)

    @property
    def all_coverage_names(self) -> tuple[str, ...]:
        """Return all coverage zone names (municipalities + communities)."""
        return self.assigned_municipalities + self.assigned_communities


# ---------------------------------------------------------------------------
# Coverage matching models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoverageAssignment:
    """Result of matching an OSM spatial unit to a fire station."""

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

    This is intentionally solver-agnostic: no PuLP/Gurobi objects.
    Populate from ``OptimizationResult.open_stations`` and
    ``OptimizationResult.firetruck_allocations``.
    """

    station_id: str
    station_name: str
    lat: float
    lon: float
    is_active: bool
    apparatus_count: int  # total firetrucks deployed (sum of all v_ij)
    capacity: int
    annual_cost: float
    region_allocations: tuple[tuple[str, int], ...] = ()  # (region_id, truck_count) pairs

    @property
    def region_allocations_dict(self) -> dict[str, int]:
        """Return region_allocations as a plain ``{region_id: truck_count}`` dict."""
        return dict(self.region_allocations)


@dataclass(frozen=True)
class MilpDistrictAssignment:
    """How a single demand district is served in the MILP solution."""

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

    Constructed by the caller from ``OptimizationResult`` + ``FireProtectionProblem``
    without importing any solver library.
    """

    station_statuses: list[MilpStationStatus] = field(default_factory=list)
    district_assignments: list[MilpDistrictAssignment] = field(default_factory=list)
    boundaries: Optional[object] = None  # GeoDataFrame, kept optional
    solver_status: str = "Unknown"
    objective_value: float = 0.0
    total_operational_cost: float = 0.0
    avg_response_time_min: float = 0.0
