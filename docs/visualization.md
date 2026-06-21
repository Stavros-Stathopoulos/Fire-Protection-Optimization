# Visualization Pipeline

## Overview

The `src/visualization/` package is a **solver-agnostic** visualisation pipeline.  It ingests typed Python dataclasses (not PuLP objects) and produces two output artefacts:

1. **Interactive Folium Map** (`public/milp_map.html`) — 5-layer Leaflet map.
2. **Executive HTML Dashboard** (`public/milp_report.html`) — 3-tab Tailwind dashboard.

A third pipeline (the **operational coverage map**) renders the real-world Hellenic Fire Service station coverage by fetching OSM boundaries and matching them to station records.

---

## Package Components

| Module | Class / Entry-point | Purpose |
|--------|---------------------|---------|
| `models.py` | `StationRecord`, `CoverageAssignment`, `MilpStationStatus`, `MilpDistrictAssignment`, `MilpVisualizationInput` | Typed dataclasses for inter-stage data transfer |
| `exceptions.py` | `VisualizationError`, `DataStructureMismatchError`, `CoverageResolutionError`, `ProjectionError` | Domain-specific exception hierarchy |
| `normalization.py` | `strip_political_terms()`, `normalize_name()`, `ALIASES` | Greek administrative-text normalisation |
| `parser.py` | `StationDataParser` | JSON parser for `real_world_fire_stations.json` |
| `matcher.py` | `HybridMatcher` | Four-tier OSM unit → station matcher |
| `osm_fetcher.py` | `fetch_attica_hull()`, `fetch_admin_layer()` | OSM boundary fetcher with GeoPackage cache |
| `coverage_renderer.py` | `CoverageMapRenderer` | Operational coverage map renderer |
| `milp_visualizer.py` | `MilpResultVisualizer` | MILP result multi-layer Folium renderer |
| `html_reporter.py` | `MilpHtmlReporter` | 3-tab executive HTML dashboard generator |
| `cli.py` | `main()` | CLI for the operational coverage map pipeline |

---

## MILP Result Visualisation

### From a saved JSON (recommended for CI / post-processing)

```python
from src.visualization.milp_visualizer import MilpResultVisualizer

visualizer = MilpResultVisualizer.from_json("results/optimization_result.json")
visualizer.render("public/milp_map.html")
```

The JSON must be produced by `OptimizationResult.to_full_json()` (the "full" format includes `"stations"` and `"districts"` metadata).

### Directly from solver output

```python
from src.visualization.milp_visualizer import MilpResultVisualizer

visualizer = MilpResultVisualizer.from_optimization_result(
    result=result,
    problem=problem,
    response_times=problem.response_time_matrix(AVERAGE_SPEED_KMH),
    center=(38.00, 23.75),
    zoom_start=10,
)
visualizer.render("public/milp_map.html")
```

### Map Layers

| Layer | Name | Default |
|-------|------|---------|
| 1 | Municipality Coverage (MILP) | Visible |
| 2 | Stations (MILP Result) | Visible |
| 3 | Allocation Routes | Visible |
| 4 | Demand Centroids | Hidden |
| 5 | Response Time Heatmap | Hidden |

A fixed summary overlay in the top-right corner shows solver status, open station count, average response time, total cost, and objective value.

---

## HTML Executive Dashboard

```python
from src.visualization.html_reporter import MilpHtmlReporter

reporter = MilpHtmlReporter(result, problem, response_times)
reporter.generate_report(Path("public/milp_report.html"))
```

### Tab Layout

| Tab | Content |
|-----|---------|
| **Γενικά Στατιστικά** | 5 global KPI cards + 4 regional fleet deployment cards with progress bars |
| **Σταθμοί** | Collapsible accordion card per active station (avg response, truck allocation, district sub-table) + compact grid of inactive stations |
| **Χρόνοι Ανταπόκρισης** | Sortable district datatable (district name, area, risk, demand, assigned station, response time badge) |

The dashboard is fully standalone HTML (single file) using Tailwind CSS via CDN.  No server required.

---

## Operational Coverage Map Pipeline

Generates a map of the existing Hellenic Fire Service station coverage by:

1. Parsing `real_world_fire_stations.json` via `StationDataParser`.
2. Fetching OSM administrative boundaries via `fetch_admin_layer()`.
3. Matching every OSM community unit to a station via `HybridMatcher`.
4. Rendering the coverage map via `CoverageMapRenderer`.

**CLI:**

```bash
python -m src.visualization.cli
python -m src.visualization.cli --output public/attica_fire_stations_map.html
python -m src.visualization.cli --no-cache   # skip GeoPackage cache
```

### Hybrid Matching Algorithm

`HybridMatcher.resolve_coverage()` runs a four-tier cascade for each OSM admin_level=8 unit:

1. **Community exact match** — normalised unit name exactly matches a community in the station's `assigned_communities`.
2. **Community substring match** — either string is a substring of the other.
3. **Municipality exact match** — parent municipality (from spatial join) exactly matches a municipality in `assigned_municipalities`.
4. **Municipality substring match** — either string is a substring of the other.

All comparisons use `strip_political_terms()` normalised strings (uppercase, accent-free, stop-words removed).

### Greek Text Normalisation

`normalization.py` provides:

- `strip_political_terms(text)` — removes accents (NFD decomposition), uppercases, collapses dashes to spaces, strips administrative stop-words (`ΔΗΜΟΣ`, `ΔΗΜΟΤΙΚΗ ΕΝΟΤΗΤΑ`, etc.).
- `normalize_name(raw_name)` — applies `ALIASES` lookup first (OSM nominative → genitive), then `strip_political_terms`.
- `ALIASES` — maps 40+ known OSM nominative forms to pre-normalised genitive keys used in the station JSON.

### OSM Caching

`fetch_admin_layer()` caches downloaded GeoDataFrames as GeoPackages in `cache/osm/`.  The cache key is an MD5 hash of `(place, admin_level)`.  Use `--no-cache` to force a fresh download.

```
cache/osm/admin_7_<hash>.gpkg   # municipalities
cache/osm/admin_8_<hash>.gpkg   # community units
```

---

## Exception Hierarchy

```
VisualizationError
├── DataStructureMismatchError   # JSON schema validation failures
├── CoverageResolutionError      # OSM unit cannot be matched to a station
└── ProjectionError              # CRS conversion / spatial-join failures
```

All exceptions carry contextual attributes (`key`, `station_id`, `unit_name`, `source_crs`, `target_crs`) for structured error logging.

---

## Data Model Relationships

```
StationDataParser.parse()
    └── list[StationRecord]
            ├── assigned_municipalities → tuple[str, ...]
            └── assigned_communities   → tuple[str, ...]

StationDataParser.build_lookup_tables()
    ├── community_lookup:   {normalised_name → StationRecord}
    └── municipality_lookup:{normalised_name → StationRecord}

HybridMatcher.resolve_coverage(gdf_units, gdf_muns)
    └── list[CoverageAssignment]
            ├── geometry    (Shapely polygon)
            ├── station_id  (matched or "unknown")
            └── match_method

CoverageMapRenderer.render(community_assignments, municipality_assignments, stations, path)
    └── folium.Map  →  HTML file
```
