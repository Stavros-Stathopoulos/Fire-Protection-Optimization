"""Diagnostic script: identifies districts that are geometrically infeasible
under the current RISK_COVERAGE_MAX_TIMES bounds.

Run with:  python test.py
"""

import io
import math
import sys

# Force UTF-8 so Greek names print correctly on Windows consoles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from config.milp_config import (
    AVERAGE_SPEED_KMH,
    REGION_ID,
    REGION_NAME,
    REGION_TOTAL_FIRETRUCKS,
    RISK_COVERAGE_MAX_TIMES,
)
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from utils.dataHandlers.preprocessor import load_districts
from utils.dataHandlers.station_loader import load_stations

# --- Build the same problem object the solver uses ---
region = FireRegion(
    id=REGION_ID,
    name=REGION_NAME,
    total_firetrucks=REGION_TOTAL_FIRETRUCKS,
)
districts = load_districts()
stations = load_stations()
problem = FireProtectionProblem(region=region, stations=stations, districts=districts)

# Compute the full response-time matrix (identical to what build_model receives)
c = problem.response_time_matrix(AVERAGE_SPEED_KMH)

print("=" * 65)
print("  DIAGNOSTIC: GEOGRAPHIC FEASIBILITY vs RISK COVERAGE BOUNDS")
print("=" * 65)

infeasible = []
feasible_tight = []  # within bound but < 10 % margin

for d in problem.districts:
    max_t = RISK_COVERAGE_MAX_TIMES.get(d.wildfire_risk)
    if max_t is None:
        continue

    best_station = min(problem.stations, key=lambda s: c[(d.id, s.id)])
    min_time = c[(d.id, best_station.id)]

    if min_time > max_t:
        infeasible.append((d, best_station, min_time, max_t))
    elif min_time > max_t * 0.90:
        feasible_tight.append((d, best_station, min_time, max_t))

# --- Report: infeasible districts ---
if infeasible:
    print(f"\n[INFEASIBLE]  {len(infeasible)} district(s) unreachable within their time bound:\n")
    for d, s, min_t, max_t in sorted(infeasible, key=lambda x: x[2] - x[3], reverse=True):
        gap = min_t - max_t
        radius = math.sqrt(d.area_km2 / math.pi)
        intra = radius / AVERAGE_SPEED_KMH * 60 * 0.5
        print(f"  {d.name}")
        print(f"    risk={d.wildfire_risk}  area={d.area_km2:.0f} km2  bound={max_t:.0f} min")
        print(f"    best station : {s.name}")
        print(f"    min time     : {min_t:.1f} min  (over by {gap:.1f} min)")
        print(f"    intra-dist.  : {intra:.1f} min  travel: {min_t - intra - 1.3:.1f} min  dispatch: 1.3 min")
        print()
else:
    print("\n[OK]  All districts have at least one station within their time bound.")

# --- Report: districts near the edge ---
if feasible_tight:
    print(f"[WARNING]  {len(feasible_tight)} district(s) within bound but with <10% margin:\n")
    for d, s, min_t, max_t in feasible_tight:
        print(f"  {d.name}  risk={d.wildfire_risk}  min={min_t:.1f} min / bound={max_t:.0f} min  ({s.name})")

# --- Summary ---
print()
print(f"Districts checked : {len(problem.districts)}")
print(f"Infeasible        : {len(infeasible)}")
print(f"Tight (<10% slack): {len(feasible_tight)}")
print(f"Comfortably OK    : {len(problem.districts) - len(infeasible) - len(feasible_tight)}")
print("=" * 65)

if infeasible:
    print("\nRECOMMENDATION: Add candidate stations near the infeasible")
    print("districts or relax RISK_COVERAGE_MAX_TIMES for those risk levels.")
