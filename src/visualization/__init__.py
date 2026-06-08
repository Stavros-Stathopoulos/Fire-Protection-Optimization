"""Operational coverage visualization package for Attica fire stations.

Public API
----------
- ``StationDataParser``     — Hierarchical JSON parser for station coverage data.
- ``CoverageMapRenderer``   — Folium renderer for operational coverage maps.
- ``MilpResultVisualizer``  — Solver-agnostic MILP results visualizer.
- ``HybridMatcher``         — OSM-to-station spatial matching engine.

Usage
-----
As a library::

    from src.visualization import StationDataParser, CoverageMapRenderer

As a CLI (from project root)::

    python -m src.visualization.cli
"""

from .coverage_renderer import CoverageMapRenderer
from .matcher import HybridMatcher
from .milp_visualizer import MilpResultVisualizer
from .parser import StationDataParser

__all__ = [
    "CoverageMapRenderer",
    "HybridMatcher",
    "MilpResultVisualizer",
    "StationDataParser",
]
