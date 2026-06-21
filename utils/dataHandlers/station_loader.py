"""Loads fire station candidates from JSON into FireStation domain objects."""

import json
import os

from config import JSON_PATH
from config.milp_config import STATION_DEFAULT_CAPACITY, STATION_DEFAULT_COST
from domain.entities import FireStation
from utils.logger import get_logger

logger = get_logger(__name__)

_STATIONS_FILE = os.path.join(JSON_PATH, "fire_stations.json")


def load_stations() -> list[FireStation]:
    """Parse ``fire_stations.json`` and return candidate station objects.

    Each JSON entry must provide ``id``, ``name``, ``lat``, and ``lon``.
    The ``capacity`` and ``cost`` fields are optional and fall back to
    ``STATION_DEFAULT_CAPACITY`` and ``STATION_DEFAULT_COST`` respectively.

    Returns
    -------
    list[FireStation]
        One :class:`~domain.entities.FireStation` per entry in the JSON
        array, in file order.

    Raises
    ------
    FileNotFoundError
        If ``fire_stations.json`` does not exist at the expected path.
    KeyError
        If a required field (``id``, ``name``, ``lat``, or ``lon``) is
        absent from an entry.
    json.JSONDecodeError
        If the file is not valid JSON.
    """
    with open(_STATIONS_FILE, encoding="utf-8") as f:
        raw: list = json.load(f)

    stations = [
        FireStation(
            id=entry["id"],
            name=entry["name"],
            lat=entry["lat"],
            lon=entry["lon"],
            capacity=entry.get("capacity", STATION_DEFAULT_CAPACITY),
            cost=float(entry.get("cost", STATION_DEFAULT_COST)),
        )
        for entry in raw
    ]
    logger.info(f"Loaded {len(stations)} candidate fire stations")
    return stations
