# Fire-Protection-Optimization

> **Multi-Region Capacitated Facility Location via Mixed-Integer Linear Programming for Optimal Fire Station Placement in Attica, Greece**

Final project for course **ECE_CK806 — Linear & Combinatorial Optimization**  
Spring Semester, Academic Year 2025–2026

---

## Table of Contents

1. [Overview](#overview)
2. [Mathematical Formulation](#mathematical-formulation)
   - [Sets & Parameters](#sets--parameters)
   - [Decision Variables](#decision-variables)
   - [Objective Function](#objective-function)
   - [Constraints](#constraints)
3. [Project Structure](#project-structure)
4. [Installation](#installation)
5. [Data Files](#data-files)
6. [Configuration Reference](#configuration-reference)
7. [Usage](#usage)
   - [Running the Optimizer](#1-running-the-optimizer)
   - [Generating the Interactive Map](#2-generating-the-interactive-map)
   - [Advanced Visualization Module](#3-advanced-visualization-module)
   - [Loading a Saved Result](#4-loading-a-saved-result)
8. [Output Format](#output-format)
9. [Architecture Overview](#architecture-overview)
10. [Academic Context](#academic-context)

---

## Overview

This project solves the **fire station placement problem** for the **Region of Attica, Greece** as a **Multi-Region Capacitated Facility Location Problem (CFLP)** formulated as a Mixed-Integer Linear Program (MILP) and solved with the [PuLP](https://coin-or.github.io/pulp/) / CBC solver.

### Problem statement

Given a set of candidate station sites, a set of demand districts (municipalities), and four regional fire-service directorates (ΔΙΠΥ) each with a fixed fleet of firetrucks, the optimizer selects:

- **which stations to open** (subject to a budget cap),
- **which district each open station covers**, and
- **how many trucks each ΔΙΠΥ directorate deploys to each open station**,

so as to **minimize demand-weighted average response time** across all districts while respecting fleet supply limits, station capacities, coverage time hard bounds, and operational minimum-truck requirements.

### The four ΔΙΠΥ Regional Directorates

| ID | Name | Fleet |
| ---- | ------ | ------: |
| `dipy_athens` | ΔΙΠΥ ΑΘΗΝΩΝ | 120 trucks |
| `dipy_piraeus` | ΔΙΠΥ ΠΕΙΡΑΙΩΣ | 40 trucks |
| `dipy_west` | ΔΙΠΥ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ | 45 trucks |
| `dipy_east` | ΔΙΠΥ ΑΝΑΤΟΛΙΚΗΣ ΑΤΤΙΚΗΣ | 45 trucks |
| | **Total** | **250 trucks** |

---

## Mathematical Formulation

The model extends the classical Klose & Drexl (1999) capacitated facility location formulation with multi-source supply, hard response-time bounds, and an operational minimum-truck constraint.

### Sets & Parameters

| Symbol | Meaning |
| -------- | --------- |
| $I$ | Set of ΔΙΠΥ regional directorates (4 regions) |
| $J$ | Set of candidate fire station sites |
| $K$ | Set of incident demand districts |
| $\pi_i$ | Fleet size (firetrucks) of region $i$ |
| $s_j$ | Firetruck capacity of station $j$ |
| $d_k$ | Fire-coverage demand of district $k$ (units: mean vehicles per incident) |
| $c_{kj}$ | Traffic-adjusted response time from station $j$ to district $k$ (minutes) |
| $f_j$ | Annual operational cost of station $j$ (EUR) |
| $w_k$ | WUI-priority composite weight: $w_k = d_k \cdot \text{risk}_k^2 \cdot \ln(\max(\text{area}_k, 1))$ |
| $B$ | Maximum annual operational budget (EUR) |

### Decision Variables

| Variable | Domain | Meaning |
| ---------- | -------- | --------- |
| $y_j$ | $\{0, 1\}$ | 1 if station $j$ is operational |
| $z_{kj}$ | $\{0, 1\}$ | 1 if district $k$ is assigned to station $j$ |
| $v_{ij}$ | $\mathbb{Z}_{\geq 0}$ | Firetrucks deployed from region $i$ to station $j$ |

### Objective Function

$$\min \sum_{k \in K} \sum_{j \in J} w_k \cdot c_{kj} \cdot z_{kj}$$

Minimizes the **WUI-priority weighted total response time** across all district–station assignments.

The composite weight $w_k = d_k \cdot \text{risk}_k^2 \cdot \ln(\text{area}_k)$ encodes:
- **$d_k$** — operational load (how many trucks an incident typically needs),
- **$\text{risk}_k^2$** — quadratic wildfire risk penalty (risk=5 → 25× priority vs. risk=1 → 1×),
- **$\ln(\text{area}_k)$** — geographic coverage difficulty (larger municipality ≈ harder to reach the fire).

### Constraints

#### Structural

| # | Constraint | Meaning |
| --- | ----------- | --------- |
| Budget | $\sum_{j \in J} f_j y_j \leq B$ | Total operational cost stays within budget |
| Assignment | $\sum_{j \in J} z_{kj} = 1 \quad \forall k$ | Every district is covered by exactly one station |
| Capacity | $\sum_{k \in K} d_k z_{kj} \leq s_j y_j \quad \forall j$ | Demand assigned to $j$ cannot exceed its firetruck capacity |
| Clique | $z_{kj} \leq y_j \quad \forall k, j$ | A district can only be assigned to an open station |
| Coverage time | $\sum_{j \in J} c_{kj} z_{kj} \leq T_k \quad \forall k$ | Hard upper bound on response time per district (depends on risk level) |
| Agg. capacity | $\sum_{j \in J} s_j y_j \geq \sum_{k \in K} d_k$ | Enough total capacity exists across all open stations |

#### Multi-Region

| # | Constraint | Meaning |
| --- | ----------- | --------- |
| (6) Supply | $\sum_{j \in J} v_{ij} \leq \pi_i \quad \forall i$ | Total trucks deployed from region $i$ cannot exceed its fleet |
| (7) Flow | $\sum_{i \in I} v_{ij} = \sum_{k \in K} d_k z_{kj} \quad \forall j$ | Trucks arriving at station $j$ exactly cover the demand of its assigned districts |
| (8) VUB | $v_{ij} \leq \pi_i \cdot y_j \quad \forall i, j$ | No trucks go to a closed station |
| (9) Min-truck | $\sum_{i \in I} v_{ij} \geq y_j \quad \forall j$ | Every open station receives at least 1 firetruck |

#### Response-Time Hard Bounds $T_k$

| Wildfire risk | $T_k$ (minutes) |
| :---: | ---: |
| 5.0 (extreme / forest) | 15 |
| 4.5 | 18 |
| 4.0 | 20 |
| 3.5 | 22 |
| 3.0 | 25 |
| ≤ 2.5 | 30 |

---

## Project Structure

```
Fire-Protection-Optimization/
│
├── main.py                         # CLI entry point — runs the optimizer
│
├── config/
│   ├── __init__.py                 # Re-exports all config constants
│   ├── milp_config.py              # All MILP tuning knobs (budget, fleet sizes, etc.)
│   ├── data_config.py              # Data file paths and column mappings
│   └── env_config.py               # Environment flags (DEBUG, LOG_LEVEL)
│
├── domain/
│   ├── entities.py                 # Frozen dataclasses: FireRegion, FireStation, IncidentDistrict
│   └── problem.py                  # FireProtectionProblem — assembles parameter matrices
│
├── optimization/
│   ├── model.py                    # Builds the PuLP MILP model (all constraints)
│   ├── solver.py                   # Runs CBC, extracts and returns OptimizationResult
│   └── result.py                   # OptimizationResult dataclass + JSON serialization
│
├── utils/
│   ├── dataHandlers/
│   │   ├── preprocessor.py         # ODS → IncidentDistrict objects
│   │   ├── station_loader.py       # fire_stations.json → FireStation objects
│   │   └── ods_loader.py           # Raw ODS file reader
│   ├── traffic/
│   │   └── traffic.py              # Congestion-aware route multiplier lookup
│   └── logger/
│       └── logger.py               # Structured logging setup
│
├── visualization/
│   └── generate_map.py             # Standalone Folium map (optimal + diagnostic modes)
│
├── src/
│   └── visualization/
│       ├── models.py               # Typed dataclasses for the visualization pipeline
│       ├── milp_visualizer.py      # Solver-agnostic Folium multi-layer renderer
│       ├── parser.py               # real_world_fire_stations.json parser
│       ├── matcher.py              # OSM geometry ↔ station coverage matcher
│       ├── coverage_renderer.py    # Real-world coverage map renderer
│       ├── normalization.py        # Greek text normalization utilities
│       ├── osm_fetcher.py          # OSM boundary fetcher
│       ├── exceptions.py           # Domain-specific exceptions
│       └── cli.py                  # Visualization CLI entry point
│
└── data/
    ├── fire_stations.json          # Candidate station locations, capacities, costs
    ├── municipalities.json         # District centroids, area, wildfire risk factor
    ├── island_municipalities.json  # Island districts excluded from the model
    ├── traffic_data.json           # Per-axis congestion multipliers (6 time slots)
    └── real_world_fire_stations.json  # Actual Hellenic Fire Service stations (ground truth)
```

---

## Installation

### Prerequisites

- Python **3.11** or later
- A Unix/macOS/Windows terminal (PowerShell works on Windows)

### 1 — Clone the repository

```bash
git clone <repo-url>
cd Fire-Protection-Optimization
```

### 2 — Create and activate a virtual environment

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3 — Install dependencies

```bash
pip install pulp pandas folium shapely geopandas requests
```

> **Note:** PuLP ships with the CBC solver bundled — no separate CBC installation is required.

### 4 — Verify the setup

```bash
python -c "import pulp; pulp.pulpTestAll()"
```

All tests should report `OK`.

---

## Data Files

All data lives in the `data/` directory.

### `fire_stations.json`

Array of candidate fire station objects. Each entry must contain:

```json
[
  {
    "id": "ps_marathon",
    "name": "ΠΣ Μαραθώνα",
    "lat": 38.157,
    "lon": 23.963,
    "capacity": 15,
    "cost": 800000.0
  }
]
```

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `id` | string | required | Unique station identifier (ASCII, no spaces) |
| `name` | string | required | Human-readable Greek name |
| `lat` | float | required | Centroid latitude (WGS84) |
| `lon` | float | required | Centroid longitude (WGS84) |
| `capacity` | int | `STATION_DEFAULT_CAPACITY` (15) | Maximum firetrucks the station can hold ($s_j$) |
| `cost` | float | `STATION_DEFAULT_COST` (800,000 EUR) | Annual operating cost ($f_j$) |

### `municipalities.json`

Maps each municipality name to its centroid coordinates, area, and wildfire risk factor.

```json
{
  "municipalities": {
    "Μαραθώνας": {
      "coords": [38.157, 23.963],
      "area_km2": 239.0,
      "wildfire_risk_factor": 5.0
    }
  }
}
```

`wildfire_risk_factor` must be one of the keys in `RISK_COVERAGE_MAX_TIMES` (1.0 – 5.0).

### `traffic_data.json`

Per-axis congestion multipliers for 6 daily time slots (00–06, 06–09, 09–14, 14–17, 17–21, 21–00):

```json
{
  "traffic_profiles": {
    "CENTER_URBAN": [1.1, 1.6, 1.4, 1.35, 1.5, 1.15],
    "KIFISIAS_AXIS": [1.05, 1.55, 1.3, 1.3, 1.45, 1.1],
    ...
  }
}
```

The strategy for aggregating slots is controlled by `TRAFFIC_STRATEGY` in `milp_config.py`.

---

## Configuration Reference

All tunable parameters live in [`config/milp_config.py`](config/milp_config.py).

### Solver

| Parameter | Default | Description |
| ----------- | --------- | ------------- |
| `SOLVER_TIME_LIMIT_SECONDS` | `300` | CBC wall-clock time limit |
| `SOLVER_MIP_GAP` | `0.01` | Acceptable MIP optimality gap (1 %) |

### Fleet & Regional Directorates

```python
REGIONS: list[dict] = [
    {"id": "dipy_athens",  "name": "ΔΙΠΥ ΑΘΗΝΩΝ",             "total_firetrucks": 120},
    {"id": "dipy_piraeus", "name": "ΔΙΠΥ ΠΕΙΡΑΙΩΣ",           "total_firetrucks": 40},
    {"id": "dipy_west",    "name": "ΔΙΠΥ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ",    "total_firetrucks": 45},
    {"id": "dipy_east",    "name": "ΔΙΠΥ ΑΝΑΤΟΛΙΚΗΣ ΑΤΤΙΚΗΣ", "total_firetrucks": 45},
]
```

### Station Defaults

| Parameter | Default | Description |
| ----------- | --------- | ------------- |
| `STATION_DEFAULT_CAPACITY` | `15` | Firetruck slots if not set in JSON |
| `STATION_DEFAULT_COST` | `800,000 EUR` | Annual cost if not set in JSON |

### Response-Time Estimation

| Parameter | Default | Description |
| ----------- | --------- | ------------- |
| `AVERAGE_SPEED_KMH` | `50.0` | Assumed travel speed for Haversine distance → minutes conversion |
| `DISPATCH_BASE_MINUTES` | `1.3` | Fixed pre-departure time (crew boarding, vehicle checks) added to every route |
| `INTRA_DISTRICT_FACTOR` | `0.5` | Scale factor for intra-district travel time (accounts for non-straight roads) |
| `TRAFFIC_STRATEGY` | `"worst_case"` | `"worst_case"` uses max slot multiplier; `"average"` uses mean |

### Objective Weights

| Parameter | Default | Description |
| ----------- | --------- | ------------- |
| `DEMAND_WEIGHTED_RESPONSE` | `True` | Multiply each term by district demand $d_k$ |
| `WILDFIRE_RISK_WEIGHT` | `True` | Apply $\text{risk}_k^2 \cdot \ln(\text{area}_k)$ composite weight |

### Budget

```python
MAX_BUDGET: float | None = 8_000_000.0   # EUR — roughly 10 stations at default cost
# MAX_BUDGET = None                       # no budget limit
```

Setting `MAX_BUDGET = None` removes the budget constraint entirely and lets the solver open as many stations as it needs to minimize response time.

### Demand Metric

| Value | Description |
| ------- | ------------- |
| `"mean_vehicles"` | (default) Average firetrucks deployed per incident — best for capacity planning |
| `"incident_count"` | Raw number of incidents (each counted as 1 unit) |
| `"total_vehicles"` | Cumulative firetrucks deployed over the year |

### Forced-Open Stations

```python
FORCED_OPEN_STATIONS: list[str] = [
    # "ps_marathon",
    # "ps_lavrio",
]
```

Station IDs in this list have their $y_j$ variable pinned to 1 before solving, regardless of budget. Use this for strategically critical perimeter locations.

---

## Usage

### 1. Running the Optimizer

The main entry point is `main.py`. It loads the data, builds the problem, solves the MILP, prints a detailed log report, and saves the result as JSON.

**Basic run (uses budget from `milp_config.py`):**
```bash
python main.py
```

**Override budget at runtime:**
```bash
python main.py --budget 12000000
```

**Override both budget and output path:**
```bash
python main.py --budget 12000000 --output results/high_budget_solution.json
```

**Remove budget limit entirely (pass 0 to signal unconstrained — or edit config):**
```bash
python main.py --budget 0
```

#### CLI arguments

| Argument | Type | Default | Description |
| ---------- | ------ | --------- | ------------- |
| `--budget` | float | `None` (use config) | Override `MAX_BUDGET` in EUR. If omitted, the value from `milp_config.py` is used. |
| `--output` | path | `results/optimization_result.json` | Path for the JSON output file |

#### Example log output

```
INFO  Problem built — 28 candidate stations, 62 districts,
      total demand = 147.30, 4 DIPY regions, total fleet = 250 trucks
INFO  Budget override: 12,000,000 EUR
INFO  Solver finished — status: Optimal
INFO  Objective value: 3284.71
INFO  ══════════════════════════════════════════════════════════════════════
INFO  Status:                   Optimal
INFO  Open stations:            14 / 28
INFO  Avg response time:        11.4 min  (simple avg, all districts)
INFO  Risk-weighted avg:         9.8 min  (weighted by demand x risk)
INFO  Operational cost:         11,200,000 EUR
INFO  ──────────────────────────────────────────────────────────────────────
INFO  DIPY Regional Fleet Deployment:
INFO    ΔΙΠΥ ΑΘΗΝΩΝ: 87/120 trucks deployed
INFO    ΔΙΠΥ ΠΕΙΡΑΙΩΣ: 32/40 trucks deployed
INFO    ΔΙΠΥ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ: 31/45 trucks deployed
INFO    ΔΙΠΥ ΑΝΑΤΟΛΙΚΗΣ ΑΤΤΙΚΗΣ: 39/45 trucks deployed
INFO  ──────────────────────────────────────────────────────────────────────
INFO    ΠΣ Μαραθώνα
INFO      avg response   : 14.2 min  |  firetrucks: 5 [dipy_east=5]
INFO        Μαραθώνας  risk=5.0  area=239.0km2  18.3min
INFO        Νέα Μάκρη  risk=4.0  area= 52.0km2  12.6min
...
INFO  Result serialized to results/optimization_result.json
```

---

### 2. Generating the Interactive Map

`visualization/generate_map.py` runs the optimizer and produces a **standalone HTML map** that opens in any browser.

```bash
python visualization/generate_map.py
# → saves to attica_fire_coverage_map.html

python visualization/generate_map.py results/my_map.html
# → saves to a custom path
```

The script automatically detects the solver status:

**Optimal mode** — four interactive layers:
1. **Incident Districts** — circles colour-coded by wildfire risk (dark red = 5.0 → green = 1.0); popup shows risk, area, demand, assigned station, and response time.
2. **Candidate Stations** — blue markers for open stations, grey for closed; popup shows status, firetrucks deployed, capacity, and cost.
3. **Real-World ΠΣ Stations** — red star markers showing the actual Hellenic Fire Service stations as a ground-truth baseline.
4. **Assignment Routes** — dashed polylines from each district centroid to its assigned station, coloured by the district's risk level.

**Diagnostic mode** (when the model is infeasible) — districts coloured by feasibility gap:
- **Red** — geometrically infeasible: the nearest candidate station still exceeds the risk-based time bound.
- **Yellow** — tight: within bound but with less than 10 % margin.
- **Green** — comfortably within bound.

This mode is useful for debugging `RISK_COVERAGE_MAX_TIMES` settings or sparse station configurations.

---

### 3. Advanced Visualization Module

The `src/visualization/` package provides a **solver-agnostic** multi-layer Folium renderer. It ingests typed dataclasses (not PuLP objects) and can be driven programmatically:

```python
from config.milp_config import AVERAGE_SPEED_KMH
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from optimization import solve
from src.visualization.milp_visualizer import MilpResultVisualizer

# ... build problem and solve ...

result = solve(problem, max_budget=10_000_000)

visualizer = MilpResultVisualizer.from_optimization_result(
    result=result,
    problem=problem,
    response_times=problem.response_time_matrix(AVERAGE_SPEED_KMH),
    center=(38.00, 23.75),
    zoom_start=10,
)
visualizer.render("output/milp_result.html")
```

The rendered map includes four layers:
1. **District Assignments** — circles coloured by assigned station, sized by demand.
2. **Stations (MILP Result)** — open/closed station markers; popup shows per-ΔΙΠΥ truck allocation and covered districts.
3. **Allocation Routes** — dashed polylines from district centroids to their assigned station.
4. **Response Time Heatmap** — (hidden by default) colour gradient from green (≤ 10 min) to red (> 25 min).

A fixed **summary overlay** in the top-right corner shows solver status, open station count, average response time, total cost, and objective value.

#### Parsing real-world station data

To overlay actual Hellenic Fire Service stations fetched from `data/real_world_fire_stations.json`:

```python
from src.visualization.parser import StationDataParser

parser = StationDataParser("data/real_world_fire_stations.json")
stations = parser.parse()
community_lookup, municipality_lookup = parser.build_lookup_tables()
```

---

### 4. Loading a Saved Result

`OptimizationResult` supports full round-trip JSON serialization. To reload a previously saved result without re-solving:

```python
from optimization.result import OptimizationResult

result = OptimizationResult.from_json("results/optimization_result.json")

print(result.status)                    # "Optimal"
print(result.open_stations)             # {"ps_marathon", "ps_lavrio", ...}
print(result.station_total_trucks)      # {"ps_marathon": 5, ...}
print(result.region_total_deployed)     # {"dipy_athens": 87, "dipy_east": 39, ...}
```

> **Note:** Station and district metadata (names, coordinates) is not stored in the JSON. If you need to pair the result with geographic data for visualization, reload `FireProtectionProblem` from the original data sources alongside the result.

---

## Output Format

The JSON file produced by `result.to_json()` has the following top-level structure:

```json
{
  "status": "Optimal",
  "objective_value": 3284.7123,
  "avg_response_time_min": 11.42,
  "total_operational_cost": 11200000.0,

  "open_stations": ["ps_acharnes", "ps_lavrio", "ps_marathon", "..."],

  "district_assignments": {
    "dist_0": "ps_marathon",
    "dist_1": "ps_acharnes",
    "..."
  },

  "region_allocations": {
    "dipy_athens":  {"ps_acharnes": 12, "ps_kifisia": 8, "...": "..."},
    "dipy_east":    {"ps_marathon": 5,  "ps_lavrio": 7,  "...": "..."},
    "dipy_piraeus": {"ps_piraeus": 9,   "...": "..."},
    "dipy_west":    {"ps_elefsina": 6,  "...": "..."}
  },

  "station_totals": {
    "ps_acharnes": 12,
    "ps_marathon": 5,
    "..."
  },

  "stations_detail": {
    "ps_marathon": {
      "is_active": true,
      "total_trucks": 5,
      "region_breakdown": {"dipy_east": 5},
      "assigned_districts": ["dist_0", "dist_14", "dist_22"]
    },
    "ps_kifisia": {
      "is_active": false,
      "total_trucks": 0,
      "region_breakdown": {},
      "assigned_districts": []
    },
    "..."
  }
}
```

### Key sections

| Key | Description |
| ----- | ------------- |
| `status` | PuLP solver status: `"Optimal"`, `"Infeasible"`, `"Not Solved"`, etc. |
| `objective_value` | Value of the minimized objective (weighted response time sum) |
| `avg_response_time_min` | Simple average response time across all assigned district–station pairs |
| `total_operational_cost` | Sum of annual operating costs for all open stations (EUR) |
| `open_stations` | Sorted list of station IDs where $y_j = 1$ |
| `district_assignments` | Flat map `{district_id → station_id}` for every district $k$ |
| `region_allocations` | Nested map `{region_id → {station_id → truck_count}}` for non-zero $v_{ij}$ |
| `station_totals` | Flat map `{station_id → total_trucks}` aggregated across all regions |
| `stations_detail` | Per-station summary: active flag, total trucks, per-ΔΙΠΥ breakdown, assigned districts |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py (CLI)                           │
│          --budget 10000000  --output results/out.json           │
└──────────────────────┬──────────────────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │   Data Loading Layer    │
          │  preprocessor.py        │  ← ODS incident data → IncidentDistrict[]
          │  station_loader.py      │  ← fire_stations.json → FireStation[]
          │  milp_config.REGIONS    │  ← config → FireRegion[]
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  FireProtectionProblem  │
          │  (domain/problem.py)    │  ← assembles ckj response-time matrix
          │                         │    via Haversine + traffic multipliers
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   optimization/         │
          │   model.py  ────────────┼──► PuLP LpProblem (constraints 1–9)
          │   solver.py ────────────┼──► CBC solver → OptimizationResult
          │   result.py ────────────┼──► to_json() / from_json()
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────────────────────────────┐
          │              Visualization Layer                  │
          │  visualization/generate_map.py   (standalone)    │
          │  src/visualization/milp_visualizer.py (advanced) │
          └───────────────────────────────────────────────────┘
```

### Design principles

- **Domain isolation** — `domain/` entities are frozen dataclasses with no solver imports. PuLP types never leak past `optimization/`.
- **Solver agnosticism** — `src/visualization/` ingests typed dataclasses (`MilpVisualizationInput`), not PuLP variables. Switching from CBC to Gurobi requires changing only `solver.py`.
- **Dynamic budget override** — `build_model(problem, max_budget=...)` and `solve(problem, max_budget=...)` accept a runtime override. The CLI `--budget` flag feeds directly into this parameter without touching `milp_config.py`.
- **Round-trip serialization** — `OptimizationResult.to_json()` / `from_json()` guarantee that a saved result can be reloaded and fed to the visualization pipeline without re-solving.

---

## Academic Context

| Field | Detail |
| --- | --- |
| **Course** | ECE_CK806 — Linear & Combinatorial Optimization |
| **Semester** | Spring 2025–2026 |
| **Model basis** | Klose, A. & Drexl, A. (2005). *Facility location models for distribution system design*. European Journal of Operational Research, 162(1), 4–29. |
| **Solver** | COIN-OR CBC (via PuLP 2.x) |
| **Region** | Attica, Greece — 4 ΔΙΠΥ regional fire directorates |

### Key modelling decisions

- **WUI composite weight** ($d_k \cdot \text{risk}_k^2 \cdot \ln(\text{area}_k)$): the quadratic risk term makes the solver non-linearly sensitive to high-risk zones — a district with risk=5 receives 25× the weight of a risk=1 district under the objective, versus only 5× under a linear formulation.
- **Traffic-adjusted response time**: rather than pure Haversine distance, each $c_{kj}$ entry is multiplied by a congestion factor derived from the dominant Attica road axis between the two points (8 axes: center urban, Kifisias, Kifisou, Attiki Odos, Poseidonos, Athinon, Mesogeion, rural).
- **Intra-district travel time**: models the average time to navigate from the district boundary to the fire location within the municipality, approximated from the effective circular radius $\sqrt{\text{area}/\pi}$.
- **Integer demand** ($d_k \in \mathbb{Z}_{>0}$): demands are rounded to integers so that the flow conservation constraint (7) — which equates integer $v_{ij}$ to $\sum_k d_k z_{kj}$ — remains feasible without fractional truck assignments.
- **Constraint (9) — minimum truck**: prevents the solver from opening a station as a "coverage anchor" without actually staffing it, which would be operationally meaningless. It also tightens the LP relaxation.
