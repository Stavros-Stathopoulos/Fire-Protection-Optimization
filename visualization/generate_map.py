"""
visualization/generate_map.py
Generates an interactive HTML map of the MILP fire protection optimization results.

Optimal mode (model solved):
  1. Incident Districts  — circles colour-coded by wildfire risk (Dark Red 5.0 → Green 1.0).
  2. Candidate Stations  — blue markers (OPEN), grey markers (CLOSED).
  3. Real-World ΠΣ       — red star markers, actual Hellenic Fire Service station locations.
  4. Assignment Routes   — dashed polylines from each district centroid to its assigned station.

Diagnostic mode (model infeasible):
  Same layers 2 & 3, plus districts colour-coded by feasibility status:
    Red   = min achievable time EXCEEDS the risk bound (geometrically infeasible).
    Yellow = within bound but <10 % margin (tight).
    Green  = comfortably within bound.

Usage
-----
From the project root:
    python visualization/generate_map.py
    python visualization/generate_map.py path/to/output.html
"""

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import folium

from config import (
    AVERAGE_SPEED_KMH,
    FILE_NAME_ASTIKA,
    REGION_ID,
    REGION_NAME,
    REGION_TOTAL_FIRETRUCKS,
    RISK_COVERAGE_MAX_TIMES,
)
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from optimization import solve
from utils.dataHandlers.preprocessor import load_districts
from utils.dataHandlers.station_loader import load_stations
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_OUTPUT = os.path.join(_ROOT, "attica_fire_coverage_map.html")
_MAP_CENTER = [38.00, 23.75]
_ZOOM_START = 10

# Risk factor → fill colour (5.0 = extreme forest, 1.0 = low urban)
_RISK_COLOURS: dict[float, str] = {
    5.0: "#8B0000",
    4.5: "#CC0000",
    4.0: "#FF4500",
    3.5: "#FF8C00",
    3.0: "#FFC200",
    2.5: "#FFD700",
    2.0: "#ADFF2F",
    1.5: "#90EE90",
    1.0: "#228B22",
}

# Actual Hellenic Fire Service stations in Attica (ground-truth baseline).
_REAL_WORLD_STATIONS: list[dict] = [
    {"name": "1ος ΠΣ Αθηνών",      "unit": "Λ. Αλεξάνδρας",              "lat": 37.9826, "lon": 23.7268},
    {"name": "2ος ΠΣ Αθηνών",      "unit": "Νέος Κόσμος",                 "lat": 37.9503, "lon": 23.7290},
    {"name": "3ος ΠΣ Αθηνών",      "unit": "Αγ. Βαρβάρα",                 "lat": 37.9930, "lon": 23.6670},
    {"name": "ΠΣ Πειραιά",         "unit": "Πειραιάς",                     "lat": 37.9450, "lon": 23.6460},
    {"name": "ΠΣ Κερατσινίου",     "unit": "Κερατσίνι",                    "lat": 37.9620, "lon": 23.6250},
    {"name": "ΠΣ Νίκαιας",         "unit": "Νίκαια",                       "lat": 37.9670, "lon": 23.6640},
    {"name": "ΠΣ Περιστερίου",     "unit": "Περιστέρι",                    "lat": 38.0130, "lon": 23.6890},
    {"name": "ΠΣ Αιγάλεω",         "unit": "Αιγάλεω",                      "lat": 37.9950, "lon": 23.6820},
    {"name": "ΠΣ Ιλίου",           "unit": "Ίλιον",                        "lat": 38.0220, "lon": 23.7010},
    {"name": "ΠΣ Νέας Ιωνίας",     "unit": "Νέα Ιωνία",                    "lat": 38.0280, "lon": 23.7620},
    {"name": "ΠΣ Χαλανδρίου",      "unit": "Χαλάνδρι",                     "lat": 38.0130, "lon": 23.7980},
    {"name": "ΠΣ Αμαρουσίου",      "unit": "Μαρούσι",                      "lat": 38.0560, "lon": 23.8010},
    {"name": "ΠΣ Κηφισιάς",        "unit": "Κηφισιά",                      "lat": 38.0700, "lon": 23.8140},
    {"name": "ΠΣ Αχαρνών",         "unit": "Αχαρνές",                      "lat": 38.0780, "lon": 23.7390},
    {"name": "ΠΣ Γλυφάδας",        "unit": "Γλυφάδα",                      "lat": 37.8760, "lon": 23.7520},
    {"name": "ΠΣ Καλλιθέας",       "unit": "Καλλιθέα",                     "lat": 37.9560, "lon": 23.7030},
    {"name": "ΠΣ Ελευσίνας",       "unit": "Ελευσίνα",                     "lat": 38.0650, "lon": 23.5410},
    {"name": "ΠΣ Ασπροπύργου",     "unit": "Ασπρόπυργος",                  "lat": 38.0630, "lon": 23.5970},
    {"name": "ΠΣ Μεγάρων",         "unit": "Μέγαρα",                       "lat": 37.9960, "lon": 23.3410},
    {"name": "ΠΣ Κορωπίου",        "unit": "Κορωπί",                       "lat": 37.8920, "lon": 23.8770},
    {"name": "ΠΣ Σπάτων",          "unit": "Σπάτα",                        "lat": 37.9640, "lon": 23.9160},
    {"name": "ΠΣ Ραφήνας",         "unit": "Ραφήνα",                       "lat": 38.0190, "lon": 24.0020},
    {"name": "ΠΣ Μαραθώνα",        "unit": "Μαραθώνας",                    "lat": 38.1570, "lon": 23.9630},
    {"name": "ΠΣ Νέας Μάκρης",     "unit": "Νέα Μάκρη",                    "lat": 38.0900, "lon": 23.9820},
    {"name": "ΠΣ Λαυρίου",         "unit": "Λαύριο",                       "lat": 37.7160, "lon": 24.0530},
    {"name": "ΠΣ Μαρκοπούλου",     "unit": "Μαρκόπουλο Μεσογαίας",        "lat": 37.8833, "lon": 23.9333},
    {"name": "ΕΚΚ Καπανδριτίου",   "unit": "Εποχ. Κλιμάκιο Ωρωπός",      "lat": 38.3015, "lon": 23.7910},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk_colour(risk: float) -> str:
    return _RISK_COLOURS.get(risk, "#808080")


def _circle_radius(area_km2: float) -> float:
    return max(5, min(30, math.sqrt(area_km2) * 0.9))


def _min_achievable_time(d, stations, c: dict) -> tuple:
    """Return (best_station, min_time) over all candidate stations."""
    best = min(stations, key=lambda s: c[(d.id, s.id)])
    return best, c[(d.id, best.id)]


# ---------------------------------------------------------------------------
# Optimal-mode layers
# ---------------------------------------------------------------------------

def _build_districts_layer(districts, assignments, station_name_map, c) -> folium.FeatureGroup:
    fg = folium.FeatureGroup(name="Incident Districts", show=True)

    for d in districts:
        colour = _risk_colour(d.wildfire_risk)
        sid = assignments.get(d.id)
        assigned_name = station_name_map.get(sid, "—") if sid else "—"
        rt = c.get((d.id, sid)) if sid else None
        rt_str = f"{rt:.1f} min" if rt is not None else "—"

        popup_html = (
            f"<b>{d.name}</b><br>"
            f"Wildfire Risk: <b>{d.wildfire_risk:.1f}</b><br>"
            f"Area: {d.area_km2:.1f} km²<br>"
            f"Demand (dk): {d.demand:.2f}<br>"
            f"Assigned to: {assigned_name}<br>"
            f"Response time: <b>{rt_str}</b>"
        )
        folium.CircleMarker(
            location=[d.lat, d.lon],
            radius=_circle_radius(d.area_km2),
            color=colour, fill=True, fill_color=colour, fill_opacity=0.50, weight=1.5,
            popup=folium.Popup(popup_html, max_width=270),
            tooltip=f"{d.name}  |  risk={d.wildfire_risk:.1f}  |  {rt_str}",
        ).add_to(fg)

    return fg


def _build_candidates_layer(stations, open_stations, allocations) -> folium.FeatureGroup:
    fg = folium.FeatureGroup(name="Candidate Stations (model)", show=True)

    for s in stations:
        is_open = s.id in open_stations
        colour = "blue" if is_open else "gray"
        trucks = allocations.get(s.id, 0)
        status_str = f"OPEN — {trucks} firetrucks deployed" if is_open else "CLOSED (not selected)"

        popup_html = (
            f"<b>{s.name}</b><br>"
            f"Status: <b>{status_str}</b><br>"
            f"Capacity (sj): {s.capacity}<br>"
            f"Annual cost: {s.cost:,.0f} EUR"
        )
        folium.Marker(
            location=[s.lat, s.lon],
            icon=folium.Icon(color=colour, icon="fire" if is_open else "times-circle", prefix="fa"),
            popup=folium.Popup(popup_html, max_width=270),
            tooltip=f"{s.name}  |  {status_str}",
        ).add_to(fg)

    return fg


def _build_real_stations_layer() -> folium.FeatureGroup:
    fg = folium.FeatureGroup(name="Real-World ΠΣ Stations (ground truth)", show=True)

    for ps in _REAL_WORLD_STATIONS:
        popup_html = (
            f"<b>{ps['name']}</b><br>"
            f"Τοποθεσία: {ps['unit']}<br>"
            f"<i>Υφιστάμενος σταθμός ΠΣ Ελλάδος</i>"
        )
        folium.Marker(
            location=[ps["lat"], ps["lon"]],
            icon=folium.Icon(color="red", icon="star", prefix="fa"),
            popup=folium.Popup(popup_html, max_width=230),
            tooltip=ps["name"],
        ).add_to(fg)

    return fg


def _build_routing_layer(districts, assignments, station_obj_map, c) -> folium.FeatureGroup:
    fg = folium.FeatureGroup(name="Assignment Routes", show=True)

    for d in districts:
        sid = assignments.get(d.id)
        if sid is None:
            continue
        s = station_obj_map[sid]
        rt = c.get((d.id, sid))
        rt_str = f"{rt:.1f} min" if rt is not None else "?"

        folium.PolyLine(
            locations=[[d.lat, d.lon], [s.lat, s.lon]],
            color=_risk_colour(d.wildfire_risk),
            weight=1.8, opacity=0.65, dash_array="8 5",
            tooltip=f"{d.name} → {s.name}  ({rt_str})",
        ).add_to(fg)

    return fg


# ---------------------------------------------------------------------------
# Diagnostic-mode layer (infeasible model)
# ---------------------------------------------------------------------------

def _build_diagnostic_layer(districts, stations, c) -> folium.FeatureGroup:
    """Colour districts by feasibility gap vs their RISK_COVERAGE_MAX_TIMES bound."""
    fg = folium.FeatureGroup(name="Districts — Feasibility Diagnostic", show=True)

    for d in districts:
        best_s, min_time = _min_achievable_time(d, stations, c)
        bound = RISK_COVERAGE_MAX_TIMES.get(d.wildfire_risk)

        if bound is None:
            colour, status = "#808080", "No bound"
        elif min_time > bound:
            gap = min_time - bound
            colour = "#CC0000"
            status = f"INFEASIBLE — over by {gap:.1f} min (best: {min_time:.1f} min, bound: {bound:.0f} min)"
        elif min_time > bound * 0.90:
            colour = "#FFD700"
            status = f"TIGHT — {min_time:.1f} min / {bound:.0f} min bound"
        else:
            colour = "#228B22"
            status = f"OK — {min_time:.1f} min / {bound:.0f} min bound"

        radius_km = math.sqrt(d.area_km2 / math.pi)
        intra = radius_km / AVERAGE_SPEED_KMH * 60 * 0.5

        popup_html = (
            f"<b>{d.name}</b><br>"
            f"Risk: {d.wildfire_risk:.1f}  |  Area: {d.area_km2:.1f} km²<br>"
            f"Best station: {best_s.name}<br>"
            f"Min achievable: {min_time:.1f} min<br>"
            f"  • Intra-district: {intra:.1f} min<br>"
            f"  • Travel + dispatch: {min_time - intra:.1f} min<br>"
            f"<b>{status}</b>"
        )
        folium.CircleMarker(
            location=[d.lat, d.lon],
            radius=_circle_radius(d.area_km2),
            color=colour, fill=True, fill_color=colour, fill_opacity=0.55, weight=2.0,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{d.name}  |  {status}",
        ).add_to(fg)

    return fg


# ---------------------------------------------------------------------------
# Map builders
# ---------------------------------------------------------------------------

def generate_optimal_map(result, problem: FireProtectionProblem) -> folium.Map:
    m = folium.Map(location=_MAP_CENTER, zoom_start=_ZOOM_START, tiles="CartoDB positron")
    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)
    station_obj_map = {s.id: s for s in problem.stations}
    station_name_map = {s.id: s.name for s in problem.stations}
    assignments = result.district_assignments

    m.add_child(_build_districts_layer(problem.districts, assignments, station_name_map, c))
    m.add_child(_build_candidates_layer(problem.stations, result.open_stations, result.firetruck_allocations))
    m.add_child(_build_real_stations_layer())
    m.add_child(_build_routing_layer(problem.districts, assignments, station_obj_map, c))
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def generate_diagnostic_map(problem: FireProtectionProblem) -> folium.Map:
    m = folium.Map(location=_MAP_CENTER, zoom_start=_ZOOM_START, tiles="CartoDB positron")
    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)

    m.add_child(_build_diagnostic_layer(problem.districts, problem.stations, c))
    # Show all candidate stations as grey (none open since model is infeasible)
    m.add_child(_build_candidates_layer(problem.stations, set(), {}))
    m.add_child(_build_real_stations_layer())
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_OUTPUT

    region = FireRegion(id=REGION_ID, name=REGION_NAME, total_firetrucks=REGION_TOTAL_FIRETRUCKS)
    districts = load_districts(FILE_NAME_ASTIKA)
    stations = load_stations()

    if not districts or not stations:
        logger.error("Data load failed — check municipalities.json and fire_stations.json.")
        sys.exit(1)

    problem = FireProtectionProblem(region=region, stations=stations, districts=districts)
    logger.info(
        f"Problem: {len(stations)} candidate stations, {len(districts)} districts, "
        f"total demand = {problem.total_demand:.2f}"
    )

    result = solve(problem)

    if result.status == "Optimal":
        logger.info(
            f"Solution: {len(result.open_stations)} stations open, "
            f"avg response = {result.avg_response_time_min:.1f} min, "
            f"cost = {result.total_operational_cost:,.0f} EUR"
        )
        m = generate_optimal_map(result, problem)
        logger.info("Generating optimal coverage map.")
    else:
        logger.warning(
            f"Solver status: {result.status!r} — switching to diagnostic mode. "
            "Map will show each district's minimum achievable time vs its bound."
        )
        m = generate_diagnostic_map(problem)

    m.save(output_path)
    logger.info(f"Map saved → {output_path}")
    logger.info("Open the HTML file in any browser to explore the interactive map.")


if __name__ == "__main__":
    main()
