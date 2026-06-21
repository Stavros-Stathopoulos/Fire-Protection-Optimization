"""OSM geometry fetcher with local GeoPackage caching.

Downloads administrative boundaries from OpenStreetMap via ``osmnx`` and
filters them to the Attica convex hull.  Results are cached in a local
GeoPackage file so that repeated runs during development skip the network
round-trip.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry.base import BaseGeometry

from .exceptions import ProjectionError

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "osm"

_WGS84  = "EPSG:4326"
_EGSA87 = "EPSG:2100"


def _cache_key(place: str, level: str) -> str:
    """Generate a deterministic GeoPackage filename for a (place, level) pair.

    Parameters
    ----------
    place : str
        OSM place query string (e.g. ``"Αττική, Ελλάδα"``).
    level : str
        OSM ``admin_level`` value (e.g. ``"7"``).

    Returns
    -------
    str
        A filename of the form ``"admin_<level>_<md5[:10]>.gpkg"``.
    """
    digest = hashlib.md5(f"{place}:{level}".encode()).hexdigest()[:10]
    return f"admin_{level}_{digest}.gpkg"


def fetch_attica_hull(
    place: str = "Αττική, Ελλάδα",
) -> BaseGeometry:
    """Download the Attica region polygon and return its convex hull.

    Parameters
    ----------
    place : str, optional
        OSM place query string.  Defaults to ``"Αττική, Ελλάδα"``.

    Returns
    -------
    shapely.geometry.base.BaseGeometry
        Convex hull of the Attica boundary polygon in WGS 84.
    """
    gdf = ox.geocode_to_gdf(place).to_crs(epsg=4326)
    return gdf.geometry.iloc[0].convex_hull


def fetch_admin_layer(
    level: str,
    attica_hull: BaseGeometry,
    *,
    place: str = "Αττική, Ελλάδα",
    cache_dir: Path | None = _DEFAULT_CACHE_DIR,
) -> gpd.GeoDataFrame:
    """Download and spatially filter an OSM administrative layer to the Attica hull.

    If *cache_dir* is not ``None``, the result is persisted as a GeoPackage
    on first call and subsequent calls return the cached copy without
    hitting the network.

    Parameters
    ----------
    level : str
        OSM ``admin_level`` tag value.  Use ``"7"`` for municipalities and
        ``"8"`` for community units.
    attica_hull : shapely.geometry.base.BaseGeometry
        Convex hull of the Attica region in WGS 84, used as a spatial
        filter to discard features outside the study area.
    place : str, optional
        OSM place query string.  Defaults to ``"Αττική, Ελλάδα"``.
    cache_dir : Path or None, optional
        Directory for caching GeoPackages.  ``None`` disables caching.
        Defaults to ``<project_root>/cache/osm``.

    Returns
    -------
    geopandas.GeoDataFrame
        Filtered ``GeoDataFrame`` in EPSG:4326 with ``name`` and
        ``geometry`` columns only.

    Raises
    ------
    ProjectionError
        If the OSM download fails or CRS conversion to EPSG:2100 fails.
    """
    if cache_dir is not None:
        cache_path = Path(cache_dir) / _cache_key(place, level)
        if cache_path.exists():
            return gpd.read_file(cache_path)

    try:
        raw = ox.features_from_place(place, tags={"admin_level": level})
    except Exception as exc:
        raise ProjectionError(
            f"OSM download failed for admin_level={level}: {exc}",
            source_crs="OSM",
            target_crs=_WGS84,
        ) from exc

    gdf = raw[raw.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf = gdf.reset_index(drop=True).to_crs(epsg=4326)

    if "admin_level" in gdf.columns:
        gdf = gdf[gdf["admin_level"].astype(str).str.strip() == level].copy()

    try:
        gdf_projected = gdf.to_crs(epsg=2100)
        hull_projected = gpd.GeoSeries(
            [attica_hull], crs=_WGS84
        ).to_crs(epsg=2100).iloc[0]
    except Exception as exc:
        raise ProjectionError(
            f"CRS conversion to EPSG:2100 failed: {exc}",
            source_crs=_WGS84,
            target_crs=_EGSA87,
        ) from exc

    mask = gdf_projected.geometry.centroid.within(hull_projected)
    result = gdf[mask][["name", "geometry"]].copy().reset_index(drop=True)

    if cache_dir is not None:
        cache_path = Path(cache_dir) / _cache_key(place, level)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_file(cache_path, driver="GPKG")

    return result
