"""Loads fire station candidates from JSON into FireStation domain objects."""

import json
import os
from typing import List

from config import DATA_PATH
from config.milp_config import STATION_DEFAULT_CAPACITY, STATION_DEFAULT_COST
from domain.entities import FireStation
from utils.logger import get_logger

logger = get_logger(__name__)

_STATIONS_FILE = os.path.join(DATA_PATH, "fire_stations.json")


def load_stations() -> List[FireStation]:
    """Return candidate FireStation objects from fire_stations.json."""
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
