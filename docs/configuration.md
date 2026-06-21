# Configuration Reference

All tunable parameters are centralised in the `config/` package.  Callers should import from the appropriate sub-module or from the top-level `config` package — never hard-code numeric constants elsewhere.

---

## `config/milp_config.py`

### Solver

| Constant | Type | Default | Description |
|----------|------|---------|-------------|
| `SOLVER_TIME_LIMIT_SECONDS` | `int` | `300` | CBC wall-clock time limit in seconds. |
| `SOLVER_MIP_GAP` | `float` | `0.01` | Acceptable MIP optimality gap (1%). The solver stops when the gap between the best integer solution and the LP relaxation bound is ≤ this value. |

### Regional Directorates

```python
REGIONS: list[dict] = [
    {"id": "dipy_athens",  "name": "ΔΙΠΥ ΑΘΗΝΩΝ",             "total_firetrucks": 120, "lat": 37.9838, "lon": 23.7275},
    {"id": "dipy_piraeus", "name": "ΔΙΠΥ ΠΕΙΡΑΙΩΣ",           "total_firetrucks": 120, "lat": 37.9430, "lon": 23.6460},
    {"id": "dipy_west",    "name": "ΔΙΠΥ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ",    "total_firetrucks": 120, "lat": 38.0410, "lon": 23.5320},
    {"id": "dipy_east",    "name": "ΔΙΠΥ ΑΝΑΤΟΛΙΚΗΣ ΑΤΤΙΚΗΣ", "total_firetrucks": 120, "lat": 38.0040, "lon": 23.8910},
]
```

Each entry in `REGIONS` must have:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | ASCII identifier used in constraint names and JSON keys. |
| `name` | `str` | Greek display name. |
| `total_firetrucks` | `int` | Fleet size π_i. |
| `lat` | `float` | HQ latitude (WGS 84) — used for proximity penalty. |
| `lon` | `float` | HQ longitude (WGS 84). |

### Station Defaults

| Constant | Type | Default | Description |
|----------|------|---------|-------------|
| `STATION_DEFAULT_CAPACITY` | `int` | `15` | Firetruck slots (s_j) when not specified in `fire_stations.json`. |
| `STATION_DEFAULT_COST` | `float` | `800,000.0` | Annual cost f_j (EUR) when not specified in JSON. |

### Response-Time Estimation

| Constant | Type | Default | Description |
|----------|------|---------|-------------|
| `AVERAGE_SPEED_KMH` | `float` | `50.0` | Assumed travel speed for Haversine distance → minutes. |
| `DISPATCH_BASE_MINUTES` | `float` | `1.3` | Fixed pre-departure time added to every route. |
| `INTRA_DISTRICT_FACTOR` | `float` | `0.5` | Scale factor for intra-district travel time (effective radius). |
| `TRAFFIC_STRATEGY` | `str` | `"worst_case"` | `"worst_case"` → max slot multiplier; `"average"` → mean. |

### Objective Weights

| Constant | Type | Default | Description |
|----------|------|---------|-------------|
| `DEMAND_WEIGHTED_RESPONSE` | `bool` | `True` | Multiply objective terms by d_k. |
| `WILDFIRE_RISK_WEIGHT` | `bool` | `True` | Apply `risk²·ln(area)` composite weight. |
| `PROXIMITY_ALPHA` | `float` | `10.0` | Secondary objective coefficient for proximity penalty. |

### Budget

```python
MAX_BUDGET: float | None = 8_000_000.0   # EUR — roughly 10 stations at default cost
# MAX_BUDGET = None                       # remove budget constraint entirely
```

Setting `MAX_BUDGET = None` removes the budget constraint.  The solver will open as many stations as needed to minimise response time subject to the coverage-time bounds.

### Response-Time Hard Bounds

```python
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
```

Every district's `wildfire_risk` must be a key in this dict; otherwise the coverage-time constraint is skipped for that district.

### Demand Metric

| Value | Description |
|-------|-------------|
| `"mean_vehicles"` (default) | Average firetrucks per incident — best for capacity planning. |
| `"incident_count"` | Raw number of incidents (each = 1 unit). |
| `"total_vehicles"` | Cumulative firetrucks deployed over the year. |

### Forced-Open Stations

```python
FORCED_OPEN_STATIONS: list[str] = []
```

Station IDs listed here have their y_j variable pinned to 1 before solving, regardless of budget.  Useful for strategically critical perimeter locations.

---

## `config/data_config.py`

| Constant | Type | Description |
|----------|------|-------------|
| `DATA_PATH` | `str` | Absolute path to the `data/` directory (resolved relative to this file). |
| `FILE_NAME_ASTIKA` | `str` | ODS incident data file: `"Stoixeia_Symvantwn.ods"`. |
| `FILE_NAME_DASIKA` | `str` | Forest-fire ODS file (unused in main pipeline). |
| `REQUIRED_COLUMNS` | `list[str]` | Greek column names that must be present in the ODS file. |
| `DATE_COLUMNS` | `list[str]` | Columns to parse as dates. |
| `TIME_COLUMNS` | `list[str]` | Columns to parse as times. |
| `CATEGORICAL_COLUMNS` | `list[str]` | Columns to treat as categorical. |
| `NUMERICAL_COLUMNS` | `list[str]` | Columns to coerce to numeric. |
| `COLUMN_RENAME_MAP` | `dict[str, str]` | Greek → English column name mapping applied after loading. |

---

## `config/env_config.py`

Runtime flags read from environment variables at import time.

| Variable | Python Constant | Default | Description |
|----------|----------------|---------|-------------|
| `APP_DEBUG` | `DEBUG: bool` | `False` | Set to `"true"` to enable debug mode. |
| `APP_LOG_LEVEL` | `LOG_LEVEL: str` | `"INFO"` | Logging level (`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`). |

**Usage:**

```bash
# Enable debug logging
APP_LOG_LEVEL=DEBUG python main.py

# Debug mode
APP_DEBUG=true python main.py
```

---

## Traffic Data (`data/traffic_data.json`)

```json
{
  "traffic_profiles": {
    "CENTER_URBAN":    [1.1, 1.6, 1.4, 1.35, 1.5, 1.15],
    "KIFISIAS_AXIS":   [1.05, 1.55, 1.3, 1.3, 1.45, 1.1],
    "KIFISOU_AXIS":    [1.1, 1.5, 1.3, 1.25, 1.45, 1.1],
    "ATTIKI_ODOS":     [1.0, 1.35, 1.2, 1.2, 1.3, 1.05],
    "POSEIDONOS_AVEN": [1.05, 1.4, 1.25, 1.3, 1.55, 1.15],
    "ATHINON_AVENUE":  [1.05, 1.45, 1.3, 1.25, 1.4, 1.1],
    "MESOGEION_AXIS":  [1.05, 1.5, 1.3, 1.3, 1.4, 1.1],
    "RURAL_SUBURBAN":  [1.0, 1.2, 1.1, 1.1, 1.15, 1.0]
  }
}
```

Each array contains 6 multipliers for time slots: [00-06, 06-09, 09-14, 14-17, 17-21, 21-00].

The zone assignment is performed by `utils/traffic/traffic.py::_assign_profile()` using geographic bounding-box tests on the route midpoint.
