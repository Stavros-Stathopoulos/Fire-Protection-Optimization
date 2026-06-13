"""Solver-agnostic MILP results visualizer.

Ingests standardized ``MilpVisualizationInput`` (plain dicts / dataclasses)
— **NOT** solver objects (PuLP variables, Gurobi models, etc.).

Visual outputs:
  1. Municipality Coverage Polygons — choropleth fill colored by assigned station.
  2. Active vs. Inactive Stations — green fire icons (open) / grey × icons (closed).
  3. Demand-to-Station Allocation — dashed polylines from district centroids to
     assigned stations.
  4. Capacity / Unmet Demand — circle radius proportional to demand.
  5. Response-Time Heatmap — optional layer showing response time as a gradient.
"""

from __future__ import annotations

import colorsys
import math
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import folium

from .models import (
    MilpDistrictAssignment,
    MilpStationStatus,
    MilpVisualizationInput,
)

if TYPE_CHECKING:
    import geopandas as gpd


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _generate_station_palette(
    station_ids: list[str],
) -> dict[str, str]:
    """Assign visually distinct colours to each station via HSL rotation."""
    n = max(len(station_ids), 1)
    palette: dict[str, str] = {}
    for rank, sid in enumerate(sorted(station_ids)):
        hue = rank / n
        lightness = 0.40 + 0.10 * (rank % 3)
        r, g, b = colorsys.hls_to_rgb(hue, lightness, 0.82)
        palette[sid] = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    return palette


def _response_time_colour(minutes: float) -> str:
    """Map response time to a green → yellow → red gradient."""
    if minutes <= 10.0:
        return "#228B22"  # forest green
    if minutes <= 15.0:
        return "#7CFC00"  # lawn green
    if minutes <= 20.0:
        return "#FFD700"  # gold
    if minutes <= 25.0:
        return "#FF8C00"  # dark orange
    return "#CC0000"      # red


def _demand_radius(demand: float) -> float:
    """Circle marker radius proportional to demand."""
    return max(6, min(35, math.sqrt(demand) * 3.5))


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------

def _build_municipality_polygons_layer(
    assignments: list[MilpDistrictAssignment],
    boundaries: gpd.GeoDataFrame,
    palette: dict[str, str],
    station_name_map: dict[str, str],
) -> folium.FeatureGroup:
    """Layer: Choropleth polygons of municipalities colored by assigned MILP station."""
    from .normalization import normalize_name

    fg = folium.FeatureGroup(name="🗺️ Municipality Coverage (MILP)", show=True)

    # O(N) lookup index: normalized_name -> MilpDistrictAssignment
    assignment_map = {normalize_name(a.district_name): a for a in assignments}

    def highlight_fn(_):
        return {
            "weight": 2.5,
            "color": "#222222",
            "fillOpacity": 0.75,
        }

    for _, row in boundaries.iterrows():
        osm_name = str(row["name"])
        norm_name = normalize_name(osm_name)

        # Main exact/aliased lookup
        assignment = assignment_map.get(norm_name)

        # Fallback substring evaluation to guarantee mapping robustness
        if not assignment:
            for key, assoc in assignment_map.items():
                if key in norm_name or norm_name in key:
                    assignment = assoc
                    break

        if assignment:
            color = palette.get(assignment.assigned_station_id, "#b0b0b0")
            station_label = station_name_map.get(assignment.assigned_station_id, "Unassigned")

            popup_html = (
                f"<div style=\"font-family:'Segoe UI',sans-serif; font-size:12px; min-width:220px;\">"
                f"<h4 style=\"margin:0; padding:6px; background:{color}; color:white; border-radius:4px 4px 0 0;\">"
                f"Δήμος {assignment.district_name}</h4>"
                f"<div style=\"padding:8px; border:1px solid #ddd; border-top:none; background:white;\">"
                f"<b>Assigned Structure:</b> <span style=\"color:{color}; font-weight:bold;\">{station_label}</span><br>"
                f"<b>Optimized Response:</b> {assignment.response_time_min:.1f} min<br>"
                f"<b>Demand Weight:</b> {assignment.demand:.1f}<br>"
                f"<b>Wildfire Risk:</b> {assignment.wildfire_risk:.1f}"
                f"</div></div>"
            )

            folium.GeoJson(
                data=row["geometry"].__geo_interface__,
                style_function=lambda _, c=color: {
                    "fillColor": c,
                    "color": "white",
                    "weight": 1.2,
                    "fillOpacity": 0.50,
                },
                highlight_function=highlight_fn,
                tooltip=folium.Tooltip(f"<b>{assignment.district_name}</b> → {station_label} ({assignment.response_time_min:.1f} min)"),
                popup=folium.Popup(popup_html, max_width=320),
            ).add_to(fg)
        else:
            # Map unassigned boundaries cleanly in a muted tone
            folium.GeoJson(
                data=row["geometry"].__geo_interface__,
                style_function=lambda _: {
                    "fillColor": "#8c8c8c",
                    "color": "#d0d0d0",
                    "weight": 1.0,
                    "fillOpacity": 0.15,
                },
                tooltip=folium.Tooltip(f"<b>{osm_name}</b> (No Active MILP Assignment)"),
            ).add_to(fg)

    return fg


def _build_stations_layer(
    statuses: list[MilpStationStatus],
    palette: dict[str, str],
    district_assignments: list[MilpDistrictAssignment],
) -> folium.FeatureGroup:
    """Layer: Active vs. Inactive station markers."""
    fg = folium.FeatureGroup(name="🏢 Stations (MILP Result)", show=True)

    coverage_map: dict[str, list[MilpDistrictAssignment]] = {}
    for da in district_assignments:
        coverage_map.setdefault(da.assigned_station_id, []).append(da)

    for s in statuses:
        colour = "green" if s.is_active else "gray"
        icon_name = "fire" if s.is_active else "times-circle"

        if s.is_active:
            covered = coverage_map.get(s.station_id, [])
            avg_rt = (
                sum(d.response_time_min for d in covered) / len(covered)
                if covered else 0.0
            )
            district_rows = "".join(
                f"<br>&nbsp;&nbsp;• {d.district_name} ({d.response_time_min:.1f} min)"
                for d in sorted(covered, key=lambda x: x.district_name)
            )
            status_str = (
                f"<span style='color:#2e7d32;font-weight:bold;'>OPEN</span>"
                f" — {s.apparatus_count} firetruck{'s' if s.apparatus_count != 1 else ''} deployed"
            )
            region_detail = ""
            if s.region_allocations:
                region_lines = "".join(
                    f"<br>&nbsp;&nbsp;• {rid}: {cnt} truck{'s' if cnt != 1 else ''}"
                    for rid, cnt in sorted(s.region_allocations)
                )
                region_detail = f"ΔΙΠΥ allocation:{region_lines}<br>"
            extra = (
                f"{region_detail}"
                f"Avg response: <b>{avg_rt:.1f} min</b><br>"
                f"Districts covered ({len(covered)}):{district_rows}"
            )
        else:
            status_str = "<span style='color:#757575;'>CLOSED (not selected)</span>"
            extra = ""

        popup_html = (
            f"<div style=\"font-family:'Segoe UI',sans-serif; font-size:12px; max-width:300px;\">"
            f"<b style='font-size:13px;'>🏢 {s.station_name}</b><br>"
            f"Status: {status_str}<br>"
            f"Capacity: {s.capacity}  |  Cost: {s.annual_cost:,.0f} EUR<br>"
            f"{extra}</div>"
        )

        folium.Marker(
            location=[s.lat, s.lon],
            icon=folium.Icon(color=colour, icon=icon_name, prefix="fa"),
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"{'OPEN' if s.is_active else 'CLOSED'} — {s.station_name}",
        ).add_to(fg)

    return fg


def _build_district_zones_layer(
    assignments: list[MilpDistrictAssignment],
    palette: dict[str, str],
    station_name_map: dict[str, str],
) -> folium.FeatureGroup:
    """Layer 2: District demand nodes coloured by assigned station."""
    fg = folium.FeatureGroup(name="📍 Demand Centroids", show=False)

    for d in assignments:
        colour = palette.get(d.assigned_station_id, "#b0b0b0")
        station_label = station_name_map.get(d.assigned_station_id, "Unassigned")

        popup_html = (
            f"<div style=\"font-family:'Segoe UI',sans-serif; font-size:12px;\">"
            f"<b>{d.district_name}</b><br>"
            f"Risk: <b>{d.wildfire_risk:.1f}</b>  |  Area: {d.area_km2:.0f} km²<br>"
            f"Demand: {d.demand:.1f}<br>"
            f"Assigned to: <b>{station_label}</b><br>"
            f"Response time: <b>{d.response_time_min:.1f} min</b>"  # <- ΕΔΩ: Το ' min' βγήκε έξω από το }
            f"</div>"
        )

        folium.CircleMarker(
            location=[d.lat, d.lon],
            radius=_demand_radius(d.demand),
            color="#2c2c2c",
            weight=0.8,
            fill=True,
            fill_color=colour,
            fill_opacity=0.70,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{d.district_name} → {station_label}  ({d.response_time_min:.1f} min)",
        ).add_to(fg)

    return fg


def _build_allocation_routes_layer(
    assignments: list[MilpDistrictAssignment],
    station_coords: dict[str, tuple[float, float]],
    palette: dict[str, str],
) -> folium.FeatureGroup:
    """Layer: Dashed polylines from district to assigned station."""
    fg = folium.FeatureGroup(name="🔗 Allocation Routes", show=True)

    for d in assignments:
        coords = station_coords.get(d.assigned_station_id)
        if coords is None:
            continue
        colour = palette.get(d.assigned_station_id, "#888888")

        folium.PolyLine(
            locations=[[d.lat, d.lon], list(coords)],
            color=colour,
            weight=1.6,
            opacity=0.60,
            dash_array="8 5",
            tooltip=f"{d.district_name} → {d.assigned_station_id}  ({d.response_time_min:.1f} min)",
        ).add_to(fg)

    return fg


def _build_response_heatmap_layer(
    assignments: list[MilpDistrictAssignment],
) -> folium.FeatureGroup:
    """Layer: Response-time colour gradient (green → red)."""
    fg = folium.FeatureGroup(name="⏱️ Response Time Heatmap", show=False)

    for d in assignments:
        colour = _response_time_colour(d.response_time_min)

        folium.CircleMarker(
            location=[d.lat, d.lon],
            radius=_demand_radius(d.demand) * 0.85,
            color=colour,
            weight=1.5,
            fill=True,
            fill_color=colour,
            fill_opacity=0.55,
            tooltip=(
                f"{d.district_name}  |  {d.response_time_min:.1f} min  |  "
                f"risk={d.wildfire_risk:.1f}"
            ),
        ).add_to(fg)

    return fg


def _build_summary_overlay(data: MilpVisualizationInput) -> folium.Element:
    """Fixed-position HTML summary box."""
    active = sum(1 for s in data.station_statuses if s.is_active)
    total = len(data.station_statuses)

    return folium.Element(
        '<div style="position:fixed; top:12px; right:12px; z-index:9999; background:white;'
        " padding:12px 16px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.3);"
        " font-family:'Segoe UI',sans-serif; font-size:12px; line-height:1.8;\">"
        '<b style="font-size:14px">MILP Optimization Summary</b><br>'
        f"Status: <b>{data.solver_status}</b><br>"
        f"Open stations: <b>{active}/{total}</b><br>"
        f"Avg response: <b>{data.avg_response_time_min:.1f} min</b><br>"
        f"Total cost: <b>{data.total_operational_cost:,.0f} EUR</b><br>"
        f"Objective: <b>{data.objective_value:,.2f}</b>"
        "</div>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MilpResultVisualizer:
    """Decoupled MILP optimization output renderer.

    Ingests standardized dicts / dataclasses — **NOT** solver objects.
    """

    def __init__(
        self,
        data: MilpVisualizationInput,
        *,
        center: tuple[float, float] = (38.00, 23.75),
        zoom_start: int = 10,
    ) -> None:
        self._data = data
        self._center = list(center)
        self._zoom = zoom_start

    def render(
        self, 
        output_path: Path | str, 
        boundaries: Optional[gpd.GeoDataFrame] = None
    ) -> folium.Map:
        """Build and save the MILP results map.

        Parameters
        ----------
        output_path:
            File path for the saved HTML.
        boundaries:
            Optional GeoDataFrame containing municipality polygons. If None,
            the method attempts lazy fetching via osm_fetcher.
        """
        m = folium.Map(
            location=self._center,
            zoom_start=self._zoom,
            tiles="CartoDB positron",
        )

        # Self-healing configuration fallback for JSON deserialization
        if boundaries is None and self._data.boundaries is not None:
            boundaries = self._data.boundaries  # type: ignore[assignment]

        if boundaries is None:
            print("🌍 Boundaries missing from context. Lazily fetching Attica admin_level=7 from OSM...")
            try:
                from .osm_fetcher import fetch_admin_layer, fetch_attica_hull
                attica_hull = fetch_attica_hull()
                boundaries = fetch_admin_layer("7", attica_hull)
            except Exception as err:
                print(f"⚠️ Failed to dynamically load admin boundaries: {err}. Rendering without polygons.")

        # Build palette from active stations
        active_ids = [s.station_id for s in self._data.station_statuses if s.is_active]
        palette = _generate_station_palette(active_ids)

        station_name_map = {
            s.station_id: s.station_name for s in self._data.station_statuses
        }
        station_coords = {
            s.station_id: (s.lat, s.lon) for s in self._data.station_statuses
        }

        # Step 1: Add the requested Choropleth Boundary Layer FIRST so it forms the background
        if boundaries is not None:
            m.add_child(
                _build_municipality_polygons_layer(
                    self._data.district_assignments, boundaries, palette, station_name_map
                )
            )

        # Step 2: Overlay point markers, vectors, and analytics layers on top
        m.add_child(
            _build_stations_layer(
                self._data.station_statuses, palette, self._data.district_assignments,
            )
        )
        m.add_child(
            _build_allocation_routes_layer(
                self._data.district_assignments, station_coords, palette,
            )
        )
        m.add_child(
            _build_district_zones_layer(
                self._data.district_assignments, palette, station_name_map,
            )
        )
        m.add_child(
            _build_response_heatmap_layer(self._data.district_assignments)
        )

        # Summary overlay & layer control
        m.get_root().html.add_child(_build_summary_overlay(self._data))
        folium.LayerControl(collapsed=False).add_to(m)

        # Persist to disk
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(output))
        print(f"✅ MILP visualization saved → {output}")

        return m

    @classmethod
    def from_json(
        cls,
        path: "Path | str",
        **kwargs: object,
    ) -> "MilpResultVisualizer":
        """Build a visualizer directly from a full format JSON file."""
        import json as _json

        with open(Path(path), encoding="utf-8") as fh:
            data: dict = _json.load(fh)

        if "stations" not in data or "districts" not in data:
            raise ValueError(
                f"{path!r} lacks required station/district metadata."
            )

        station_statuses = [
            MilpStationStatus(
                station_id=s["id"],
                station_name=s["name"],
                lat=float(s["lat"]),
                lon=float(s["lon"]),
                is_active=bool(s["is_active"]),
                apparatus_count=int(s["total_trucks"]),
                capacity=int(s["capacity"]),
                annual_cost=float(s["annual_cost"]),
                region_allocations=tuple(
                    sorted(s.get("region_allocations", {}).items())
                ),
            )
            for s in data["stations"]
        ]

        district_assignments = [
            MilpDistrictAssignment(
                district_id=d["id"],
                district_name=d["name"],
                lat=float(d["lat"]),
                lon=float(d["lon"]),
                assigned_station_id=str(d["assigned_station_id"]),
                response_time_min=float(d["response_time_min"]),
                demand=float(d["demand"]),
                area_km2=float(d["area_km2"]),
                wildfire_risk=float(d["wildfire_risk"]),
            )
            for d in data["districts"]
        ]

        viz_data = MilpVisualizationInput(
            station_statuses=station_statuses,
            district_assignments=district_assignments,
            solver_status=str(data.get("status", "Unknown")),
            objective_value=float(data.get("objective_value", 0.0)),
            total_operational_cost=float(data.get("total_operational_cost", 0.0)),
            avg_response_time_min=float(data.get("avg_response_time_min", 0.0)),
        )

        return cls(viz_data, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_optimization_result(
        cls,
        result: object,
        problem: object,
        response_times: dict[tuple[str, str], float],
        **kwargs: object,
    ) -> "MilpResultVisualizer":
        """Convenience factory that bridges OptimizationResult to the visualizer."""
        from domain.problem import FireProtectionProblem
        from optimization.result import OptimizationResult

        prob: FireProtectionProblem = problem  # type: ignore[assignment]
        res: OptimizationResult = result  # type: ignore[assignment]

        station_trucks = res.station_total_trucks

        station_statuses = []
        for s in prob.stations:
            region_allocs: list[tuple[str, int]] = []
            for r in prob.regions:
                count = res.firetruck_allocations.get((r.id, s.id), 0)
                if count > 0:
                    region_allocs.append((r.id, count))

            station_statuses.append(
                MilpStationStatus(
                    station_id=s.id,
                    station_name=s.name,
                    lat=s.lat,
                    lon=s.lon,
                    is_active=s.id in res.open_stations,
                    apparatus_count=station_trucks.get(s.id, 0),
                    capacity=s.capacity,
                    annual_cost=s.cost,
                    region_allocations=tuple(region_allocs),
                )
            )

        district_assignments = [
            MilpDistrictAssignment(
                district_id=d.id,
                district_name=d.name,
                lat=d.lat,
                lon=d.lon,
                assigned_station_id=res.district_assignments.get(d.id, ""),
                response_time_min=response_times.get(
                    (d.id, res.district_assignments.get(d.id, "")), 0.0
                ),
                demand=d.demand,
                area_km2=d.area_km2,
                wildfire_risk=d.wildfire_risk,
            )
            for d in prob.districts
        ]

        data = MilpVisualizationInput(
            station_statuses=station_statuses,
            district_assignments=district_assignments,
            solver_status=res.status,
            objective_value=res.objective_value,
            total_operational_cost=res.total_operational_cost,
            avg_response_time_min=res.avg_response_time_min,
        )

        return cls(data, **kwargs)  # type: ignore[arg-type]