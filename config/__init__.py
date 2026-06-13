"""Project-wide configuration package.

Re-exports all public constants from the sub-modules so callers can either
import from the top-level package::

    from config import DATA_PATH, LOG_LEVEL

or import from a specific sub-module when only part of the config is needed::

    from config.data_config import COLUMN_RENAME_MAP
    from config.env_config  import DEBUG
"""

from .data_config import (
    DATA_PATH,
    FILE_NAME_ASTIKA,
    FILE_NAME_DASIKA,
    REQUIRED_COLUMNS,
    DATE_COLUMNS,
    TIME_COLUMNS,
    CATEGORICAL_COLUMNS,
    NUMERICAL_COLUMNS,
    COLUMN_RENAME_MAP,
)
from .env_config import DEBUG, LOG_LEVEL
from .milp_config import (
    AVERAGE_SPEED_KMH,
    DEMAND_METRIC,
    DEMAND_WEIGHTED_RESPONSE,
    DISPATCH_BASE_MINUTES,
    FORCED_OPEN_STATIONS,
    INTRA_DISTRICT_FACTOR,
    MAX_BUDGET,
    PROXIMITY_ALPHA,
    REGION_ID,
    REGION_NAME,
    REGION_TOTAL_FIRETRUCKS,
    REGIONS,
    RISK_COVERAGE_MAX_TIMES,
    SOLVER_MIP_GAP,
    SOLVER_TIME_LIMIT_SECONDS,
    STATION_DEFAULT_CAPACITY,
    STATION_DEFAULT_COST,
    TRAFFIC_STRATEGY,
    WILDFIRE_RISK_WEIGHT,
)

__all__ = [
    "DATA_PATH",
    "FILE_NAME_ASTIKA",
    "FILE_NAME_DASIKA",
    "REQUIRED_COLUMNS",
    "DATE_COLUMNS",
    "TIME_COLUMNS",
    "CATEGORICAL_COLUMNS",
    "NUMERICAL_COLUMNS",
    "COLUMN_RENAME_MAP",
    "LOG_LEVEL",
    "DEBUG",
    "SOLVER_TIME_LIMIT_SECONDS",
    "SOLVER_MIP_GAP",
    "REGION_ID",
    "REGION_NAME",
    "REGION_TOTAL_FIRETRUCKS",
    "REGIONS",
    "STATION_DEFAULT_CAPACITY",
    "STATION_DEFAULT_COST",
    "AVERAGE_SPEED_KMH",
    "DEMAND_METRIC",
    "DEMAND_WEIGHTED_RESPONSE",
    "DISPATCH_BASE_MINUTES",
    "INTRA_DISTRICT_FACTOR",
    "MAX_BUDGET",
    "PROXIMITY_ALPHA",
    "TRAFFIC_STRATEGY",
    "WILDFIRE_RISK_WEIGHT",
]
