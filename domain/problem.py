"""Assembles the MILP parameter matrices from domain entities.

Multi-region formulation: accepts a list of ``FireRegion`` objects (one per
ΔΙΠΥ directorate).  The response-time matrix ``c_{kj}`` is region-independent
(geography does not change per ΔΙΠΥ), but the proximity-distance matrix
``t_{ij}`` is indexed ``(region_id, station_id)`` to capture how far each
directorate's HQ is from each candidate station.
"""

import math
from dataclasses import dataclass

from config.milp_config import DISPATCH_BASE_MINUTES, INTRA_DISTRICT_FACTOR
from utils.traffic import route_multiplier

from .entities import FireRegion, FireStation, IncidentDistrict


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great-circle distance between two WGS 84 points.

    Parameters
    ----------
    lat1 : float
        Latitude of the first point in decimal degrees.
    lon1 : float
        Longitude of the first point in decimal degrees.
    lat2 : float
        Latitude of the second point in decimal degrees.
    lon2 : float
        Longitude of the second point in decimal degrees.

    Returns
    -------
    float
        Great-circle distance in kilometres.
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class FireProtectionProblem:
    """Multi-region fire protection problem definition.

    Aggregates all domain entities and provides factory methods that build the
    parameter matrices required by the MILP model builder.

    Parameters
    ----------
    regions : list[FireRegion]
        One ``FireRegion`` per ΔΙΠΥ directorate.  Each carries its fleet size
        ``π_i`` and HQ coordinates used for the proximity penalty.
    stations : list[FireStation]
        Candidate fire station sites shared across all regions.
    districts : list[IncidentDistrict]
        Aggregated demand nodes (municipalities).

    Attributes
    ----------
    regions : list[FireRegion]
        ΔΙΠΥ directorates as supplied.
    stations : list[FireStation]
        Candidate stations as supplied.
    districts : list[IncidentDistrict]
        Demand districts as supplied.
    """

    regions: list[FireRegion]
    stations: list[FireStation]
    districts: list[IncidentDistrict]

    # -- Aggregate accessors -------------------------------------------------

    @property
    def total_fleet(self) -> int:
        """Sum of all regional fleet sizes (``Σ π_i``).

        Returns
        -------
        int
            Total number of firetrucks available across all ΔΙΠΥ directorates.
        """
        return sum(r.total_firetrucks for r in self.regions)

    @property
    def total_demand(self) -> float:
        """Aggregate demand across all districts (``Σ d_k``).

        Returns
        -------
        float
            Sum of every district's demand value.
        """
        return sum(d.demand for d in self.districts)

    # -- Matrix builders -----------------------------------------------------

    def response_time_matrix(self, speed_kmh: float) -> dict[tuple[str, str], float]:
        """Build ``c_{kj}``: traffic-adjusted response time for every (district, station) pair.

        The response time for district ``k`` and station ``j`` is:

        .. code-block:: text

            intra_time = sqrt(area_km2 / π) / speed_kmh * 60 * INTRA_DISTRICT_FACTOR
            travel_time = haversine_km(k, j) / speed_kmh * 60 * traffic_multiplier(j, k)
            c_kj = DISPATCH_BASE_MINUTES + travel_time + intra_time

        ``intra_time`` models the expected navigation time once the crew is
        within the district boundary — the fire is somewhere inside the
        municipality area, not exactly at the centroid.  It grows with the
        effective radius ``sqrt(area/π)`` and ensures that even a co-located
        station reports a physically meaningful response time.

        Parameters
        ----------
        speed_kmh : float
            Assumed travel speed in km/h for converting Haversine distance to
            minutes.

        Returns
        -------
        dict[tuple[str, str], float]
            Mapping ``{(district_id, station_id): response_time_minutes}``
            covering every ``(k, j)`` pair.
        """
        result: dict[tuple[str, str], float] = {}
        for d in self.districts:
            effective_radius_km = math.sqrt(d.area_km2 / math.pi)
            intra_time = effective_radius_km / speed_kmh * 60 * INTRA_DISTRICT_FACTOR
            for s in self.stations:
                km = _haversine_km(d.lat, d.lon, s.lat, s.lon)
                multiplier = route_multiplier(s.lat, s.lon, d.lat, d.lon)
                travel_time = km / speed_kmh * 60 * multiplier
                result[(d.id, s.id)] = travel_time + intra_time + DISPATCH_BASE_MINUTES
        return result

    def transport_cost_matrix(self) -> dict[tuple[str, str], float]:
        """Build ``t_{ij}``: firetruck deployment cost from region ``i`` to station ``j``.

        In the current Attica formulation all ΔΙΠΥ depots are co-located with
        their operating area, so inter-depot transport cost is uniformly zero.
        The matrix is retained to keep the interface consistent with
        generalised multi-depot facility-location formulations.

        Returns
        -------
        dict[tuple[str, str], float]
            Mapping ``{(region_id, station_id): 0.0}`` for every ``(i, j)``
            pair.
        """
        return {
            (r.id, s.id): 0.0
            for r in self.regions
            for s in self.stations
        }

    def region_station_distance_matrix(self) -> dict[tuple[str, str], float]:
        """Build the Haversine-distance matrix from each ΔΙΠΥ HQ to each station.

        Used exclusively to compute the geographic proximity penalty in the MILP
        objective so that truck allocation is geographically meaningful: trucks
        are preferentially assigned from the nearest ΔΙΠΥ directorate rather
        than picked arbitrarily when the primary objective is degenerate.

        Returns
        -------
        dict[tuple[str, str], float]
            Mapping ``{(region_id, station_id): distance_km}`` for every
            ``(i, j)`` pair.
        """
        return {
            (r.id, s.id): _haversine_km(r.lat, r.lon, s.lat, s.lon)
            for r in self.regions
            for s in self.stations
        }
