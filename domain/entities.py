"""Core domain objects for the fire-protection optimization problem.

Frozen dataclasses act as value objects: safe to hash, safe to use as dict keys.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FireRegion:
    id: str
    name: str
    total_firetrucks: int   # pi: fleet size available to the region
    lat: float = 0.0        # HQ latitude  — used for proximity-weighted allocation
    lon: float = 0.0        # HQ longitude — used for proximity-weighted allocation


@dataclass(frozen=True)
class FireStation:
    id: str
    name: str
    lat: float
    lon: float
    capacity: int    # sj: maximum firetrucks the station can hold
    cost: float      # fj: annual operational cost (EUR)


@dataclass(frozen=True)
class IncidentDistrict:
    id: str
    name: str
    lat: float           # centroid latitude
    lon: float           # centroid longitude
    demand: float        # dk: fire-coverage need (unit depends on DEMAND_METRIC)
    area_km2: float      # municipality area — used to estimate intra-district travel time
    wildfire_risk: float # 1.0 (low/urban) … 5.0 (extreme/forest) — objective weight
