"""Transforms raw incident ODS data into IncidentDistrict domain objects.

Aggregation strategy is controlled by config.milp_config.DEMAND_METRIC:
  "mean_vehicles"  — average firetrucks per incident (recommended for capacity planning)
  "incident_count" — number of incidents (unit demand per event)
  "total_vehicles" — cumulative firetrucks deployed over the year
"""

import json
import os
from typing import List

import pandas as pd

from config import COLUMN_RENAME_MAP, DATA_PATH, FILE_NAME_ASTIKA
from config.milp_config import DEMAND_METRIC
from domain.entities import IncidentDistrict
from utils.logger import get_logger

from .ods_loader import OdsLoader

logger = get_logger(__name__)

_MUNICIPALITIES_FILE = os.path.join(DATA_PATH, "municipalities.json")
_ISLAND_FILE = os.path.join(DATA_PATH, "island_municipalities.json")


def _district_id(index: int) -> str:
    """Stable numeric id for use in PuLP variable names (Greek names are non-ASCII)."""
    return f"dist_{index}"


def _compute_demand(group: pd.DataFrame) -> float:
    """Return integer-valued demand so the flow conservation constraint (v_ij ∈ ℤ) stays feasible."""
    if DEMAND_METRIC == "incident_count":
        return float(len(group))
    if DEMAND_METRIC == "total_vehicles":
        return float(group["total_vehicles"].sum())
    return float(max(1, round(group["total_vehicles"].mean())))  # "mean_vehicles"


def load_districts(filename: str = FILE_NAME_ASTIKA) -> List[IncidentDistrict]:
    """Load ODS incident file, aggregate by municipality, return domain objects."""
    loader = OdsLoader(filename)
    raw = loader.load_data()
    loader.check_data_format(raw)

    df = raw.rename(columns=COLUMN_RENAME_MAP)
    df["total_vehicles"] = pd.to_numeric(df["total_vehicles"], errors="coerce").fillna(0)

    with open(_MUNICIPALITIES_FILE, encoding="utf-8") as f:
        muni_data: dict = json.load(f)
    # Support both the new nested format {"municipalities": {...}} and the old flat format
    muni_entries: dict = muni_data.get("municipalities", muni_data)

    # Build lookup: name → {coords, area_km2, wildfire_risk_factor}
    coord_lookup = {}
    for name, entry in muni_entries.items():
        if isinstance(entry, dict) and "coords" in entry:
            coord_lookup[name] = entry
        elif isinstance(entry, list):
            # Old flat format: just coordinates
            coord_lookup[name] = {"coords": entry, "area_km2": 10.0, "wildfire_risk_factor": 1.0}

    with open(_ISLAND_FILE, encoding="utf-8") as f:
        island_names: set = set(json.load(f).keys())

    districts: List[IncidentDistrict] = []
    skipped = []
    islands_skipped = []

    for municipality, group in df.groupby("municipality"):
        if municipality in island_names:
            islands_skipped.append(municipality)
            continue
        if municipality not in coord_lookup:
            skipped.append(municipality)
            continue

        entry = coord_lookup[municipality]
        lat, lon = entry["coords"]
        districts.append(
            IncidentDistrict(
                id=_district_id(len(districts)),
                name=str(municipality),
                lat=lat,
                lon=lon,
                demand=_compute_demand(group),
                area_km2=float(entry.get("area_km2", 10.0)),
                wildfire_risk=float(entry.get("wildfire_risk_factor", 1.0)),
            )
        )

    if islands_skipped:
        logger.info(f"Excluded {len(islands_skipped)} island municipalities (no road access): {islands_skipped}")
    if skipped:
        logger.warning(f"Skipped {len(skipped)} municipalities with no coordinates: {skipped}")
    logger.info(f"Loaded {len(districts)} incident districts (metric: {DEMAND_METRIC})")
    return districts
