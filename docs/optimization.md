# MILP Formulation Deep-Dive

## Problem Class

The fire station placement problem is formulated as a **Multi-Region Capacitated Facility Location Problem (CFLP)**, extending the classical Klose & Drexl (2005) formulation with:

- Multi-source truck supply (4 ΔΙΠΥ directorates).
- Hard per-district response-time bounds (risk-dependent).
- WUI-priority composite objective weights.
- Geographic proximity penalty to break degeneracy.

---

## Sets and Parameters

| Symbol | Type | Meaning |
|--------|------|---------|
| I | Set | ΔΙΠΥ regional directorates (4 regions) |
| J | Set | Candidate fire station sites |
| K | Set | Incident demand districts |
| π_i | ℤ>0 | Fleet size (firetrucks) of region i |
| s_j | ℤ>0 | Firetruck capacity of station j |
| d_k | ℤ>0 | Fire-coverage demand of district k |
| c_{kj} | ℝ≥0 | Traffic-adjusted response time: station j → district k (minutes) |
| f_j | ℝ>0 | Annual operational cost of station j (EUR) |
| w_k | ℝ>0 | WUI-priority composite weight for district k |
| T_k | ℝ>0 | Hard response-time bound for district k (minutes, risk-dependent) |
| B | ℝ>0 | Maximum annual operational budget (EUR) |
| d_{ij} | ℝ≥0 | Haversine km from ΔΙΠΥ HQ i to station j |
| α | ℝ>0 | Proximity penalty coefficient (`PROXIMITY_ALPHA`) |

---

## Decision Variables

| Variable | Domain | Meaning |
|----------|--------|---------|
| y_j | {0, 1} | 1 if station j is operational |
| z_{kj} | {0, 1} | 1 if district k is assigned to station j |
| v_{ij} | ℤ≥0 | Firetrucks deployed from region i to station j |

---

## Objective Function

```
min  Σ_{k∈K, j∈J}  w_k · c_{kj} · z_{kj}
     + α · Σ_{i∈I, j∈J}  (d_{ij} / max_d) · (v_{ij} / Σπ_i)
```

### Primary term

Minimises the **WUI-priority weighted total response time** across all district–station assignments.

The composite weight is:

```
w_k = d_k · risk_k² · ln(max(area_k, 1))
```

| Factor | Role |
|--------|------|
| d_k | Operational load (mean trucks per incident) |
| risk_k² | Quadratic wildfire priority: risk=5 → 25×, risk=1 → 1× |
| ln(area_k) | Geographic difficulty: 500 km² needs faster response than 4 km² |

The quadratic risk exponent creates a non-linear incentive: the solver is 25× more sensitive to a high-risk district than to a low-risk one, compared to only 5× under a linear formulation.

### Secondary term (proximity penalty)

```
α · Σ_{i,j}  (d_{ij} / max_d) · (v_{ij} / Σπ_i)
```

Breaks solver degeneracy in `v_{ij}` allocation: when multiple feasible allocations yield the same primary objective, the penalty prefers assigning trucks from the geographically nearest ΔΙΠΥ directorate.  Bounded in `[0, α]`, it is always ≪ the primary objective (`O(10⁴)`) and cannot distort station selection decisions.

---

## Constraints

### Structural Constraints

#### Budget

```
Σ_{j∈J}  f_j · y_j  ≤  B
```

Total annual operational cost must not exceed the budget `B`.  Implemented via `config.milp_config.MAX_BUDGET`.  Set `MAX_BUDGET = None` to remove this constraint entirely.

#### Assignment

```
Σ_{j∈J}  z_{kj}  =  1    ∀k ∈ K
```

Every district is covered by **exactly one** station.  This prevents unassigned districts.

#### Capacity

```
Σ_{k∈K}  d_k · z_{kj}  ≤  s_j · y_j    ∀j ∈ J
```

The aggregate demand served by station j cannot exceed its truck capacity, and only open stations (y_j = 1) can take demand.

#### Clique

```
z_{kj}  ≤  y_j    ∀k ∈ K, ∀j ∈ J
```

A district can only be assigned to an **open** station.  Redundant given the capacity constraint but tightens the LP relaxation.

#### Coverage Time Bound

```
Σ_{j∈J}  c_{kj} · z_{kj}  ≤  T_k    ∀k ∈ K
```

Hard upper bound on response time per district.  `T_k` is keyed by the district's `wildfire_risk` value:

| Risk | T_k (minutes) |
|------|--------------|
| 5.0 | 15 |
| 4.5 | 18 |
| 4.0 | 20 |
| 3.5 | 22 |
| 3.0 | 25 |
| ≤ 2.5 | 30 |

If no candidate station can reach district k within T_k, the problem is **Infeasible**.  Use `test/infeasible_diagnostic_tool.py` to identify such districts before solving.

#### Aggregate Capacity

```
Σ_{j∈J}  s_j · y_j  ≥  Σ_{k∈K}  d_k
```

The total capacity of all open stations must cover total demand.  Redundant for MIP but strengthens the LP relaxation bound.

---

### Multi-Region Constraints

#### (6) Supply

```
Σ_{j∈J}  v_{ij}  ≤  π_i    ∀i ∈ I
```

Total firetrucks deployed from region i cannot exceed its fleet.

#### (7) Flow Sufficiency

```
Σ_{i∈I}  v_{ij}  ≥  Σ_{k∈K}  d_k · z_{kj}    ∀j ∈ J
```

Trucks arriving at station j must be sufficient to cover the total demand of its assigned districts.  Uses **≥** (not ==) because `d_k` is a float (mean vehicles) and `v_{ij} ∈ ℤ`: equality would be infeasible whenever the demand sum is non-integer.  With ≥, `v_{ij}` naturally rounds up to `ceil(demand_sum)`, which is physically correct.

#### (8) Variable Upper Bound

```
v_{ij}  ≤  π_i · y_j    ∀i ∈ I, ∀j ∈ J
```

No trucks go to a closed station.

#### (9) Minimum Truck

```
Σ_{i∈I}  v_{ij}  ≥  y_j    ∀j ∈ J
```

Every open station receives at least one firetruck.  Prevents the solver from opening a station as a "coverage anchor" without actually staffing it.  Also tightens the LP relaxation.

---

## Response-Time Matrix (`c_{kj}`)

Computed by `FireProtectionProblem.response_time_matrix(speed_kmh)`:

```
intra_time   = sqrt(area_k / π) / speed · 60 · INTRA_DISTRICT_FACTOR
travel_time  = haversine(k, j) / speed · 60 · traffic_multiplier(j, k)
c_{kj}       = DISPATCH_BASE_MINUTES + travel_time + intra_time
```

| Component | Default | Description |
|-----------|---------|-------------|
| `DISPATCH_BASE_MINUTES` | 1.3 min | Fixed pre-departure time (crew boarding, checks) |
| `INTRA_DISTRICT_FACTOR` | 0.5 | Scales navigation within the district (non-straight roads) |
| `AVERAGE_SPEED_KMH` | 50 km/h | Free-flow travel speed |
| Traffic multiplier | ≥ 1.0 | Peak congestion factor from `traffic_data.json` |

The intra-district term ensures that even a co-located station reports a non-zero response time proportional to the effective municipality radius (`sqrt(area/π)`).

---

## Solver Configuration

| Parameter | Default | Effect |
|-----------|---------|--------|
| `SOLVER_TIME_LIMIT_SECONDS` | 300 | CBC wall-clock time limit |
| `SOLVER_MIP_GAP` | 0.01 | Acceptable MIP optimality gap (1%) |

CBC is invoked via PuLP with `msg=1` so its branch-and-bound log is printed to stdout.  The result status is extracted from `pulp.LpStatus[model.status]`.

---

## Infeasibility Handling

If `model.status == -1` (INFEASIBLE), `solver.py` returns a sentinel `OptimizationResult` with:

- `status = "Infeasible"`
- `objective_value = float("inf")`
- All collections empty

A CRITICAL log message is emitted.  `main.py` checks `result.status != "Optimal"` and exits cleanly without generating maps or reports.

**Common causes of infeasibility:**

1. A district with wildfire_risk=5.0 (T_k=15 min) is more than 15 minutes from every candidate station.
2. Total station capacity `Σ s_j · y_j` is less than total demand `Σ d_k` under the budget constraint.

Use `python test/infeasible_diagnostic_tool.py` to diagnose cause (1) before solving.

---

## Forced-Open Stations

```python
FORCED_OPEN_STATIONS: list[str] = ["ps_marathon", "ps_lavrio"]
```

Variables `y[j]` for stations in this list are pinned to 1 before the solver runs via equality constraints.  They are operational regardless of budget optimisation.
