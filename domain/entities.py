"""Core domain objects for the fire-protection optimization problem.

Frozen dataclasses act as value objects: safe to hash, safe to use as dict
keys, and free of solver imports.  All numeric attributes use their natural
Python types (``int`` / ``float``) so they can flow into PuLP expressions
without conversion.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FireRegion:
    """A ΔΙΠΥ regional fire-service directorate.

    Carries its available fleet size and headquarters coordinates.  The HQ
    coordinates are used exclusively for the geographic proximity penalty in
    the MILP objective — they do not affect coverage constraints.

    Parameters
    ----------
    id : str
        Unique ASCII identifier (e.g. ``"dipy_athens"``).
    name : str
        Human-readable Greek name (e.g. ``"ΔΙΠΥ ΑΘΗΝΩΝ"``).
    total_firetrucks : int
        Total fleet size available to this directorate (``π_i`` in the model).
    lat : float, optional
        Headquarters latitude in WGS 84 decimal degrees.  Defaults to ``0.0``.
    lon : float, optional
        Headquarters longitude in WGS 84 decimal degrees.  Defaults to ``0.0``.
    """

    id: str
    name: str
    total_firetrucks: int
    lat: float = 0.0
    lon: float = 0.0


@dataclass(frozen=True)
class FireStation:
    """A candidate fire station site.

    Parameters
    ----------
    id : str
        Unique ASCII identifier (e.g. ``"ps_marathon"``).
    name : str
        Human-readable Greek name (e.g. ``"ΠΣ Μαραθώνα"``).
    lat : float
        Centroid latitude in WGS 84 decimal degrees.
    lon : float
        Centroid longitude in WGS 84 decimal degrees.
    capacity : int
        Maximum number of firetrucks the station can hold (``s_j`` in the
        model).
    cost : float
        Annual operational cost in EUR (``f_j`` in the model).
    """

    id: str
    name: str
    lat: float
    lon: float
    capacity: int
    cost: float


@dataclass(frozen=True)
class IncidentDistrict:
    """An aggregated incident demand district (municipality).

    Parameters
    ----------
    id : str
        Stable numeric identifier used in PuLP variable names, e.g.
        ``"dist_0"``.  Greek names are non-ASCII and cannot appear in PuLP
        variable names.
    name : str
        Greek municipality name (e.g. ``"Μαραθώνας"``).
    lat : float
        Centroid latitude in WGS 84 decimal degrees.
    lon : float
        Centroid longitude in WGS 84 decimal degrees.
    demand : float
        Fire-coverage need ``d_k``.  The unit depends on
        ``config.milp_config.DEMAND_METRIC`` (mean vehicles per incident,
        incident count, or total vehicles per year).  Always rounded to an
        integer value so the integer flow constraint ``v_{ij} ∈ ℤ`` remains
        feasible.
    area_km2 : float
        Municipality area in km².  Used to estimate intra-district travel
        time — the effective radius ``sqrt(area/π)`` models how long it takes
        to reach the fire once the crew is inside the district boundary.
    wildfire_risk : float
        Wildfire risk level on a continuous scale from ``1.0`` (low/urban) to
        ``5.0`` (extreme/forest).  Controls the hard response-time bound
        ``T_k`` and the quadratic objective weight ``risk_k²``.
    """

    id: str
    name: str
    lat: float
    lon: float
    demand: float
    area_km2: float
    wildfire_risk: float
