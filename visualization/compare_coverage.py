"""
visualization/compare_coverage.py

Side-by-side interactive map benchmarking the MILP optimized station configuration
against the real-world Hellenic Fire Service (ΠΣ) operational zones.

Left  (Map A) — MILP Optimized: districts colour-coded by their mathematically assigned station.
Right (Map B) — Real-World ΠΣ:  districts colour-coded by the actual ΠΣ operational assignment.

Both panels zoom and pan in sync via folium DualMap.

Usage (from project root):
    python visualization/compare_coverage.py
    python visualization/compare_coverage.py path/to/output.html
"""

import colorsys
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import folium
from folium.plugins import DualMap

from config import (
    AVERAGE_SPEED_KMH,
    FILE_NAME_ASTIKA,
    REGION_ID,
    REGION_NAME,
    REGION_TOTAL_FIRETRUCKS,
)
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from optimization import solve
from utils.dataHandlers.preprocessor import load_districts
from utils.dataHandlers.station_loader import load_stations
from utils.logger import get_logger

logger = get_logger(__name__)

_DATA_DIR = os.path.join(_ROOT, "data")
_RW_FILE = os.path.join(_DATA_DIR, "real_world_fire_stations.json")
_DEFAULT_OUTPUT = os.path.join(_ROOT, "coverage_comparison.html")

_MAP_CENTER = [38.00, 23.75]
_ZOOM_START = 10

# Island district names — excluded by the preprocessor, skip in real-world assignments too.
_ISLAND_PREFIXES = {
    "Δ. ΑΓΚΙΣΤΡΙΟΥ", "Δ. ΑΙΓΙΝΑΣ", "Δ. ΚΥΘΗΡΩΝ",
    "Δ. ΠΟΡΟΥ", "Δ. ΣΑΛΑΜΙΝΑΣ", "Δ. ΣΠΕΤΣΩΝ",
    "Δ. ΤΡΟΙΖΗΝΙΑΣ - ΜΕΘΑΝΩΝ", "Δ. ΥΔΡΑΣ",
}


# ---------------------------------------------------------------------------
# Colour generation — evenly spaced hues, cycling lightness for more stations
# ---------------------------------------------------------------------------

def _palette(station_ids: list[str]) -> dict[str, str]:
    """Return {station_id: "#rrggbb"} with visually distinct colours."""
    n = max(len(station_ids), 1)
    colours: dict[str, str] = {}
    for rank, sid in enumerate(sorted(station_ids)):
        hue = rank / n
        lightness = 0.40 + 0.10 * (rank % 3)   # 0.40 / 0.50 / 0.60 cycle
        r, g, b = colorsys.hls_to_rgb(hue, lightness, 0.82)
        colours[sid] = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    return colours


# ---------------------------------------------------------------------------
# Real-world data loader
# ---------------------------------------------------------------------------

def _load_rw_stations(districts_by_name: dict) -> list[dict]:
    if not os.path.exists(_RW_FILE):
        logger.error(f"Real-world stations file missing: {_RW_FILE}")
        return []

    with open(_RW_FILE, encoding="utf-8") as fh:
        raw = json.load(fh)

    stations: list[dict] = raw if isinstance(raw, list) else raw.get("stations", [])

    for ps in stations:
        resolved = []
        for mname in ps.get("assigned_municipalities", []):
            if mname in _ISLAND_PREFIXES:
                continue
            d = districts_by_name.get(mname)
            if d:
                resolved.append(d)
            else:
                logger.debug(f"[RW] '{mname}' not found in loaded districts — skipped.")
        ps["_districts"] = resolved

    return stations


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------

def _circle_radius(area_km2: float) -> float:
    return max(7, min(32, math.sqrt(area_km2) * 1.05))


def _add_zone_markers(
    target,
    districts,
    district_to_station: dict,      # d.id → station_id  (or d.name → station_id)
    colour_map: dict,
    station_name_map: dict,
    response_time_map: dict | None,
) -> None:
    """Add one zone-coloured CircleMarker per district to target panel."""
    for d in districts:
        sid = district_to_station.get(d.id) or district_to_station.get(d.name)
        colour = colour_map.get(sid, "#b0b0b0") if sid else "#b0b0b0"
        assigned_label = station_name_map.get(sid, "Unassigned") if sid else "Unassigned"

        rt_line = ""
        if response_time_map and sid:
            rt = response_time_map.get((d.id, sid))
            if rt is not None:
                rt_line = f"<br>Response time: <b>{rt:.1f} min</b>"

        popup = (
            f"<b>{d.name}</b><br>"
            f"Risk: {d.wildfire_risk:.1f}  |  Area: {d.area_km2:.0f} km²<br>"
            f"Assigned to: <b>{assigned_label}</b>"
            f"{rt_line}"
        )

        folium.CircleMarker(
            location=[d.lat, d.lon],
            radius=_circle_radius(d.area_km2),
            color="#2c2c2c",
            weight=0.8,
            fill=True,
            fill_color=colour,
            fill_opacity=0.72,
            popup=folium.Popup(popup, max_width=280),
            tooltip=f"{d.name}  →  {assigned_label}",
        ).add_to(target)


def _add_routing_lines(
    target,
    districts,
    district_to_station: dict,
    station_coords: dict,           # station_id → (lat, lon)
    colour_map: dict,
) -> None:
    for d in districts:
        sid = district_to_station.get(d.id) or district_to_station.get(d.name)
        if not sid or sid not in station_coords:
            continue
        slat, slon = station_coords[sid]
        folium.PolyLine(
            locations=[[d.lat, d.lon], [slat, slon]],
            color=colour_map.get(sid, "#888"),
            weight=1.3,
            opacity=0.55,
            dash_array="7 4",
            tooltip=f"{d.name} → {sid}",
        ).add_to(target)


def _add_station_marker(
    target,
    lat: float,
    lon: float,
    name: str,
    icon_colour: str,
    icon_name: str,
    popup_html: str,
    tooltip: str,
) -> None:
    folium.Marker(
        location=[lat, lon],
        icon=folium.Icon(color=icon_colour, icon=icon_name, prefix="fa"),
        popup=folium.Popup(popup_html, max_width=320),
        tooltip=tooltip,
    ).add_to(target)


def _html_legend(title: str, items: list[tuple[str, str]]) -> str:
    """Build a fixed-position HTML legend string for injection."""
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0;">'
        f'<span style="display:inline-block;width:14px;height:14px;border-radius:3px;'
        f'background:{colour};border:1px solid #555;flex-shrink:0;"></span>'
        f'<span style="font-size:11px;">{label}</span></div>'
        for label, colour in items
    )
    return (
        f'<div style="position:fixed;bottom:24px;left:16px;background:rgba(255,255,255,0.93);'
        f'padding:10px 14px;border:1px solid #aaa;border-radius:6px;z-index:9999;'
        f'max-height:280px;overflow-y:auto;min-width:200px;">'
        f'<b style="font-size:12px;">{title}</b><br>'
        f'{rows}</div>'
    )


# ---------------------------------------------------------------------------
# MILP panel builder
# ---------------------------------------------------------------------------

def _build_milp_panel(m1, result, problem, c, colours) -> None:
    station_name_map = {s.id: s.name for s in problem.stations}
    station_coords = {s.id: (s.lat, s.lon) for s in problem.stations}
    assignments = result.district_assignments          # {district_id: station_id}

    # Zone markers
    _add_zone_markers(m1, problem.districts, assignments, colours, station_name_map, c)

    # Routing lines
    _add_routing_lines(m1, problem.districts, assignments, station_coords, colours)

    # Open station markers
    for s in problem.stations:
        if s.id not in result.open_stations:
            continue
        trucks = result.firetruck_allocations.get(s.id, 0)
        covered_ids = [did for did, sid in assignments.items() if sid == s.id]
        covered_names = sorted(
            next((d.name for d in problem.districts if d.id == did), did)
            for did in covered_ids
        )
        rt_avg = (
            sum(c.get((did, s.id), 0) for did in covered_ids) / len(covered_ids)
            if covered_ids else 0.0
        )
        district_rows = "".join(f"<br>&nbsp;&nbsp;• {n}" for n in covered_names)
        popup = (
            f"<b>{s.name}</b><br>"
            f"<span style='color:#1565c0;font-weight:bold;'>OPEN — {trucks} trucks deployed</span><br>"
            f"Capacity: {s.capacity}  |  Cost: {s.cost:,.0f} EUR<br>"
            f"Avg response: {rt_avg:.1f} min<br>"
            f"Districts covered ({len(covered_names)}):{district_rows}"
        )
        _add_station_marker(
            m1, s.lat, s.lon, s.name,
            icon_colour="blue", icon_name="fire",
            popup_html=popup,
            tooltip=f"[MILP] {s.name}  |  {trucks} trucks  |  {len(covered_names)} districts",
        )


# ---------------------------------------------------------------------------
# Real-world panel builder
# ---------------------------------------------------------------------------

def _build_rw_panel(m2, rw_stations, districts, colours) -> None:
    rw_assignment: dict[str, str] = {}
    rw_coords: dict[str, tuple] = {}
    rw_name_map: dict[str, str] = {}

    for ps in rw_stations:
        sid = ps["id"]
        rw_coords[sid] = (ps["lat"], ps["lon"])
        rw_name_map[sid] = ps["name"]
        for d in ps["_districts"]:
            rw_assignment[d.id] = sid
            rw_assignment[d.name] = sid

    # Zone markers (no response-time map for real-world — not computed)
    _add_zone_markers(m2, districts, rw_assignment, colours, rw_name_map, None)

    # Routing lines
    _add_routing_lines(m2, districts, rw_assignment, rw_coords, colours)

    # Station markers
    for ps in rw_stations:
        sid = ps["id"]
        covered = ps["_districts"]
        if not ps["lat"] or not covered and not ps.get("assigned_municipalities"):
            continue
        district_rows = "".join(f"<br>&nbsp;&nbsp;• {d.name}" for d in sorted(covered, key=lambda x: x.name))
        popup = (
            f"<b>{ps['name']}</b><br>"
            f"<span style='color:#b71c1c;font-weight:bold;'>Υφιστάμενος σταθμός ΠΣ Ελλάδος</span><br>"
            f"Districts under command ({len(covered)}):{district_rows}"
        )
        _add_station_marker(
            m2, ps["lat"], ps["lon"], ps["name"],
            icon_colour="red", icon_name="star",
            popup_html=popup,
            tooltip=f"[ΠΣ] {ps['name']}  |  {len(covered)} districts",
        )


# ---------------------------------------------------------------------------
# Title overlay via DivIcon at a geographic anchor
# ---------------------------------------------------------------------------

def _add_title(target, lat: float, lon: float, text: str) -> None:
    folium.Marker(
        [lat, lon],
        icon=folium.DivIcon(
            html=(
                f'<div style="font-size:14px;font-weight:bold;color:#1a1a2e;'
                f'background:rgba(255,255,255,0.90);padding:5px 12px;'
                f'border-radius:5px;border:1px solid #888;white-space:nowrap;">'
                f'{text}</div>'
            ),
            icon_size=(300, 34),
            icon_anchor=(0, 0),
        ),
    ).add_to(target)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_OUTPUT

    # --- Load problem data ---
    region = FireRegion(id=REGION_ID, name=REGION_NAME, total_firetrucks=REGION_TOTAL_FIRETRUCKS)
    districts = load_districts(FILE_NAME_ASTIKA)
    stations = load_stations()

    if not districts or not stations:
        logger.error("Data load failed — aborting.")
        sys.exit(1)

    problem = FireProtectionProblem(region=region, stations=stations, districts=districts)
    districts_by_name = {d.name: d for d in districts}

    # --- Load real-world station assignments ---
    rw_stations = _load_rw_stations(districts_by_name)
    if not rw_stations:
        logger.warning("No real-world station data — right panel will show unassigned districts.")

    # --- Solve MILP ---
    logger.info(f"Problem: {len(stations)} candidates, {len(districts)} districts")
    result = solve(problem)

    if result.status != "Optimal":
        logger.error(f"Solver status: {result.status!r} — cannot generate comparison map.")
        sys.exit(1)

    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)
    logger.info(
        f"MILP: {len(result.open_stations)} open, "
        f"avg {result.avg_response_time_min:.1f} min, "
        f"cost {result.total_operational_cost:,.0f} EUR"
    )

    # --- Colour maps (independent per panel) ---
    milp_colours = _palette(list(result.open_stations))
    rw_colours = _palette([ps["id"] for ps in rw_stations])

    # --- Build DualMap ---
    dual = DualMap(location=_MAP_CENTER, zoom_start=_ZOOM_START, layout="horizontal")

    # Tile layer for both panels
    folium.TileLayer("CartoDB positron").add_to(dual.m1)
    folium.TileLayer("CartoDB positron").add_to(dual.m2)

    # Title banners (geographic anchor: upper-left corner of Attica viewport)
    _add_title(dual.m1, 38.42, 22.85, "MILP Optimized Configuration")
    _add_title(dual.m2, 38.42, 22.85, "Real-World ΠΣ Ground Truth")

    # Populate both panels
    _build_milp_panel(dual.m1, result, problem, c, milp_colours)
    _build_rw_panel(dual.m2, rw_stations, districts, rw_colours)

    # --- HTML colour legends injected into the page root ---
    milp_legend_items = [
        (next((s.name for s in problem.stations if s.id == sid), sid), col)
        for sid, col in sorted(milp_colours.items(), key=lambda x: x[0])
    ]
    rw_legend_items = [
        (next((ps["name"] for ps in rw_stations if ps["id"] == sid), sid), col)
        for sid, col in sorted(rw_colours.items(), key=lambda x: x[0])
    ]

    combined_legend_html = (
        '<div style="position:fixed;bottom:24px;left:24px;display:flex;gap:16px;z-index:9999;">'
        + _html_legend("MILP Stations", milp_legend_items).replace("position:fixed;", "position:relative;")
        + _html_legend("Real-World ΠΣ", rw_legend_items).replace("position:fixed;", "position:relative;")
        + "</div>"
    )
    dual.get_root().html.add_child(folium.Element(combined_legend_html))

    # --- Save ---
    dual.save(output_path)
    logger.info(f"Comparison map saved → {output_path}")
    logger.info("Open in a browser — both panels pan/zoom in sync.")


if __name__ == "__main__":
    main()
