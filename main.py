"""Fire-protection optimization entry point.

Usage:
    python main.py
"""

from config import FILE_NAME_ASTIKA
from config.milp_config import AVERAGE_SPEED_KMH, REGION_ID, REGION_NAME, REGION_TOTAL_FIRETRUCKS
from domain.entities import FireRegion
from domain.problem import FireProtectionProblem
from optimization import solve
from utils.dataHandlers.preprocessor import load_districts
from utils.dataHandlers.station_loader import load_stations
from utils.logger import get_logger

logger = get_logger(__name__)


def _report(result, problem: FireProtectionProblem) -> None:
    station_map = {s.id: s.name for s in problem.stations}
    d_meta = {d.id: d for d in problem.districts}
    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)

    # Risk-weighted average: how well the solver served the priority districts
    assignments = result.district_assignments
    total_weight = sum(d_meta[did].demand * d_meta[did].wildfire_risk for did in assignments)
    risk_weighted_avg = (
        sum(
            d_meta[did].demand * d_meta[did].wildfire_risk * c[(did, sid)]
            for did, sid in assignments.items()
        ) / total_weight
        if total_weight else 0.0
    )

    logger.info("=" * 70)
    logger.info(f"Status:                   {result.status}")
    logger.info(f"Open stations:            {len(result.open_stations)} / {len(problem.stations)}")
    logger.info(f"Avg response time:        {result.avg_response_time_min:.1f} min  (simple avg, all districts)")
    logger.info(f"Risk-weighted avg:        {risk_weighted_avg:.1f} min  (weighted by demand × risk)")
    logger.info(f"Operational cost:         {result.total_operational_cost:,.0f} EUR")
    logger.info("-" * 70)

    for sid in sorted(result.open_stations):
        trucks = result.firetruck_allocations.get(sid, 0)
        covered_dids = [did for did, asid in assignments.items() if asid == sid]
        avg_rt = (
            sum(c[(did, sid)] for did in covered_dids) / len(covered_dids)
            if covered_dids else 0.0
        )
        logger.info(f"  {station_map.get(sid, sid)}")
        logger.info(f"    avg response   : {avg_rt:.1f} min  |  firetrucks: {trucks}")
        for did in sorted(covered_dids, key=lambda d: -d_meta[d].wildfire_risk):
            d = d_meta[did]
            rt = c[(did, sid)]
            logger.info(f"      {d.name:<50s}  risk={d.wildfire_risk:.1f}  area={d.area_km2:6.1f}km²  {rt:.1f}min")


def main() -> None:
    region = FireRegion(
        id=REGION_ID,
        name=REGION_NAME,
        total_firetrucks=REGION_TOTAL_FIRETRUCKS,
    )

    districts = load_districts(FILE_NAME_ASTIKA)
    stations = load_stations()

    if not districts:
        logger.error("No districts loaded — check municipalities.json coverage.")
        return
    if not stations:
        logger.error("No fire stations loaded — check fire_stations.json.")
        return

    problem = FireProtectionProblem(region=region, stations=stations, districts=districts)
    logger.info(
        f"Problem built — {len(stations)} candidate stations, "
        f"{len(districts)} districts, "
        f"total demand = {problem.total_demand:.2f}, "
        f"region fleet = {region.total_firetrucks} trucks"
    )

    result = solve(problem)

    if result.status != "Optimal":
        logger.error(
            f"No feasible plan available (solver status: '{result.status}'). "
            "Review RISK_COVERAGE_MAX_TIMES constraints or expand station infrastructure."
        )
        return

    _report(result, problem)


if __name__ == "__main__":
    main()
