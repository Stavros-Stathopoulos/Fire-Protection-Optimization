"""Assembles the MILP parameter matrices from domain entities.

Multi-region formulation: accepts a list of ``FireRegion`` objects
(one per ΔΙΠΥ directorate).  The response-time matrix ``ckj`` is
region-independent (geography doesn't change), but the transport-cost
matrix ``tij`` is now properly indexed ``(region_id, station_id)``.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from config.milp_config import DISPATCH_BASE_MINUTES, INTRA_DISTRICT_FACTOR
from utils.traffic import route_multiplier

from .entities import FireRegion, FireStation, IncidentDistrict


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class FireProtectionProblem:
    """Multi-region fire protection problem definition.

    Parameters
    ----------
    regions:
        One ``FireRegion`` per ΔΙΠΥ directorate.  Each carries its own
        fleet size (``total_firetrucks``).
    stations:
        Candidate fire stations (shared across all regions).
    districts:
        Incident districts (demand nodes).
    """

    regions: List[FireRegion]
    stations: List[FireStation]
    districts: List[IncidentDistrict]

    # -- Aggregate accessors -------------------------------------------------

    @property
    def total_fleet(self) -> int:
        """Sum of all regional fleet sizes (Σ pi)."""
        return sum(r.total_firetrucks for r in self.regions)

    @property
    def total_demand(self) -> float:
        """d(K): aggregate demand across all districts."""
        return sum(d.demand for d in self.districts)

    # -- Matrix builders -----------------------------------------------------

    def response_time_matrix(self, speed_kmh: float) -> Dict[Tuple[str, str], float]:
        """ckj: traffic-adjusted response time (minutes) for every (district, station) pair.

        Formula:
          intra_time = sqrt(area_km2 / π) / speed_kmh * 60 * INTRA_DISTRICT_FACTOR
          travel_time = haversine_km / speed_kmh * 60 * traffic_multiplier
          ckj = travel_time + intra_time + DISPATCH_BASE_MINUTES

        intra_time is the expected navigation time once the crew is within the
        district boundary — the fire is somewhere inside the municipality area,
        not exactly at the centroid.  It grows with the effective radius
        (sqrt(area/π)) and ensures that even a co-located station reports a
        meaningful response time.
        """
        result: Dict[Tuple[str, str], float] = {}
        for d in self.districts:
            effective_radius_km = math.sqrt(d.area_km2 / math.pi)
            intra_time = effective_radius_km / speed_kmh * 60 * INTRA_DISTRICT_FACTOR
            for s in self.stations:
                km = _haversine_km(d.lat, d.lon, s.lat, s.lon)
                multiplier = route_multiplier(s.lat, s.lon, d.lat, d.lon)
                travel_time = km / speed_kmh * 60 * multiplier
                result[(d.id, s.id)] = travel_time + intra_time + DISPATCH_BASE_MINUTES
        return result

    def transport_cost_matrix(self) -> Dict[Tuple[str, str], float]:
        """tij: firetruck deployment cost from region i to station j.

        Zero for all pairs: Attica regions are co-located with no
        inter-depot transport cost in this formulation.
        """
        return {
            (r.id, s.id): 0.0
            for r in self.regions
            for s in self.stations
        }
