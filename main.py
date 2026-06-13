"""Fire-protection optimization entry point.

Multi-region formulation with 4 ΔΙΠΥ directorates.

Usage:
    python main.py
    python main.py --budget 10000000
    python main.py --budget 10000000 --output results/solution.json
    python main.py --no-map
    python main.py --map-output public/milp_map.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import FILE_NAME_ASTIKA, REGIONS
from config.milp_config import AVERAGE_SPEED_KMH
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from optimization import solve
from utils.dataHandlers.preprocessor import load_districts
from utils.dataHandlers.station_loader import load_stations
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_JSON_OUTPUT = Path("results") / "optimization_result.json"
_DEFAULT_MAP_OUTPUT  = Path("public") / "milp_map.html"


def _build_regions() -> list[FireRegion]:
    """Construct FireRegion objects from the REGIONS config list."""
    return [
        FireRegion(
            id=str(r["id"]),
            name=str(r["name"]),
            total_firetrucks=int(r["total_firetrucks"]),
        )
        for r in REGIONS
    ]


def _report(
    result: object,
    problem: FireProtectionProblem,
    response_times: dict[tuple[str, str], float],
) -> None:
    """Log a detailed breakdown of the optimization solution."""
    # Lazy import to avoid circular references at module level
    from optimization.result import OptimizationResult
    res: OptimizationResult = result  # type: ignore[assignment]

    station_map = {s.id: s.name for s in problem.stations}
    d_meta = {d.id: d for d in problem.districts}
    c = response_times

    # Risk-weighted average
    assignments = res.district_assignments
    total_weight = sum(d_meta[did].demand * d_meta[did].wildfire_risk for did in assignments)
    risk_weighted_avg = (
        sum(
            d_meta[did].demand * d_meta[did].wildfire_risk * c[(did, sid)]
            for did, sid in assignments.items()
        ) / total_weight
        if total_weight else 0.0
    )

    logger.info("=" * 70)
    logger.info(f"Status:                   {res.status}")
    logger.info(f"Open stations:            {len(res.open_stations)} / {len(problem.stations)}")
    logger.info(f"Avg response time:        {res.avg_response_time_min:.1f} min  (simple avg, all districts)")
    logger.info(f"Risk-weighted avg:        {risk_weighted_avg:.1f} min  (weighted by demand x risk)")
    logger.info(f"Operational cost:         {res.total_operational_cost:,.0f} EUR")
    logger.info("-" * 70)

    # Per-region deployment summary
    logger.info("DIPY Regional Fleet Deployment:")
    for region in problem.regions:
        deployed = res.region_total_deployed.get(region.id, 0)
        logger.info(f"  {region.name}: {deployed}/{region.total_firetrucks} trucks deployed")
    logger.info("-" * 70)

    # Per-station detail
    station_trucks = res.station_total_trucks
    for sid in sorted(res.open_stations):
        trucks = station_trucks.get(sid, 0)
        covered_dids = [did for did, asid in assignments.items() if asid == sid]
        avg_rt = (
            sum(c[(did, sid)] for did in covered_dids) / len(covered_dids)
            if covered_dids else 0.0
        )

        # Per-region breakdown for this station
        region_parts: list[str] = []
        for region in problem.regions:
            count = res.firetruck_allocations.get((region.id, sid), 0)
            if count > 0:
                region_parts.append(f"{region.id}={count}")
        region_str = ", ".join(region_parts) if region_parts else "none"

        logger.info(f"  {station_map.get(sid, sid)}")
        logger.info(f"    avg response   : {avg_rt:.1f} min  |  firetrucks: {trucks} [{region_str}]")
        for did in sorted(covered_dids, key=lambda d: -d_meta[d].wildfire_risk):
            d = d_meta[did]
            rt = c[(did, sid)]
            logger.info(f"      {d.name:<50s}  risk={d.wildfire_risk:.1f}  area={d.area_km2:6.1f}km2  {rt:.1f}min")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fire-protection MILP optimizer for Attica.",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Override MAX_BUDGET (EUR). Omit to use config default.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_JSON_OUTPUT,
        help="Output JSON file path for the optimization result.",
    )
    parser.add_argument(
        "--map-output",
        type=Path,
        default=_DEFAULT_MAP_OUTPUT,
        dest="map_output",
        help="Output HTML file path for the interactive map.",
    )
    parser.add_argument(
        "--no-map",
        action="store_true",
        dest="no_map",
        help="Skip rendering the interactive HTML map.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("public") / "milp_report.html",
        dest="report_output",
        help="Output path for the HTML executive dashboard (default: public/milp_report.html).",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        dest="no_report",
        help="Skip generating the HTML executive dashboard.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    regions = _build_regions()
    districts = load_districts(FILE_NAME_ASTIKA)
    stations = load_stations()

    if not districts:
        logger.error("No districts loaded — check municipalities.json coverage.")
        return
    if not stations:
        logger.error("No fire stations loaded — check fire_stations.json.")
        return

    problem = FireProtectionProblem(regions=regions, stations=stations, districts=districts)
    logger.info(
        f"Problem built — {len(stations)} candidate stations, "
        f"{len(districts)} districts, "
        f"total demand = {problem.total_demand:.2f}, "
        f"{len(regions)} DIPY regions, total fleet = {problem.total_fleet} trucks"
    )

    if args.budget is not None:
        logger.info(f"Budget override: {args.budget:,.0f} EUR")

    result = solve(problem, max_budget=args.budget)

    if result.status != "Optimal":
        logger.error(
            f"No feasible plan available (solver status: '{result.status}'). "
            "Review RISK_COVERAGE_MAX_TIMES constraints or expand station infrastructure."
        )
        return

    response_times = problem.response_time_matrix(AVERAGE_SPEED_KMH)
    _report(result, problem, response_times)

    # Serialize to JSON — full format includes station/district metadata so the
    # src/visualization module can reconstruct the map from the file alone.
    result.to_full_json(args.output, problem, response_times)
    logger.info(f"Result serialized to {args.output}")

    if not args.no_map:
        from src.visualization.milp_visualizer import MilpResultVisualizer
        MilpResultVisualizer.from_json(args.output).render(args.map_output)
        logger.info(f"Interactive map saved to {args.map_output}")

    if not args.no_report:
        from src.visualization.html_reporter import MilpHtmlReporter
        MilpHtmlReporter(result, problem, response_times).generate_report(args.report_output)
        logger.info(f"Executive dashboard saved to {args.report_output}")


if __name__ == "__main__":
    main()
