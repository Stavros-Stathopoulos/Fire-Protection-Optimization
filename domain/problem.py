"""Assembles the MILP parameter matrices from domain entities."""

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
    region: FireRegion
    stations: List[FireStation]
    districts: List[IncidentDistrict]

    @property
    def total_demand(self) -> float:
        """d(K): aggregate demand across all districts."""
        return sum(d.demand for d in self.districts)

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
        result = {}
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
        """tij: firetruck deployment cost from region to station.

        Zero for all pairs: Attica is treated as a single region with no
        inter-depot transport cost in this one-region formulation.
        """
        return {(self.region.id, s.id): 0.0 for s in self.stations}
