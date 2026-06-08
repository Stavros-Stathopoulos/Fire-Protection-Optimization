"""Hybrid matching algorithm: OSM spatial units → fire station assignments.

Extracts the matching decision matrix from ``test2.py`` lines 186–270 into
a reusable, testable class.  The algorithm resolves every OSM community
unit (admin_level=8) to a fire station via a four-tier cascade:

  1. Community exact match (``unit_lookup``)
  2. Community substring match
  3. Municipality exact match (``mun_lookup``, via parent spatial join)
  4. Municipality substring match

All matching is done on normalised strings (uppercase, accent-free, no
administrative stop-words) produced by ``normalization.strip_political_terms``.
"""

from __future__ import annotations

from typing import Optional

import geopandas as gpd
import pandas as pd

from .models import CoverageAssignment, StationRecord
from .normalization import normalize_name, strip_political_terms


class HybridMatcher:
    """Resolves OSM community units to fire stations via hybrid matching.

    Parameters
    ----------
    community_lookup:
        Normalised community name → ``StationRecord``.
    municipality_lookup:
        Normalised municipality name → ``StationRecord``.
    """

    def __init__(
        self,
        community_lookup: dict[str, StationRecord],
        municipality_lookup: dict[str, StationRecord],
    ) -> None:
        self._community_lookup = community_lookup
        self._municipality_lookup = municipality_lookup

    # -- Public API ----------------------------------------------------------

    def resolve_coverage(
        self,
        gdf_units: gpd.GeoDataFrame,
        gdf_muns: gpd.GeoDataFrame,
    ) -> list[CoverageAssignment]:
        """Match every community unit to a fire station.

        Parameters
        ----------
        gdf_units:
            OSM admin_level=8 GeoDataFrame with ``name`` and ``geometry``.
        gdf_muns:
            OSM admin_level=7 GeoDataFrame with ``name`` and ``geometry``.

        Returns
        -------
        list[CoverageAssignment]
            One assignment per community unit.
        """
        parent_series = self._compute_parent_municipalities(gdf_units, gdf_muns)

        assignments: list[CoverageAssignment] = []
        unmatched_count = 0

        for idx, unit_row in gdf_units.iterrows():
            unit_name: str = str(unit_row["name"])
            unit_geom = unit_row["geometry"]
            unit_clean = strip_political_terms(unit_name)

            # Resolve parent municipality from precomputed spatial join
            raw_parent = parent_series.at[idx]
            parent_mun_name = str(raw_parent) if pd.notna(raw_parent) else "—"
            parent_mun_clean = normalize_name(parent_mun_name)

            station, method = self._match(unit_clean, parent_mun_clean)

            if station is None:
                unmatched_count += 1
                if unmatched_count <= 15:
                    print(
                        f"⚠️ Unmatched → OSM Unit: '{unit_name}' "
                        f"[normalised: '{unit_clean}'] | "
                        f"Parent Municipality: '{parent_mun_name}' "
                        f"[normalised: '{parent_mun_clean}']"
                    )

            assignments.append(
                CoverageAssignment(
                    geometry=unit_geom,
                    unit_name=unit_name,
                    mun_name=parent_mun_name,
                    match_method=method,
                    station_name=station.name if station else "—",
                    station_id=station.id if station else "unknown",
                    station_type=station.station_type if station else "?",
                )
            )

        print(f"📊 Unmatched units: {unmatched_count}/{len(gdf_units)}")
        return assignments

    def build_municipality_base_layer(
        self,
        gdf_muns: gpd.GeoDataFrame,
    ) -> list[CoverageAssignment]:
        """Build fallback municipality-level coverage for gap-filling.

        Some municipalities have only partial community-unit coverage in OSM.
        Rendering every municipality polygon underneath the community units
        fills those gaps.

        Returns
        -------
        list[CoverageAssignment]
            One assignment per unique municipality.
        """
        seen: set[str] = set()
        records: list[CoverageAssignment] = []

        for _, mun_row in gdf_muns.iterrows():
            mun_name: str = str(mun_row["name"])
            if mun_name in seen:
                continue
            seen.add(mun_name)

            mun_clean = normalize_name(mun_name)
            station = self._lookup_municipality(mun_clean)

            records.append(
                CoverageAssignment(
                    geometry=mun_row["geometry"],
                    unit_name=mun_name,
                    mun_name=mun_name,
                    match_method="Δήμος (βάση)",
                    station_name=station.name if station else "—",
                    station_id=station.id if station else "unknown",
                    station_type=station.station_type if station else "?",
                )
            )

        print(f"📍 Municipality base layer: {len(records)} polygons")
        return records

    # -- Private matching logic ----------------------------------------------

    def _match(
        self,
        unit_clean: str,
        parent_mun_clean: str,
    ) -> tuple[Optional[StationRecord], str]:
        """Run the four-tier matching cascade."""
        # 1. Community exact match
        if unit_clean in self._community_lookup:
            return self._community_lookup[unit_clean], "Unit Exact Match"

        # 2. Community substring match
        for key, station in self._community_lookup.items():
            if key in unit_clean or unit_clean in key:
                return station, "Unit Substring Match"

        # 3. Municipality exact match (parent)
        if parent_mun_clean in self._municipality_lookup:
            return self._municipality_lookup[parent_mun_clean], "Municipal Fallback"

        # 4. Municipality substring match (parent)
        for key, station in self._municipality_lookup.items():
            if key in parent_mun_clean or parent_mun_clean in key:
                return station, "Municipal Substring Fallback"

        return None, "Unmatched"

    def _lookup_municipality(self, mun_clean: str) -> Optional[StationRecord]:
        """Exact-then-substring municipality lookup."""
        station = self._municipality_lookup.get(mun_clean)
        if station is not None:
            return station
        for key, st in self._municipality_lookup.items():
            if key in mun_clean or mun_clean in key:
                return st
        return None

    # -- Spatial join helpers -------------------------------------------------

    @staticmethod
    def _compute_parent_municipalities(
        gdf_units: gpd.GeoDataFrame,
        gdf_muns: gpd.GeoDataFrame,
    ) -> pd.Series:
        """Precompute the parent municipality for every community unit.

        Uses a ``within`` spatial join with a ``nearest`` fallback for units
        whose centroids fall outside all municipality polygons (complex
        mountain/forest shapes).

        Returns
        -------
        pd.Series
            Index-aligned with *gdf_units*, containing the parent
            municipality name.
        """
        gdf_units_proj = gdf_units.to_crs(epsg=2100)
        gdf_muns_proj = gdf_muns[["name", "geometry"]].copy().to_crs(epsg=2100)

        parent = (
            gpd.sjoin(
                gdf_units_proj[["geometry"]],
                gdf_muns_proj,
                how="left",
                predicate="within",
            )
            .groupby(level=0)
            .first()["name"]
        )

        no_match = parent[parent.isna()].index
        if len(no_match):
            nearest = (
                gpd.sjoin_nearest(
                    gdf_units_proj.loc[no_match, ["geometry"]],
                    gdf_muns_proj,
                    how="left",
                )
                .groupby(level=0)
                .first()["name"]
            )
            parent.loc[no_match] = nearest

        return parent
