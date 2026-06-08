"""MILP solver settings and fire-protection problem parameters.

All tunable knobs live here so callers never hard-code numeric constants.
"""

from typing import Any

# --- Solver ---
SOLVER_TIME_LIMIT_SECONDS = 300
SOLVER_MIP_GAP = 0.01  # 1 % optimality gap is acceptable for planning

# --- Fire regions (4 ΔΙΠΥ — Regional Directorates of the Fire Service) ---
# Each dict must contain: id (str), name (str), total_firetrucks (int).
REGIONS: list[dict[str, Any]] = [
    {"id": "dipy_athens",  "name": "ΔΙΠΥ ΑΘΗΝΩΝ",             "total_firetrucks": 120},
    {"id": "dipy_piraeus", "name": "ΔΙΠΥ ΠΕΙΡΑΙΩΣ",           "total_firetrucks": 40},
    {"id": "dipy_west",    "name": "ΔΙΠΥ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ",    "total_firetrucks": 45},
    {"id": "dipy_east",    "name": "ΔΙΠΥ ΑΝΑΤΟΛΙΚΗΣ ΑΤΤΙΚΗΣ", "total_firetrucks": 45},
]

# --- Backward-compatibility aliases (used by legacy callers) ---
REGION_ID = REGIONS[0]["id"]
REGION_NAME = str(REGIONS[0]["name"])
REGION_TOTAL_FIRETRUCKS: int = sum(int(r["total_firetrucks"]) for r in REGIONS)

# --- Fire station defaults (overridden per-station in fire_stations.json) ---
STATION_DEFAULT_CAPACITY = 15    # sj: firetruck slots per station
STATION_DEFAULT_COST = 800_000.0  # fj: annual operating cost in EUR

# --- Response-time estimation ---
AVERAGE_SPEED_KMH = 50.0  # used to convert Haversine distance → minutes (ckj)

# Fixed pre-departure time added to every route unconditionally:
# crew boarding, vehicle checks, and clearing the station bay.
DISPATCH_BASE_MINUTES = 1.3

# Scaling factor for intra-district travel time.
# A district's area is modelled as a circle; the effective radius is
# sqrt(area_km2 / π). The crew must navigate from the district boundary
# (or centroid for a co-located station) to the fire within the district.
# 0.5 calibrates for non-straight roads and typical urban density.
INTRA_DISTRICT_FACTOR = 0.5

# How to aggregate traffic multipliers across the 6 daily time slots:
#   "worst_case" → use max slot multiplier — optimises for peak congestion
#   "average"    → use mean slot multiplier — optimises expected response time
TRAFFIC_STRATEGY = "worst_case"

# --- Objective ---
# Primary: minimize demand-weighted total response time (Σ dk·ckj·zkj).
DEMAND_WEIGHTED_RESPONSE = True

# When True, multiply each district's objective weight by its wildfire_risk_factor
# (1.0 = low/urban, 5.0 = extreme/forest). High-risk areas are then prioritised
# more strongly by the solver when deciding which station to assign and open.
WILDFIRE_RISK_WEIGHT = True

# Maximum total annual operational cost (EUR) — budget constraint (Σ fj·yj ≤ MAX_BUDGET).
# Set to None to remove the budget limit and let the solver decide freely.
# Higher budget → more stations open → lower average response times.
MAX_BUDGET: float | None = 8_000_000.0  # EUR — allows roughly 18 stations
# MAX_BUDGET = None  # no budget limit

# --- Dynamic coverage time bounds (hard response-time constraints) ---
# Maximum permissible response time (minutes) per district, keyed by wildfire_risk_factor.
# Enforced as:  Σ_j  c_kj · z_kj  ≤  max_t_k   for every district k.
# If no candidate station can reach a district within its limit the problem is Infeasible
# and the solver will report it — see OptimizationResult.status and solver logs.
RISK_COVERAGE_MAX_TIMES: dict[float, float] = {
    5.0: 15.0,
    4.5: 18.0,
    4.0: 20.0,
    3.5: 22.0,
    3.0: 25.0,
    2.5: 30.0,
    2.0: 30.0,
    1.5: 30.0,
    1.0: 30.0,
}

# --- Forced-open perimeter stations ---
# These y[i] variables are pinned to 1 before the solver runs.
# Use for strategically critical locations that must always be staffed
# regardless of budget optimisation heuristics.
FORCED_OPEN_STATIONS: list[str] = [
    # "ps_marathon",
    # "ps_lavrio",
    # "ps_megara",
    # "ps_acharnes",
]

# --- Demand metric: how dk is computed from incident history ---
# "mean_vehicles"  → average firetrucks deployed per incident in the district
# "incident_count" → raw number of incidents (each treated as 1 unit of demand)
# "total_vehicles" → cumulative firetrucks deployed over the year
DEMAND_METRIC = "mean_vehicles"
