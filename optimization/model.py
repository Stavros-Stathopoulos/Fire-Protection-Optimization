"""Builds the PuLP MILP model for fire station placement in Attica.

Multi-region capacitated facility location formulation (extended Klose, 1999):

  Paper            → Fire protection
  ─────────────────────────────────────────────────────────────────
  Plants (I)       → ΔΙΠΥ regional directorates — multiple sources of trucks
  Depot sites (J)  → Candidate fire stations
  Customers (K)    → Incident districts (aggregated municipalities)
  pi               → Fleet size of ΔΙΠΥ region i
  sj               → Firetruck capacity of station j
  dk               → Fire-coverage demand of district k
  ckj              → Estimated response time from station j to district k (minutes)
  fj               → Annual operational cost of station j (EUR)
  yj ∈ {0,1}       → Station j is operational
  zkj ∈ {0,1}      → District k assigned to station j
  vij ∈ ℤ≥0        → Firetrucks deployed from region i to station j

Objective (1):  min Σ wk · ckj · zkj
  wk = dk · risk_k² · ln(area_k)       (WUI-priority composite weight)

Structural constraints:
  Budget:           Σ fj·yj  ≤  MAX_BUDGET
  Coverage bound:   Σ_j ckj·zkj  ≤  max_time(risk_k)    ∀k   [hard upper bound]
  Force-open:       yj  = 1                               ∀j ∈ FORCED_OPEN_STATIONS

Multi-region constraints:
  (6) Supply:       Σ_j vij  ≤  pi                        ∀i ∈ I
  (7) Flow:         Σ_i vij  == Σ_k dk·zkj                ∀j ∈ J
  (8) VUB:          vij  ≤  pi · yj                       ∀i,j
  (9) Min-truck:    Σ_i vij  ≥  1 · yj                    ∀j ∈ J
"""

import math
from typing import Optional

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
    *,
    max_budget: Optional[float] = None,
) -> tuple[pulp.LpProblem, dict, dict, dict]:
    """Return (model, y_vars, z_vars, v_vars) ready for solving.

    Parameters
    ----------
    problem:
        Multi-region ``FireProtectionProblem``.
    max_budget:
        If provided, overrides ``config.milp_config.MAX_BUDGET``.
        Pass ``None`` to use the config default.
    """
    mdl = pulp.LpProblem("FireProtectionOptimization", pulp.LpMinimize)

    I = problem.regions     # ΔΙΠΥ directorates
    J = problem.stations    # Candidate stations
    K = problem.districts   # Demand districts

    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)  # ckj: traffic-adjusted minutes

    # --- Decision variables ---

    # yj ∈ {0,1}: station j is operational
    y: dict[str, pulp.LpVariable] = {
        s.id: pulp.LpVariable(f"y_{s.id}", cat="Binary")
        for s in J
    }

    # zkj ∈ {0,1}: district k assigned to station j
    z: dict[tuple[str, str], pulp.LpVariable] = {
        (d.id, s.id): pulp.LpVariable(f"z_{d.id}__{s.id}", cat="Binary")
        for d in K
        for s in J
    }

    # vij ∈ ℤ≥0: firetrucks deployed from region i to station j
    v: dict[tuple[str, str], pulp.LpVariable] = {
        (r.id, s.id): pulp.LpVariable(f"v_{r.id}__{s.id}", lowBound=0, cat="Integer")
        for r in I
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
        base = d.demand if DEMAND_WEIGHTED_RESPONSE else 1.0  # type: ignore[union-attr]
        if WILDFIRE_RISK_WEIGHT:
            return base * (d.wildfire_risk ** 2) * math.log(max(d.area_km2, 1.0))  # type: ignore[union-attr]
        return base

    mdl += (
        pulp.lpSum(_weight(d) * c[(d.id, s.id)] * z[(d.id, s.id)] for d in K for s in J),
        "objective",
    )

    # --- Structural constraints ---

    # Budget: cap total operational cost (Σ fj·yj ≤ budget)
    effective_budget = max_budget if max_budget is not None else MAX_BUDGET
    if effective_budget is not None:
        mdl += (
            pulp.lpSum(s.cost * y[s.id] for s in J) <= effective_budget,
            "budget",
        )

    # Force-open critical perimeter stations: pin y[j] = 1 before the solver runs.
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

    # === Multi-region constraints ===

    # (6) Supply: total firetrucks deployed from region i ≤ that region's fleet
    #     Σ_j v_{ij} ≤ pi   ∀i ∈ I
    for r in I:
        mdl += (
            pulp.lpSum(v[(r.id, s.id)] for s in J) <= r.total_firetrucks,
            f"supply_{r.id}",
        )

    # (7) Flow conservation: trucks arriving at station j from ALL regions
    #     must equal the aggregate demand of districts assigned to j
    #     Σ_i v_{ij} == Σ_k dk · z_{kj}   ∀j ∈ J
    for s in J:
        mdl += (
            pulp.lpSum(v[(r.id, s.id)] for r in I)
            == pulp.lpSum(d.demand * z[(d.id, s.id)] for d in K),
            f"flow_{s.id}",
        )

    # (8) Variable upper bound: v_{ij} ≤ pi · yj   ∀i,j
    for r in I:
        for s in J:
            mdl += (
                v[(r.id, s.id)] - r.total_firetrucks * y[s.id] <= 0,
                f"vub_{r.id}__{s.id}",
            )

    # (9) Minimum-truck operational threshold: if a station is open,
    #     it must have at least 1 firetruck assigned to it.
    #     Σ_i v_{ij} ≥ 1 · yj   ∀j ∈ J
    for s in J:
        mdl += (
            pulp.lpSum(v[(r.id, s.id)] for r in I) >= 1 * y[s.id],
            f"min_truck_{s.id}",
        )

    return mdl, y, z, v
