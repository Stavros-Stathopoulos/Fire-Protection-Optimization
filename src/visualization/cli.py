"""CLI entry point for the operational coverage map pipeline.

Orchestrates: parse → fetch → match → render.

Usage (from project root):
    python -m src.visualization.cli
    python -m src.visualization.cli --output my_map.html
    python -m src.visualization.cli --no-cache
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .coverage_renderer import CoverageMapRenderer
from .matcher import HybridMatcher
from .osm_fetcher import fetch_admin_layer, fetch_attica_hull
from .parser import StationDataParser

# Default paths relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATIONS_FILE = _PROJECT_ROOT / "data" / "real_world_fire_stations.json"
_DEFAULT_OUTPUT = _PROJECT_ROOT / "public" / "attica_fire_stations_map.html"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the operational fire-station coverage map for Attica.",
    )
    parser.add_argument(
        "--stations-file",
        type=Path,
        default=_DEFAULT_STATIONS_FILE,
        help="Path to the fire stations JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Output HTML file path.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable OSM GeoPackage caching.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the full coverage-map pipeline."""
    args = _build_arg_parser().parse_args(argv)

    # 1. Parse station data (with hierarchical fix)
    print("📂 Loading station data...")
    parser = StationDataParser(args.stations_file)
    stations = parser.parse()
    community_lookup, municipality_lookup = parser.build_lookup_tables()

    print(
        f"   → {len(stations)} stations loaded, "
        f"{len(community_lookup)} community entries, "
        f"{len(municipality_lookup)} municipality entries"
    )

    # 2. Fetch OSM geometries
    cache_dir = None if args.no_cache else (_PROJECT_ROOT / "cache" / "osm")

    print("🌍 Fetching Attica hull...")
    attica_hull = fetch_attica_hull()

    print("🏛️  Fetching municipalities (admin_level=7)...")
    gdf_muns = fetch_admin_layer("7", attica_hull, cache_dir=cache_dir)

    print("🏘️  Fetching community units (admin_level=8)...")
    gdf_units = fetch_admin_layer("8", attica_hull, cache_dir=cache_dir)

    # 3. Run hybrid matching
    print("🔗 Running hybrid matching...")
    matcher = HybridMatcher(community_lookup, municipality_lookup)
    community_assignments = matcher.resolve_coverage(gdf_units, gdf_muns)
    municipality_assignments = matcher.build_municipality_base_layer(gdf_muns)

    # 4. Render coverage map
    print("🗺️  Rendering coverage map...")
    renderer = CoverageMapRenderer()
    renderer.render(
        community_assignments=community_assignments,
        municipality_assignments=municipality_assignments,
        stations=stations,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
