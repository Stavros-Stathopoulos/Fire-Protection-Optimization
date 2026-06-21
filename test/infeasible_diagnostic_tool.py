"""Diagnostic tool: identifies districts that are geometrically infeasible.

Reports every district whose minimum response time from any candidate station
exceeds the risk-based hard bound defined in ``RISK_COVERAGE_MAX_TIMES``.
Also flags districts that are feasible but within 10 % of their bound.

Usage::

    python test/infeasible_diagnostic_tool.py
    python -m test.infeasible_diagnostic_tool
"""

import io
import math
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from config import FILE_NAME_ASTIKA
from config.milp_config import AVERAGE_SPEED_KMH, REGIONS, RISK_COVERAGE_MAX_TIMES
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from utils.dataHandlers.preprocessor import load_districts
from utils.dataHandlers.station_loader import load_stations


def main() -> None:
    """Run the geographic feasibility check and print a diagnostic report.

    Computes the full response-time matrix (identical to what
    :func:`~optimization.model.build_model` receives), then classifies every
    district as **infeasible**, **tight** (< 10 % margin), or **OK**.

    Returns
    -------
    None
        Output is written directly to stdout.
    """
    regions = [
        FireRegion(
            id=str(r["id"]),
            name=str(r["name"]),
            total_firetrucks=int(r["total_firetrucks"]),
        )
        for r in REGIONS
    ]

    districts = load_districts(FILE_NAME_ASTIKA)
    stations = load_stations()

    problem = FireProtectionProblem(regions=regions, stations=stations, districts=districts)
    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)

    print("=" * 65)
    print("  DIAGNOSTIC: GEOGRAPHIC FEASIBILITY vs RISK COVERAGE BOUNDS")
    print("=" * 65)

    infeasible: list = []
    feasible_tight: list = []

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
            print(
                f"    intra-dist.  : {intra:.1f} min  "
                f"travel: {min_t - intra - 1.3:.1f} min  dispatch: 1.3 min"
            )
            print()
    else:
        print("\n[OK]  All districts have at least one station within their time bound.")

    if feasible_tight:
        print(f"[WARNING]  {len(feasible_tight)} district(s) within bound but with <10% margin:\n")
        for d, s, min_t, max_t in feasible_tight:
            print(
                f"  {d.name}  risk={d.wildfire_risk}  "
                f"min={min_t:.1f} min / bound={max_t:.0f} min  ({s.name})"
            )

    print()
    print(f"Districts checked : {len(problem.districts)}")
    print(f"Infeasible        : {len(infeasible)}")
    print(f"Tight (<10% slack): {len(feasible_tight)}")
    print(f"Comfortably OK    : {len(problem.districts) - len(infeasible) - len(feasible_tight)}")
    print("=" * 65)

    if infeasible:
        print("\nRECOMMENDATION: Add candidate stations near the infeasible")
        print("districts or relax RISK_COVERAGE_MAX_TIMES for those risk levels.")


if __name__ == "__main__":
    main()
