"""Congestion-aware multiplier lookup for station → district routes.

Traffic profiles (from ``traffic_data.json``) are indexed by road axis and
contain six time-slot multipliers:

  ====  ============================
  Slot  Time window
  ====  ============================
  0     00:00–06:00  (Night / fluid)
  1     06:00–09:00  (Morning rush)
  2     09:00–14:00  (Mid-day inter-peak)
  3     14:00–17:00  (Afternoon school/work rush)
  4     17:00–21:00  (Evening retail/commute)
  5     21:00–00:00  (Night / smooth)
  ====  ============================

Each ``(station, district)`` pair is mapped to one profile via its geographic
midpoint.  The aggregation strategy (worst-case peak vs. average) is
controlled by ``config.milp_config.TRAFFIC_STRATEGY``.
"""

import json
import os
from functools import lru_cache

from config.milp_config import TRAFFIC_STRATEGY

_TRAFFIC_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "json", "traffic_data.json"
)


@lru_cache(maxsize=1)
def load_traffic_data() -> dict:
    """Load and cache the traffic profiles from ``traffic_data.json``.

    The file is parsed exactly once per interpreter session; subsequent calls
    return the cached dict.  The ``lru_cache`` is invalidated only when the
    interpreter restarts, which is acceptable for batch optimisation runs.

    Returns
    -------
    dict
        The parsed JSON object with a ``"traffic_profiles"`` key mapping road
        axis names to lists of six congestion multipliers.

    Raises
    ------
    FileNotFoundError
        If ``traffic_data.json`` does not exist at the expected path.
    json.JSONDecodeError
        If the file is not valid JSON.
    """
    with open(_TRAFFIC_FILE, encoding="utf-8") as f:
        return json.load(f)


def _assign_profile(mid_lat: float, mid_lon: float) -> str:
    """Map a route midpoint to the dominant Attica traffic axis.

    Uses a sequence of bounding-box tests against the eight major road
    corridors in the Attica region:

    * ``CENTER_URBAN``   — dense central Athens grid (Omonia, Syntagma,
      Kolonaki belt).
    * ``KIFISIAS_AXIS``  — northern suburb corridor (Kifisias Ave towards
      Kifisia / Marousi).
    * ``KIFISOU_AXIS``   — NW industrial/residential corridor (Kifisou Ave
      towards Peristeri).
    * ``ATTIKI_ODOS``    — east-west motorway (lowest peak multiplier).
    * ``MESOGEION_AXIS`` — eastern Mesogeion Ave towards Spata / airport.
    * ``POSEIDONOS_AVEN``— southern coastal road (Glyfada–Voula–Alimos).
    * ``ATHINON_AVENUE`` — western approach towards Elefsina / Megara.
    * ``RURAL_SUBURBAN`` — outer Attica and fringe zones (catch-all).

    Parameters
    ----------
    mid_lat : float
        Latitude of the route midpoint in WGS 84 decimal degrees.
    mid_lon : float
        Longitude of the route midpoint in WGS 84 decimal degrees.

    Returns
    -------
    str
        One of the eight road-axis profile keys used in ``traffic_data.json``.
    """
    if 37.93 <= mid_lat <= 38.05 and 23.68 <= mid_lon <= 23.80:
        return "CENTER_URBAN"
    if 38.04 < mid_lat <= 38.16 and 23.77 <= mid_lon <= 23.90:
        return "KIFISIAS_AXIS"
    if 37.97 <= mid_lat <= 38.06 and 23.62 <= mid_lon < 23.68:
        return "KIFISOU_AXIS"
    if 37.99 <= mid_lat <= 38.12 and mid_lon > 23.80:
        return "ATTIKI_ODOS"
    if mid_lon > 23.83:
        return "MESOGEION_AXIS"
    if mid_lat < 37.93 and 23.69 <= mid_lon <= 23.80:
        return "POSEIDONOS_AVEN"
    if mid_lon < 23.62:
        return "ATHINON_AVENUE"
    return "RURAL_SUBURBAN"


def route_multiplier(
    station_lat: float,
    station_lon: float,
    district_lat: float,
    district_lon: float,
) -> float:
    """Return the congestion multiplier for a station → district route.

    Computes the geographic midpoint of the route, maps it to a road-axis
    profile via :func:`_assign_profile`, and aggregates the six time-slot
    multipliers using the strategy configured in
    ``config.milp_config.TRAFFIC_STRATEGY``.

    Parameters
    ----------
    station_lat : float
        Latitude of the fire station in WGS 84 decimal degrees.
    station_lon : float
        Longitude of the fire station in WGS 84 decimal degrees.
    district_lat : float
        Latitude of the district centroid in WGS 84 decimal degrees.
    district_lon : float
        Longitude of the district centroid in WGS 84 decimal degrees.

    Returns
    -------
    float
        A dimensionless congestion factor ``≥ 1.0`` by which the free-flow
        travel time is multiplied.  Under ``"worst_case"`` this is the
        maximum across all six time slots; under ``"average"`` it is the
        arithmetic mean.
    """
    profiles = load_traffic_data()["traffic_profiles"]
    mid_lat = (station_lat + district_lat) / 2
    mid_lon = (station_lon + district_lon) / 2
    slots = profiles[_assign_profile(mid_lat, mid_lon)]

    if TRAFFIC_STRATEGY == "worst_case":
        return max(slots)
    return sum(slots) / len(slots)
