"""Runs the CBC solver on the built MILP and extracts a structured result.

Multi-region formulation: ``v`` variables are keyed ``(region_id, station_id)``
and the solver extracts the full per-region firetruck allocation matrix into
``OptimizationResult.firetruck_allocations``.
"""

import pulp

from config.milp_config import AVERAGE_SPEED_KMH, SOLVER_MIP_GAP, SOLVER_TIME_LIMIT_SECONDS
from domain.problem import FireProtectionProblem
from utils.logger import get_logger

from .model import build_model
from .result import OptimizationResult

logger = get_logger(__name__)

_OPTIMAL = 1
_INFEASIBLE = -1


def _safe_value(var: pulp.LpVariable) -> float:
    """Return the numeric value of *var*, defaulting to ``0.0`` if unset.

    PuLP returns ``None`` for variables that are not in the basis (e.g. when
    the solver terminates at a time limit without finding a feasible solution).
    This helper converts ``None`` to ``0.0`` so downstream code never has to
    handle ``None`` arithmetic.

    Parameters
    ----------
    var : pulp.LpVariable
        A solved (or partially solved) PuLP decision variable.

    Returns
    -------
    float
        ``pulp.value(var)`` if defined, else ``0.0``.
    """
    v = pulp.value(var)
    return v if v is not None else 0.0


def _infeasible_result(status: str) -> OptimizationResult:
    """Build and return a sentinel ``OptimizationResult`` for infeasible runs.

    Logs a CRITICAL-level warning before returning so operators are
    immediately alerted that the current station configuration cannot safely
    cover all districts within their risk-based time bounds.

    Parameters
    ----------
    status : str
        PuLP status string (e.g. ``"Infeasible"`` or ``"Not Solved"``).

    Returns
    -------
    OptimizationResult
        A sentinel result with ``status`` set to the solver status and all
        numeric fields set to sentinel values (``float("inf")`` for times and
        costs, empty collections for assignments).
    """
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


def solve(
    problem: FireProtectionProblem,
    *,
    max_budget: float | None = None,
) -> OptimizationResult:
    """Solve the fire-protection MILP and return a populated ``OptimizationResult``.

    Builds the PuLP model via :func:`~optimization.model.build_model`, invokes
    the CBC solver, and extracts all decision variable values into a typed
    result object.

    If the model is **Infeasible** (e.g. a high-risk district cannot be reached
    within its hard time bound by any candidate station), a sentinel result is
    returned and a CRITICAL warning is logged — no exception is raised.

    Parameters
    ----------
    problem : FireProtectionProblem
        Multi-region problem definition carrying regions, stations, and
        districts.
    max_budget : float or None, optional
        If provided, overrides ``config.milp_config.MAX_BUDGET``.  Pass
        ``None`` (default) to use the config value.

    Returns
    -------
    OptimizationResult
        Fully populated result if the solver reaches **Optimal** status.
        A sentinel result (with ``float("inf")`` placeholders) for all other
        solver outcomes.
    """
    mdl, y, z, v = build_model(problem, max_budget=max_budget)

    solver = pulp.PULP_CBC_CMD(
        timeLimit=SOLVER_TIME_LIMIT_SECONDS,
        gapRel=SOLVER_MIP_GAP,
        msg=1,
    )
    mdl.solve(solver)

    status = pulp.LpStatus[mdl.status]
    logger.info(f"Solver finished — status: {status}")

    if mdl.status == _INFEASIBLE:
        return _infeasible_result(status)

    if mdl.status != _OPTIMAL:
        logger.error(
            f"Solver did not reach optimality (status: {status}). "
            "Results may be absent or partial."
        )
        if pulp.value(mdl.objective) is None:
            return _infeasible_result(status)

    obj = pulp.value(mdl.objective) or 0.0
    logger.info(f"Objective value: {obj:.2f}")

    open_stations = {sid for sid, var in y.items() if _safe_value(var) > 0.5}

    assignments: dict[str, str] = {
        did: sid
        for (did, sid), var in z.items()
        if _safe_value(var) > 0.5
    }

    allocations: dict[tuple[str, str], int] = {
        (rid, sid): int(round(_safe_value(var)))
        for (rid, sid), var in v.items()
    }

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
