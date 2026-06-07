"""Runs the CBC solver on the built MILP and extracts a structured result."""

import pulp

from config.milp_config import AVERAGE_SPEED_KMH, SOLVER_MIP_GAP, SOLVER_TIME_LIMIT_SECONDS
from domain.problem import FireProtectionProblem
from utils.logger import get_logger

from .model import build_model
from .result import OptimizationResult

logger = get_logger(__name__)

# PuLP status codes
_OPTIMAL = 1
_INFEASIBLE = -1


def _safe_value(var: pulp.LpVariable) -> float:
    v = pulp.value(var)
    return v if v is not None else 0.0


def _infeasible_result(status: str) -> OptimizationResult:
    """Return a sentinel result and emit the mandatory critical warning."""
    logger.critical(
        "CRITICAL: Current infrastructure capacity is mathematically insufficient to safely "
        "cover Attica's peripheral risk. "
        "Recommendation: Expand candidate station capacities or increase budget."
    )
    return OptimizationResult(
        status=status,
        objective_value=float("inf"),
        open_stations=set(),
        district_assignments={},
        firetruck_allocations={},
        avg_response_time_min=float("inf"),
        total_operational_cost=0.0,
    )


def solve(problem: FireProtectionProblem) -> OptimizationResult:
    """Solve the fire-protection MILP and return a populated OptimizationResult.

    If the model is Infeasible (e.g., a high-risk district cannot be reached within
    its hard time bound by any candidate station), a sentinel result is returned
    and a CRITICAL warning is logged — no exception is raised.
    """
    mdl, y, z, v = build_model(problem)

    solver = pulp.PULP_CBC_CMD(
        timeLimit=SOLVER_TIME_LIMIT_SECONDS,
        gapRel=SOLVER_MIP_GAP,
        msg=1,
    )
    mdl.solve(solver)

    status = pulp.LpStatus[mdl.status]
    logger.info(f"Solver finished — status: {status}")

    # --- Non-optimal outcomes ---
    if mdl.status == _INFEASIBLE:
        return _infeasible_result(status)

    if mdl.status != _OPTIMAL:
        # Time-limit hit without a feasible incumbent, or numerically undefined
        logger.error(
            f"Solver did not reach optimality (status: {status}). "
            "Results may be absent or partial."
        )
        if pulp.value(mdl.objective) is None:
            return _infeasible_result(status)

    obj = pulp.value(mdl.objective) or 0.0
    logger.info(f"Objective value: {obj:.2f}")

    open_stations = {sid for sid, var in y.items() if _safe_value(var) > 0.5}

    assignments = {
        did: sid
        for (did, sid), var in z.items()
        if _safe_value(var) > 0.5
    }

    allocations = {sid: int(round(_safe_value(var))) for sid, var in v.items()}

    c = problem.response_time_matrix(AVERAGE_SPEED_KMH)
    avg_rt_min = (
        sum(c[(did, sid)] for did, sid in assignments.items()) / len(assignments)
        if assignments else 0.0
    )
    total_ops = sum(s.cost for s in problem.stations if s.id in open_stations)

    return OptimizationResult(
        status=status,
        objective_value=obj,
        open_stations=open_stations,
        district_assignments=assignments,
        firetruck_allocations=allocations,
        avg_response_time_min=avg_rt_min,
        total_operational_cost=total_ops,
    )
