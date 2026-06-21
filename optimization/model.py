"""Builds the PuLP MILP model for fire station placement in Attica.

Multi-region capacitated facility location formulation (extended Klose, 1999):

  Paper            → Fire protection
  ─────────────────────────────────────────────────────────────────
  Plants (I)       → ΔΙΠΥ regional directorates — multiple sources of trucks
  Depot sites (J)  → Candidate fire stations
  Customers (K)    → Incident districts (aggregated municipalities)
  π_i              → Fleet size of ΔΙΠΥ region i
  s_j              → Firetruck capacity of station j
  d_k              → Fire-coverage demand of district k
  c_{kj}           → Estimated response time from station j to district k (min)
  f_j              → Annual operational cost of station j (EUR)
  y_j ∈ {0,1}      → Station j is operational
  z_{kj} ∈ {0,1}   → District k assigned to station j
  v_{ij} ∈ ℤ≥0     → Firetrucks deployed from region i to station j

Objective
---------
Primary (1):  min Σ w_k · c_{kj} · z_{kj}
  w_k = d_k · risk_k² · ln(area_k)          (WUI-priority composite weight)
Secondary:    + α · Σ_{i,j} (dist_{ij}/max_dist) · (v_{ij}/total_fleet)
  Breaks degeneracy in v-allocation without distorting station selection.
  Bounded in [0, α] ≪ primary objective O(10⁴).

Structural constraints
----------------------
  Budget:          Σ f_j·y_j ≤ MAX_BUDGET
  Assignment:      Σ_j z_{kj} = 1                    ∀k
  Capacity:        Σ_k d_k·z_{kj} ≤ s_j·y_j          ∀j
  Clique:          z_{kj} ≤ y_j                       ∀k, j
  Coverage bound:  Σ_j c_{kj}·z_{kj} ≤ T_k           ∀k   [hard upper bound]
  Agg. capacity:   Σ_j s_j·y_j ≥ Σ_k d_k

Multi-region constraints
------------------------
  (6) Supply:    Σ_j v_{ij} ≤ π_i                    ∀i ∈ I
  (7) Flow:      Σ_i v_{ij} ≥ Σ_k d_k·z_{kj}         ∀j ∈ J
      [≥ not ==: d_k is float, v is integer — equality is infeasible when
       demand sums are non-integer. ≥ forces sufficient integer coverage.]
  (8) VUB:       v_{ij} ≤ π_i · y_j                  ∀i, j
  (9) Min-truck: Σ_i v_{ij} ≥ y_j                    ∀j ∈ J
"""

import math

import pulp

from config.milp_config import (
    AVERAGE_SPEED_KMH,
    DEMAND_WEIGHTED_RESPONSE,
    FORCED_OPEN_STATIONS,
    MAX_BUDGET,
    PROXIMITY_ALPHA,
    RISK_COVERAGE_MAX_TIMES,
    WILDFIRE_RISK_WEIGHT,
)
from domain.problem import FireProtectionProblem


def _weight(d: object) -> float:
    """Compute the WUI-priority composite objective weight for district *d*.

    The weight encodes three planning signals:

    * **d_k** (demand) — operational load; how many trucks an incident
      typically needs in this district.
    * **risk_k²** — quadratic wildfire risk penalty; a district with
      ``risk=5`` receives 25× the weight of ``risk=1`` (vs. 5× under a
      linear formulation), making the solver non-linearly sensitive to
      high-risk zones.
    * **ln(area_k)** — geographic coverage difficulty; a forest fire in
      500 km² needs faster mobilisation than one in 4 km².

    Parameters
    ----------
    d : object
        Any object with ``demand`` (float), ``wildfire_risk`` (float), and
        ``area_km2`` (float) attributes — in practice an
        ``IncidentDistrict``.

    Returns
    -------
    float
        Composite WUI weight ``w_k``.
    """
    base = d.demand if DEMAND_WEIGHTED_RESPONSE else 1.0  # type: ignore[union-attr]
    if WILDFIRE_RISK_WEIGHT:
        return base * (d.wildfire_risk ** 2) * math.log(max(d.area_km2, 1.0))  # type: ignore[union-attr]
    return base


def build_model(
    problem: FireProtectionProblem,
    *,
    max_budget: float | None = None,
) -> tuple[pulp.LpProblem, dict, dict, dict]:
    """Construct the fire-protection MILP and return it ready for solving.

    Builds a ``pulp.LpProblem`` with all decision variables and the nine
    constraint groups described in the module docstring.  The returned
    variable dicts use the same key conventions as ``OptimizationResult``
    so that solution extraction in ``solver.py`` is straightforward.

    Parameters
    ----------
    problem : FireProtectionProblem
        Multi-region problem definition carrying regions, stations, and
        districts.
    max_budget : float or None, optional
        If provided, overrides ``config.milp_config.MAX_BUDGET``.  Pass
        ``None`` (default) to use the config value.  Set to ``0.0`` or a
        very large number to effectively disable the budget constraint.

    Returns
    -------
    tuple[pulp.LpProblem, dict, dict, dict]
        A four-tuple ``(model, y, z, v)`` where:

        * ``model`` — the fully constructed ``LpProblem`` ready for
          ``model.solve()``.
        * ``y`` — ``{station_id: LpVariable}`` binary open/close variables.
        * ``z`` — ``{(district_id, station_id): LpVariable}`` binary
          assignment variables.
        * ``v`` — ``{(region_id, station_id): LpVariable}`` integer truck
          allocation variables.
    """
    mdl = pulp.LpProblem("FireProtectionOptimization", pulp.LpMinimize)

    I = problem.regions     # ΔΙΠΥ directorates
    J = problem.stations    # Candidate stations
    K = problem.districts   # Demand districts

    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)
    region_station_dists = problem.region_station_distance_matrix()

    _max_dist: float = max(region_station_dists.values(), default=1.0)
    _total_fleet: float = float(problem.total_fleet) or 1.0

    # --- Decision variables ---

    y: dict[str, pulp.LpVariable] = {
        s.id: pulp.LpVariable(f"y_{s.id}", cat="Binary")
        for s in J
    }

    z: dict[tuple[str, str], pulp.LpVariable] = {
        (d.id, s.id): pulp.LpVariable(f"z_{d.id}__{s.id}", cat="Binary")
        for d in K
        for s in J
    }

    v: dict[tuple[str, str], pulp.LpVariable] = {
        (r.id, s.id): pulp.LpVariable(f"v_{r.id}__{s.id}", lowBound=0, cat="Integer")
        for r in I
        for s in J
    }

    # --- Objective ---

    mdl += (
        pulp.lpSum(_weight(d) * c[(d.id, s.id)] * z[(d.id, s.id)] for d in K for s in J)
        + PROXIMITY_ALPHA * pulp.lpSum(
            (region_station_dists[(r.id, s.id)] / _max_dist)
            * (v[(r.id, s.id)] / _total_fleet)
            for r in I
            for s in J
        ),
        "objective",
    )

    # --- Structural constraints ---

    effective_budget = max_budget if max_budget is not None else MAX_BUDGET
    if effective_budget is not None:
        mdl += (
            pulp.lpSum(s.cost * y[s.id] for s in J) <= effective_budget,
            "budget",
        )

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

    # (3) Station capacity: cumulative demand of assigned districts ≤ s_j · y_j
    for s in J:
        mdl += (
            pulp.lpSum(d.demand * z[(d.id, s.id)] for d in K) <= s.capacity * y[s.id],
            f"capacity_{s.id}",
        )

    # (4) Clique: a district can only be assigned to an open station
    for d in K:
        for s in J:
            mdl += z[(d.id, s.id)] - y[s.id] <= 0, f"clique_{d.id}__{s.id}"

    # (4a) Dynamic coverage time bound: Σ_j c_{kj}·z_{kj} ≤ T_k
    for d in K:
        max_t = RISK_COVERAGE_MAX_TIMES.get(d.wildfire_risk)
        if max_t is not None:
            mdl += (
                pulp.lpSum(c[(d.id, s.id)] * z[(d.id, s.id)] for s in J) <= max_t,
                f"max_response_{d.id}",
            )

    # (5) Aggregate capacity — strengthens LP relaxation
    mdl += (
        pulp.lpSum(s.capacity * y[s.id] for s in J) >= problem.total_demand,
        "agg_capacity",
    )

    # === Multi-region constraints ===

    # (6) Supply: Σ_j v_{ij} ≤ π_i   ∀i ∈ I
    for r in I:
        mdl += (
            pulp.lpSum(v[(r.id, s.id)] for s in J) <= r.total_firetrucks,
            f"supply_{r.id}",
        )

    # (7) Flow sufficiency: Σ_i v_{ij} ≥ Σ_k d_k · z_{kj}   ∀j ∈ J
    #     Uses ≥ because d_k is float and v is Integer: equality would be
    #     infeasible when demand sums are non-integer.  With ≥, v rounds up
    #     to ceil(demand_sum), which is physically correct (no half-trucks).
    for s in J:
        mdl += (
            pulp.lpSum(v[(r.id, s.id)] for r in I)
            >= pulp.lpSum(d.demand * z[(d.id, s.id)] for d in K),
            f"flow_{s.id}",
        )

    # (8) Variable upper bound: v_{ij} ≤ π_i · y_j   ∀i, j
    for r in I:
        for s in J:
            mdl += (
                v[(r.id, s.id)] - r.total_firetrucks * y[s.id] <= 0,
                f"vub_{r.id}__{s.id}",
            )

    # (9) Minimum-truck: every open station must have ≥ 1 firetruck
    for s in J:
        mdl += (
            pulp.lpSum(v[(r.id, s.id)] for r in I) >= 1 * y[s.id],
            f"min_truck_{s.id}",
        )

    return mdl, y, z, v
