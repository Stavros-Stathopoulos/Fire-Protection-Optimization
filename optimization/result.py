"""Holds the structured output of a solved MILP optimization run."""

from dataclasses import dataclass
from typing import Dict, Set


@dataclass
class OptimizationResult:
    status: str
    objective_value: float              # Σ dk·ckj·zkj — demand-weighted response time
    open_stations: Set[str]             # station ids where yj = 1
    district_assignments: Dict[str, str]  # district_id → station_id (zkj = 1)
    firetruck_allocations: Dict[str, int] # station_id → firetrucks from region (vij)
    avg_response_time_min: float        # simple average ckj across all assigned districts
    total_operational_cost: float       # Σ fj for open stations (EUR)
