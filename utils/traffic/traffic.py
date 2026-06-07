"""Congestion-aware multiplier lookup for station→district routes.

Traffic profiles (from traffic_data.json) are indexed by road axis and contain
six time-slot multipliers:
  slot 0: 00:00-06:00  (Night / fluid)
  slot 1: 06:00-09:00  (Morning rush — typically the worst)
  slot 2: 09:00-14:00  (Mid-day inter-peak)
  slot 3: 14:00-17:00  (Afternoon school/work rush)
  slot 4: 17:00-21:00  (Evening retail/commute)
  slot 5: 21:00-00:00  (Night / smooth)

Each (station, district) pair is mapped to one profile via its geographic midpoint.
"""

import json
import os
from functools import lru_cache

from config.milp_config import TRAFFIC_STRATEGY

_TRAFFIC_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "traffic_data.json"
)


@lru_cache(maxsize=1)
def load_traffic_data() -> dict:
    with open(_TRAFFIC_FILE, encoding="utf-8") as f:
        return json.load(f)


def _assign_profile(mid_lat: float, mid_lon: float) -> str:
    """Map a route midpoint to the dominant Attica traffic axis.

    The zones below reflect the major road axes in the region:
      CENTER_URBAN   — dense central Athens grid (Omonia, Syntagma, Kolonaki belt)
      KIFISIAS_AXIS  — northern suburb corridor (Kifisias Ave towards Kifisia/Marousi)
      KIFISOU_AXIS   — NW industrial/residential corridor (Kifisou Ave towards Peristeri)
      ATTIKI_ODOS    — east-west motorway (most reliable, lowest peak multiplier)
      POSEIDONOS_AVEN— southern coastal road (evening rush saturates heavily)
      ATHINON_AVENUE — western approach towards Elefsina/Megara
      MESOGEION_AXIS — eastern Mesogeion Ave towards Spata/airport
      RURAL_SUBURBAN — outer Attica and fringe zones
    """
    # Dense urban Athens core
    if 37.93 <= mid_lat <= 38.05 and 23.68 <= mid_lon <= 23.80:
        return "CENTER_URBAN"
    # Northern Kifisia corridor (lat-bounded so Marathon/Oropos fall through)
    if 38.04 < mid_lat <= 38.16 and 23.77 <= mid_lon <= 23.90:
        return "KIFISIAS_AXIS"
    # NW Kifisou/Peristeri corridor (lon-bounded so Elefsina/Megara fall through)
    if 37.97 <= mid_lat <= 38.06 and 23.62 <= mid_lon < 23.68:
        return "KIFISOU_AXIS"
    # East via Attica motorway
    if 37.99 <= mid_lat <= 38.12 and mid_lon > 23.80:
        return "ATTIKI_ODOS"
    # Eastern (Mesogeion axis / Lavrio) — checked BEFORE coastal south to
    # prevent lon > 23.83 eastern routes being misclassified as Poseidonos Ave
    if mid_lon > 23.83:
        return "MESOGEION_AXIS"
    # Southern coastal road (Glyfada–Voula–Alimos band only, lon-bounded)
    if mid_lat < 37.93 and 23.69 <= mid_lon <= 23.80:
        return "POSEIDONOS_AVEN"
    # Western approach towards Elefsina/Megara
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

    Strategy (set in config.milp_config.TRAFFIC_STRATEGY):
      "worst_case" — max across all time slots; optimises for peak congestion
      "average"    — mean across slots; optimises expected response time
    """
    profiles = load_traffic_data()["traffic_profiles"]
    mid_lat = (station_lat + district_lat) / 2
    mid_lon = (station_lon + district_lon) / 2
    slots = profiles[_assign_profile(mid_lat, mid_lon)]

    if TRAFFIC_STRATEGY == "worst_case":
        return max(slots)
    return sum(slots) / len(slots)
