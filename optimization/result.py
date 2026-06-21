"""Holds the structured output of a solved MILP optimization run.

Multi-region formulation: ``firetruck_allocations`` is keyed by
``(region_id, station_id)`` so the full ΔΙΠΥ → station deployment matrix is
preserved and can be round-tripped through JSON without information loss.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.problem import FireProtectionProblem


@dataclass
class OptimizationResult:
    """Structured output of a solved MILP run.

    All attributes are solver-agnostic plain Python types so the object can
    be serialised, logged, and passed to the visualisation pipeline without
    importing PuLP or any other solver library.

    Parameters
    ----------
    status : str
        PuLP solver status string (e.g. ``"Optimal"``, ``"Infeasible"``).
    objective_value : float
        ``Σ w_k·c_{kj}·z_{kj}`` — the minimised WUI-priority weighted total
        response time.
    open_stations : set[str]
        Station IDs where ``y_j = 1`` in the optimal solution.
    district_assignments : dict[str, str]
        ``{district_id: station_id}`` — which station serves each district
        (``z_{kj} = 1``).
    firetruck_allocations : dict[tuple[str, str], int]
        ``{(region_id, station_id): truck_count}`` — integer ``v_{ij}`` values
        for all ``(i, j)`` pairs.
    avg_response_time_min : float
        Simple arithmetic mean of ``c_{kj}`` across all assigned district–
        station pairs.
    total_operational_cost : float
        ``Σ f_j`` for open stations (EUR / year).

    Attributes
    ----------
    status : str
    objective_value : float
    open_stations : set[str]
    district_assignments : dict[str, str]
    firetruck_allocations : dict[tuple[str, str], int]
    avg_response_time_min : float
    total_operational_cost : float
    """

    status: str
    objective_value: float
    open_stations: set[str]
    district_assignments: dict[str, str]
    firetruck_allocations: dict[tuple[str, str], int]
    avg_response_time_min: float
    total_operational_cost: float

    # -- Convenience accessors -----------------------------------------------

    @property
    def station_total_trucks(self) -> dict[str, int]:
        """Aggregate firetrucks per station across all regions.

        Returns
        -------
        dict[str, int]
            ``{station_id: total_trucks}`` — the sum of ``v_{ij}`` over all
            regions ``i`` for each station ``j``.  Useful for callers that
            only need the total count without the per-region breakdown.
        """
        totals: dict[str, int] = {}
        for (_, sid), count in self.firetruck_allocations.items():
            totals[sid] = totals.get(sid, 0) + count
        return totals

    @property
    def region_total_deployed(self) -> dict[str, int]:
        """Aggregate firetrucks deployed per region across all stations.

        Returns
        -------
        dict[str, int]
            ``{region_id: total_deployed}`` — the sum of ``v_{ij}`` over all
            stations ``j`` for each region ``i``.
        """
        totals: dict[str, int] = {}
        for (rid, _), count in self.firetruck_allocations.items():
            totals[rid] = totals.get(rid, 0) + count
        return totals

    # -- JSON serialization --------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to a compact JSON-serialisable dictionary.

        The compact format omits station and district metadata (names,
        coordinates).  Use :meth:`to_full_dict` when the visualisation
        pipeline needs to reconstruct maps from the JSON alone.

        Returns
        -------
        dict
            JSON-safe dictionary with the following top-level keys:
            ``status``, ``objective_value``, ``avg_response_time_min``,
            ``total_operational_cost``, ``open_stations``,
            ``district_assignments``, ``region_allocations``,
            ``station_totals``, ``stations_detail``.
        """
        region_allocs: dict[str, dict[str, int]] = {}
        for (rid, sid), count in self.firetruck_allocations.items():
            if count > 0:
                region_allocs.setdefault(rid, {})[sid] = count

        station_region_breakdown: dict[str, dict[str, int]] = {}
        for (rid, sid), count in self.firetruck_allocations.items():
            if count > 0:
                station_region_breakdown.setdefault(sid, {})[rid] = count

        station_districts: dict[str, list[str]] = {}
        for did, sid in self.district_assignments.items():
            station_districts.setdefault(sid, []).append(did)

        all_station_ids: set[str] = (
            self.open_stations
            | set(self.district_assignments.values())
            | {sid for (_, sid) in self.firetruck_allocations}
        )

        stations_detail: dict[str, dict] = {
            sid: {
                "is_active": sid in self.open_stations,
                "total_trucks": self.station_total_trucks.get(sid, 0),
                "region_breakdown": dict(
                    sorted(station_region_breakdown.get(sid, {}).items())
                ),
                "assigned_districts": sorted(station_districts.get(sid, [])),
            }
            for sid in sorted(all_station_ids)
        }

        return {
            "status": self.status,
            "objective_value": round(self.objective_value, 4),
            "avg_response_time_min": round(self.avg_response_time_min, 2),
            "total_operational_cost": round(self.total_operational_cost, 2),
            "open_stations": sorted(self.open_stations),
            "district_assignments": dict(sorted(self.district_assignments.items())),
            "region_allocations": {
                rid: dict(sorted(stations.items()))
                for rid, stations in sorted(region_allocs.items())
            },
            "station_totals": dict(sorted(self.station_total_trucks.items())),
            "stations_detail": stations_detail,
        }

    def to_full_dict(
        self,
        problem: "FireProtectionProblem",
        response_times: dict[tuple[str, str], float],
    ) -> dict:
        """Build a self-contained dictionary embedding all station and district metadata.

        The resulting document is fully self-contained: the
        ``src/visualization`` pipeline can reconstruct a
        ``MilpResultVisualizer`` from it via
        ``MilpResultVisualizer.from_json()`` without reloading any original
        data sources.

        Parameters
        ----------
        problem : FireProtectionProblem
            The same problem instance passed to the solver.  Provides station
            and district names, coordinates, capacities, and costs.
        response_times : dict[tuple[str, str], float]
            Pre-computed ``{(district_id, station_id): minutes}`` matrix from
            :meth:`~domain.problem.FireProtectionProblem.response_time_matrix`.

        Returns
        -------
        dict
            The output of :meth:`to_dict` augmented with two additional
            top-level keys: ``"stations"`` (list of station dicts) and
            ``"districts"`` (list of district dicts), each containing full
            geographic and operational metadata.
        """
        base = self.to_dict()

        station_region_breakdown: dict[str, dict[str, int]] = {}
        for (rid, sid), count in self.firetruck_allocations.items():
            if count > 0:
                station_region_breakdown.setdefault(sid, {})[rid] = count

        station_districts: dict[str, list[str]] = {}
        for did, sid in self.district_assignments.items():
            station_districts.setdefault(sid, []).append(did)

        stations_list = [
            {
                "id": s.id,
                "name": s.name,
                "lat": s.lat,
                "lon": s.lon,
                "capacity": s.capacity,
                "annual_cost": s.cost,
                "is_active": s.id in self.open_stations,
                "total_trucks": self.station_total_trucks.get(s.id, 0),
                "region_allocations": dict(
                    sorted(station_region_breakdown.get(s.id, {}).items())
                ),
                "assigned_districts": sorted(station_districts.get(s.id, [])),
            }
            for s in problem.stations
        ]

        districts_list = [
            {
                "id": d.id,
                "name": d.name,
                "lat": d.lat,
                "lon": d.lon,
                "demand": d.demand,
                "area_km2": d.area_km2,
                "wildfire_risk": d.wildfire_risk,
                "assigned_station_id": self.district_assignments.get(d.id, ""),
                "response_time_min": round(
                    response_times.get(
                        (d.id, self.district_assignments.get(d.id, "")), 0.0
                    ),
                    2,
                ),
            }
            for d in problem.districts
        ]

        return {**base, "stations": stations_list, "districts": districts_list}

    def to_full_json(
        self,
        path: Path | str,
        problem: "FireProtectionProblem",
        response_times: dict[tuple[str, str], float],
        *,
        indent: int = 2,
    ) -> None:
        """Serialise to a self-contained JSON file for the visualisation pipeline.

        Equivalent to calling :meth:`to_full_dict` and writing the result to
        *path*.  The parent directory is created automatically if it does not
        exist.

        Parameters
        ----------
        path : Path or str
            Destination file path.
        problem : FireProtectionProblem
            The same problem instance passed to the solver.
        response_times : dict[tuple[str, str], float]
            Pre-computed ``{(district_id, station_id): minutes}`` matrix.
        indent : int, optional
            JSON indentation level (default ``2``).

        Raises
        ------
        OSError
            If the file cannot be written (e.g. permission error).
        """
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(
                self.to_full_dict(problem, response_times),
                fh,
                indent=indent,
                ensure_ascii=False,
            )

    @classmethod
    def from_json(cls, path: Path | str) -> "OptimizationResult":
        """Deserialise a result previously written by :meth:`to_json`.

        Only the fields that appear in the compact JSON format are
        reconstructed.  Station and district metadata (names, coordinates) is
        not stored in the compact format and must be reloaded from the original
        data sources when needed.

        Parameters
        ----------
        path : Path or str
            Path to the JSON file produced by :meth:`to_json` or
            :meth:`to_full_json`.

        Returns
        -------
        OptimizationResult
            Populated result object.

        Raises
        ------
        KeyError
            If a required top-level key (``status``, ``objective_value``,
            ``open_stations``, ``district_assignments``,
            ``avg_response_time_min``, ``total_operational_cost``) is absent
            from the file.
        json.JSONDecodeError
            If the file is not valid JSON.
        """
        with open(Path(path), encoding="utf-8") as fh:
            data: dict = json.load(fh)

        allocations: dict[tuple[str, str], int] = {}
        for rid, stations in data.get("region_allocations", {}).items():
            for sid, count in stations.items():
                allocations[(rid, sid)] = int(count)

        return cls(
            status=str(data["status"]),
            objective_value=float(data["objective_value"]),
            open_stations=set(data["open_stations"]),
            district_assignments={str(k): str(v) for k, v in data["district_assignments"].items()},
            firetruck_allocations=allocations,
            avg_response_time_min=float(data["avg_response_time_min"]),
            total_operational_cost=float(data["total_operational_cost"]),
        )

    def to_json(self, path: Path | str, *, indent: int = 2) -> None:
        """Serialise the compact result to a JSON file.

        Does **not** embed station or district metadata.  For a self-contained
        file usable by the visualisation pipeline, use :meth:`to_full_json`.

        Parameters
        ----------
        path : Path or str
            Output file path.  Parent directories are created as needed.
        indent : int, optional
            JSON indentation level (default ``2``).

        Raises
        ------
        OSError
            If the file cannot be written.
        """
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=indent, ensure_ascii=False)
