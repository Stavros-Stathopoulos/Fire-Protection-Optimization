"""Transforms raw incident ODS data into IncidentDistrict domain objects.

Aggregation strategy is controlled by ``config.milp_config.DEMAND_METRIC``:

* ``"mean_vehicles"``  — average firetrucks per incident (recommended for
  capacity planning).
* ``"incident_count"`` — number of incidents (unit demand per event).
* ``"total_vehicles"`` — cumulative firetrucks deployed over the year.

Island municipalities are excluded because they have no road access to any
candidate station on the mainland.
"""

import json
import os

import pandas as pd

from config import COLUMN_RENAME_MAP, JSON_PATH, FILE_NAME_ASTIKA
from config.milp_config import DEMAND_METRIC
from domain.entities import IncidentDistrict
from utils.logger import get_logger

from .ods_loader import OdsLoader

logger = get_logger(__name__)

_MUNICIPALITIES_FILE = os.path.join(JSON_PATH, "municipalities.json")
_ISLAND_FILE = os.path.join(JSON_PATH, "island_municipalities.json")


def _district_id(index: int) -> str:
    """Generate a stable, ASCII-safe district identifier.

    Greek municipality names are non-ASCII and cannot appear directly in PuLP
    variable names.  This function maps an ordinal position to a deterministic
    string key.

    Parameters
    ----------
    index : int
        Zero-based ordinal position of the district in the loaded list.

    Returns
    -------
    str
        A string of the form ``"dist_<index>"``, e.g. ``"dist_0"``.
    """
    return f"dist_{index}"


def _compute_demand(group: pd.DataFrame) -> float:
    """Compute integer-valued demand for a municipality group.

    Demands are rounded to integers so the flow conservation constraint
    ``v_{ij} ∈ ℤ`` remains feasible (you cannot deploy half a firetruck).
    The minimum value is ``1`` to prevent zero-demand districts from being
    trivially assigned without meaningful coverage.

    Parameters
    ----------
    group : pandas.DataFrame
        Slice of the incident DataFrame for a single municipality.  Must
        contain a ``total_vehicles`` column.

    Returns
    -------
    float
        Integer-valued demand ``d_k`` (stored as ``float`` for compatibility
        with PuLP's linear expression builder).  The interpretation depends
        on ``DEMAND_METRIC``:

        * ``"incident_count"`` — number of rows in *group*.
        * ``"total_vehicles"`` — sum of ``total_vehicles`` across all rows.
        * ``"mean_vehicles"`` (default) — ``max(1, round(mean(total_vehicles)))``.
    """
    if DEMAND_METRIC == "incident_count":
        return float(len(group))
    if DEMAND_METRIC == "total_vehicles":
        return float(group["total_vehicles"].sum())
    return float(max(1, round(group["total_vehicles"].mean())))


def load_districts(filename: str = FILE_NAME_ASTIKA) -> list[IncidentDistrict]:
    """Load and preprocess the ODS incident file into domain objects.

    Pipeline:

    1. Load the ODS file via :class:`~utils.dataHandlers.ods_loader.OdsLoader`
       and validate required columns.
    2. Rename Greek column headers to English using ``COLUMN_RENAME_MAP``.
    3. Join with ``municipalities.json`` to obtain centroid coordinates, area,
       and wildfire risk factor for each municipality.
    4. Exclude island municipalities (from ``island_municipalities.json``).
    5. Aggregate each municipality's incidents into a single
       :class:`~domain.entities.IncidentDistrict`.

    Parameters
    ----------
    filename : str, optional
        Filename of the ODS file inside ``config.data_config.ODS_PATH``
        (``data/data/``).  Defaults to ``FILE_NAME_ASTIKA``
        (``"Stoixeia_Symvantwn.ods"``).

    Returns
    -------
    list[IncidentDistrict]
        One district per municipality that has both incident data and a valid
        entry in ``municipalities.json``.  Island municipalities are silently
        excluded.  Municipalities with incident data but no coordinate entry
        are logged as warnings and skipped.

    Raises
    ------
    FileNotFoundError
        If *filename* does not exist in ``ODS_PATH``.
    ValueError
        If required columns are missing from the ODS file (raised by
        :meth:`~utils.dataHandlers.ods_loader.OdsLoader.check_data_format`).
    """
    loader = OdsLoader(filename)
    raw = loader.load_data()
    loader.check_data_format(raw)

    df = raw.rename(columns=COLUMN_RENAME_MAP)
    df["total_vehicles"] = pd.to_numeric(df["total_vehicles"], errors="coerce").fillna(0)

    with open(_MUNICIPALITIES_FILE, encoding="utf-8") as f:
        muni_data: dict = json.load(f)
    muni_entries: dict = muni_data.get("municipalities", muni_data)

    coord_lookup = {}
    for name, entry in muni_entries.items():
        if isinstance(entry, dict) and "coords" in entry:
            coord_lookup[name] = entry
        elif isinstance(entry, list):
            coord_lookup[name] = {"coords": entry, "area_km2": 10.0, "wildfire_risk_factor": 1.0}

    with open(_ISLAND_FILE, encoding="utf-8") as f:
        island_names: set = set(json.load(f).keys())

    districts: list[IncidentDistrict] = []
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
        logger.info(
            f"Excluded {len(islands_skipped)} island municipalities (no road access): "
            f"{islands_skipped}"
        )
    if skipped:
        logger.warning(
            f"Skipped {len(skipped)} municipalities with no coordinates: {skipped}"
        )
    logger.info(f"Loaded {len(districts)} incident districts (metric: {DEMAND_METRIC})")
    return districts
