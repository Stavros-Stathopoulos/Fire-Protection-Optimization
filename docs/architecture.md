# System Architecture

## Overview

Fire-Protection-Optimization is a **Mixed-Integer Linear Program (MILP)** solver for optimal fire station placement across the four ΔΙΠΥ regional fire-service directorates of Attica, Greece.  The system is structured as a layered pipeline: raw incident data and geographic files flow through data loaders, a domain model, a PuLP-based solver, and an independent visualisation stack.

---

## Package Layout

```
Fire-Protection-Optimization/
│
├── main.py                     # CLI entry point
│
├── config/                     # All tunable constants (no business logic)
│   ├── __init__.py             # Re-exports every public constant
│   ├── milp_config.py          # Solver, fleet, response-time, budget params
│   ├── data_config.py          # File paths & ODS column contracts
│   └── env_config.py           # Runtime flags via environment variables
│
├── domain/                     # Pure domain objects — zero solver imports
│   ├── entities.py             # Frozen dataclasses: FireRegion, FireStation, IncidentDistrict
│   └── problem.py              # FireProtectionProblem — matrix builders
│
├── optimization/               # MILP solver layer
│   ├── model.py                # build_model() → PuLP LpProblem (9 constraint groups)
│   ├── solver.py               # solve() → CBC solver → OptimizationResult
│   └── result.py               # OptimizationResult + JSON round-trip serialisation
│
├── utils/
│   ├── logger/logger.py        # Colour-aware logging factory
│   ├── traffic/traffic.py      # 8-axis Attica congestion profile router
│   └── dataHandlers/
│       ├── ods_loader.py       # ODS file reader + column validation
│       ├── preprocessor.py     # ODS → IncidentDistrict aggregation
│       └── station_loader.py   # fire_stations.json → FireStation objects
│
├── src/visualization/          # Solver-agnostic visualisation pipeline
│   ├── models.py               # Typed dataclasses for the viz pipeline
│   ├── exceptions.py           # Domain-specific exception hierarchy
│   ├── normalization.py        # Greek text normalisation + alias table
│   ├── parser.py               # real_world_fire_stations.json parser
│   ├── matcher.py              # HybridMatcher: OSM units → stations
│   ├── osm_fetcher.py          # OSM boundary fetcher + GeoPackage cache
│   ├── coverage_renderer.py    # Operational coverage map renderer
│   ├── milp_visualizer.py      # MILP result multi-layer Folium renderer
│   ├── html_reporter.py        # 3-tab executive HTML dashboard
│   └── cli.py                  # Coverage map CLI orchestrator
│
└── test/
    └── infeasible_diagnostic_tool.py  # Pre-solve geographic feasibility check
```

---

## End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          main.py  (CLI)                                  │
│    --budget 8000000  --output results/out.json  --no-report              │
└───────────┬─────────────────────────────────────────────────────────────┘
            │
  ┌─────────▼──────────────────────┐
  │       Data Loading Layer        │
  │  load_districts(ods_file)       │  ODS → DataFrame → IncidentDistrict[]
  │  load_stations()                │  fire_stations.json → FireStation[]
  │  _build_regions() from config   │  config.REGIONS → FireRegion[]
  └─────────┬──────────────────────┘
            │
  ┌─────────▼──────────────────────┐
  │   FireProtectionProblem         │
  │   domain/problem.py             │
  │   ─────────────────────────     │
  │   response_time_matrix()        │  c_{kj}: Haversine + traffic factor
  │   region_station_distance_matrix│  t_{ij}: ΔΙΠΥ HQ → station Haversine km
  └─────────┬──────────────────────┘
            │
  ┌─────────▼──────────────────────┐
  │    optimization/model.py        │
  │    build_model(problem,         │
  │                max_budget)      │  → PuLP LpProblem (variables + 9 constraint groups)
  └─────────┬──────────────────────┘
            │
  ┌─────────▼──────────────────────┐
  │    optimization/solver.py       │
  │    solve(problem, max_budget)   │  → CBC solver → OptimizationResult
  └─────────┬──────────────────────┘
            │
       ┌────┴────┐
       │         │
  ┌────▼───┐ ┌──▼──────────────────────┐
  │  JSON   │ │   Visualisation Layer    │
  │  output │ │                          │
  │         │ │  MilpResultVisualizer    │  → Folium 5-layer HTML map
  │  .json  │ │  MilpHtmlReporter        │  → Tailwind 3-tab dashboard
  └────────┘ └──────────────────────────┘
```

---

## Layer Responsibilities

### `config/`

No business logic.  All constants are module-level literals or simple derivations.  The `__init__.py` re-exports every constant so callers can use either:

```python
from config import MAX_BUDGET
from config.milp_config import RISK_COVERAGE_MAX_TIMES
```

### `domain/`

Frozen dataclasses that model the problem's input parameters.  No imports from `optimization/` or `utils/`.  This ensures the solver layer can be replaced (e.g. PuLP → Gurobi) without touching the domain model.

| Class | Role | Key fields |
|-------|------|-----------|
| `FireRegion` | ΔΙΠΥ directorate | `id`, `name`, `total_firetrucks`, `lat`, `lon` |
| `FireStation` | Candidate station | `id`, `lat`, `lon`, `capacity` (s_j), `cost` (f_j) |
| `IncidentDistrict` | Demand node | `id`, `lat`, `lon`, `demand` (d_k), `area_km2`, `wildfire_risk` |

`FireProtectionProblem` is a non-frozen dataclass (holds lists) that wraps the three entity lists and provides matrix-builder methods called by the model builder.

### `optimization/`

Stateless functions:

- `build_model(problem, max_budget)` — builds a `pulp.LpProblem` with all variables and 9 constraint groups.  Returns `(model, y, z, v)`.
- `solve(problem, max_budget)` — calls `build_model`, invokes CBC, extracts variable values into an `OptimizationResult`.
- `OptimizationResult` — plain-Python dataclass with JSON round-trip methods.

### `utils/`

Three independent sub-packages:

- **`logger`** — singleton logging factory.  All modules call `get_logger(__name__)`.
- **`traffic`** — geographic midpoint → road axis → congestion multiplier lookup with LRU cache.
- **`dataHandlers`** — ODS loading, column validation, district aggregation, station JSON parsing.

### `src/visualization/`

Solver-agnostic; depends only on `domain/` and the JSON output format.  The entry points are:

- `MilpResultVisualizer.from_json(path)` — reconstructs the visualizer from a full-format JSON without re-solving.
- `MilpResultVisualizer.from_optimization_result(result, problem, rt)` — used directly after solving in the same process.
- `MilpHtmlReporter(result, problem, rt).generate_report(path)` — 3-tab Tailwind HTML dashboard.
- `python -m src.visualization.cli` — operational coverage map pipeline.

---

## Key Design Decisions

### Domain Isolation

`domain/` entities are frozen dataclasses with zero solver imports.  PuLP types never leak past `optimization/`.  Switching from CBC to another solver requires changing only `optimization/solver.py`.

### Solver Agnosticism in Visualisation

`src/visualization/` ingests typed dataclasses (`MilpVisualizationInput`, `MilpStationStatus`, `MilpDistrictAssignment`) rather than PuLP variable objects.  This means the map and dashboard can be regenerated from a saved JSON file without re-solving.

### Integer Demand

Demands `d_k` are rounded to integers before model construction.  This keeps the flow conservation constraint (`Σ_i v_{ij} ≥ Σ_k d_k · z_{kj}`, with `v_{ij} ∈ ℤ`) feasible — you cannot deploy half a firetruck.

### Budget Override

`build_model` and `solve` accept a `max_budget` keyword that overrides the config value at runtime.  The CLI `--budget` flag feeds directly into this parameter without editing any file.

### Round-Trip Serialisation

`OptimizationResult.to_full_json()` embeds full station and district metadata so the visualisation pipeline can reconstruct everything from the JSON alone.  `from_json()` / `MilpResultVisualizer.from_json()` complete the round-trip.
