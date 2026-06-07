"""Builds the PuLP MILP model for fire station placement in Attica.

Implements the two-stage capacitated facility location formulation
(Klose, 1999) with the following mapping:

  Paper            → Fire protection
  ─────────────────────────────────────────────────────────────────
  Plants (I)       → Fire region (Attica) — single source of trucks
  Depot sites (J)  → Candidate fire stations
  Customers (K)    → Incident districts (aggregated municipalities)
  pi               → Total firetrucks in Attica
  sj               → Firetruck capacity of station j
  dk               → Fire-coverage demand of district k
  ckj              → Estimated response time from station j to district k (minutes)
  fj               → Annual operational cost of station j (EUR)
  yj ∈ {0,1}       → Station j is operational
  zkj ∈ {0,1}      → District k assigned to station j
  vij ∈ ℤ≥0        → Firetrucks deployed from region i to station j

Objective (1):  min Σ wk · ckj · zkj
  wk = dk · risk_k² · ln(area_k)       (WUI-priority composite weight)

Structural constraints added beyond the Klose baseline:
  Budget:           Σ fj·yj  ≤  MAX_BUDGET
  Coverage bound:   Σ_j ckj·zkj  ≤  max_time(risk_k)    ∀k   [hard upper bound]
  Force-open:       yj  = 1                               ∀j ∈ FORCED_OPEN_STATIONS
"""

import math

import pulp

from config.milp_config import (
    AVERAGE_SPEED_KMH,
    DEMAND_WEIGHTED_RESPONSE,
    FORCED_OPEN_STATIONS,
    MAX_BUDGET,
    RISK_COVERAGE_MAX_TIMES,
    WILDFIRE_RISK_WEIGHT,
)
from domain.problem import FireProtectionProblem


def build_model(
    problem: FireProtectionProblem,
) -> tuple[pulp.LpProblem, dict, dict, dict]:
    """Return (model, y_vars, z_vars, v_vars) ready for solving."""
    mdl = pulp.LpProblem("FireProtectionOptimization", pulp.LpMinimize)

    r = problem.region
    J = problem.stations
    K = problem.districts

    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)  # ckj: traffic-adjusted minutes

    # --- Decision variables ---
    y = {s.id: pulp.LpVariable(f"y_{s.id}", cat="Binary") for s in J}

    z = {
        (d.id, s.id): pulp.LpVariable(f"z_{d.id}__{s.id}", cat="Binary")
        for d in K
        for s in J
    }

    v = {
        s.id: pulp.LpVariable(f"v_{r.id}__{s.id}", lowBound=0, cat="Integer")
        for s in J
    }

    # --- Objective (1): WUI-priority composite weight ---
    # wk = dk · risk_k² · ln(area_k)
    #
    # risk² makes the solver non-linearly sensitive to high-risk districts:
    #   risk=5 → 25×, risk=1 → 1× (25x differential vs linear 5x).
    # ln(area) reflects the difficulty of covering a large municipality:
    #   a forest fire in 500 km² needs faster mobilisation than in 4 km².
    # Together they encode Wildland-Urban Interface (WUI) planning priority.
    def _weight(d: object) -> float:
        base = d.demand if DEMAND_WEIGHTED_RESPONSE else 1.0
        if WILDFIRE_RISK_WEIGHT:
            return base * (d.wildfire_risk ** 2) * math.log(max(d.area_km2, 1.0))
        return base

    mdl += (
        pulp.lpSum(_weight(d) * c[(d.id, s.id)] * z[(d.id, s.id)] for d in K for s in J),
        "objective",
    )

    # --- Structural constraints ---

    # Budget: cap total operational cost (Σ fj·yj ≤ MAX_BUDGET)
    if MAX_BUDGET is not None:
        mdl += (
            pulp.lpSum(s.cost * y[s.id] for s in J) <= MAX_BUDGET,
            "budget",
        )

    # Force-open critical perimeter stations: pin y[j] = 1 before the solver runs.
    # These stations are always staffed regardless of budget optimisation heuristics.
    forced = set(FORCED_OPEN_STATIONS)
    for s in J:
        if s.id in forced:
            mdl += y[s.id] == 1, f"force_open_{s.id}"

    # (2) Each district is assigned to exactly one station
    for d in K:
        mdl += (
            pulp.lpSum(z[(d.id, s.id)] for s in J) == 1,
            f"assign_{d.id}",
        )

    # (3) Station capacity: cumulative demand of assigned districts ≤ sj · yj
    for s in J:
        mdl += (
            pulp.lpSum(d.demand * z[(d.id, s.id)] for d in K) <= s.capacity * y[s.id],
            f"capacity_{s.id}",
        )

    # (4) Clique: a district can only be assigned to an open station
    for d in K:
        for s in J:
            mdl += z[(d.id, s.id)] - y[s.id] <= 0, f"clique_{d.id}__{s.id}"

    # (4a) Dynamic coverage time bound (hard upper constraint per district):
    #      Σ_j  c_kj · z_kj  ≤  max_time(risk_k)
    #
    # Because exactly one z_kj = 1 (from constraint 2), this reduces to:
    # "the station assigned to district k must have response time ≤ max_t_k".
    # Using the lpSum form keeps it a valid linear constraint in PuLP.
    for d in K:
        max_t = RISK_COVERAGE_MAX_TIMES.get(d.wildfire_risk)
        if max_t is not None:
            mdl += (
                pulp.lpSum(c[(d.id, s.id)] * z[(d.id, s.id)] for s in J) <= max_t,
                f"max_response_{d.id}",
            )

    # (5) Aggregate capacity — redundant for MIP but strengthens LP relaxation
    mdl += (
        pulp.lpSum(s.capacity * y[s.id] for s in J) >= problem.total_demand,
        "agg_capacity",
    )

    # (6) Supply: total firetrucks deployed ≤ regional fleet size
    mdl += (
        pulp.lpSum(v[s.id] for s in J) <= r.total_firetrucks,
        "supply",
    )

    # (7) Flow conservation: firetrucks at station j = demand it covers
    for s in J:
        mdl += (
            v[s.id] == pulp.lpSum(d.demand * z[(d.id, s.id)] for d in K),
            f"flow_{s.id}",
        )

    # (8) Variable upper bound: v_ij ≤ pi · yj
    for s in J:
        mdl += v[s.id] - r.total_firetrucks * y[s.id] <= 0, f"vub_{s.id}"

    return mdl, y, z, v
