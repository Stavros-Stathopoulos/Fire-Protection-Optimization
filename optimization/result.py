"""Holds the structured output of a solved MILP optimization run.

Multi-region formulation: ``firetruck_allocations`` is keyed by
``(region_id, station_id)`` so the full ΔΙΠΥ → station deployment
matrix is preserved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Set, Tuple

if TYPE_CHECKING:
    from domain.problem import FireProtectionProblem


@dataclass
class OptimizationResult:
    """Structured output of a solved MILP run.

    Attributes
    ----------
    status:
        PuLP solver status string (``"Optimal"``, ``"Infeasible"``, …).
    objective_value:
        Σ wk·ckj·zkj — demand-weighted response time.
    open_stations:
        Station ids where yj = 1.
    district_assignments:
        ``{district_id: station_id}`` — which station serves which district (zkj = 1).
    firetruck_allocations:
        ``{(region_id, station_id): truck_count}`` — how many trucks each ΔΙΠΥ
        deploys to each station (vij values).
    avg_response_time_min:
        Simple average ckj across all assigned districts.
    total_operational_cost:
        Σ fj for open stations (EUR).
    """

    status: str
    objective_value: float
    open_stations: Set[str]
    district_assignments: Dict[str, str]
    firetruck_allocations: Dict[Tuple[str, str], int]
    avg_response_time_min: float
    total_operational_cost: float

    # -- Convenience accessors -----------------------------------------------

    @property
    def station_total_trucks(self) -> Dict[str, int]:
        """Aggregate trucks per station across all regions.

        Returns ``{station_id: total_trucks}`` — useful for callers that
        don't need the per-region breakdown (e.g. the visualizer).
        """
        totals: Dict[str, int] = {}
        for (_, sid), count in self.firetruck_allocations.items():
            totals[sid] = totals.get(sid, 0) + count
        return totals

    @property
    def region_total_deployed(self) -> Dict[str, int]:
        """Aggregate trucks deployed per region across all stations.

        Returns ``{region_id: total_deployed}``.
        """
        totals: Dict[str, int] = {}
        for (rid, _), count in self.firetruck_allocations.items():
            totals[rid] = totals.get(rid, 0) + count
        return totals

    # -- JSON serialization --------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary.

        Structure:
        ```json
        {
          "status": "Optimal",
          "objective_value": 42.0,
          "avg_response_time_min": 8.5,
          "total_operational_cost": 6400000,
          "open_stations": ["ps_athens_1", ...],
          "district_assignments": {"dist_0": "ps_athens_1", ...},
          "region_allocations": {
            "dipy_athens": {"ps_athens_1": 5, ...},
            "dipy_piraeus": {"ps_piraeus": 3, ...}
          },
          "station_totals": {"ps_athens_1": 8, ...},
          "stations_detail": {
            "ps_athens_1": {
              "is_active": true,
              "total_trucks": 8,
              "region_breakdown": {"dipy_athens": 5, "dipy_piraeus": 3},
              "assigned_districts": ["dist_0", "dist_1"]
            }
          }
        }
        ```
        """
        # region → station → trucks (non-zero only)
        region_allocs: dict[str, dict[str, int]] = {}
        for (rid, sid), count in self.firetruck_allocations.items():
            if count > 0:
                region_allocs.setdefault(rid, {})[sid] = count

        # station → {region_id: count} (non-zero only)
        station_region_breakdown: dict[str, dict[str, int]] = {}
        for (rid, sid), count in self.firetruck_allocations.items():
            if count > 0:
                station_region_breakdown.setdefault(sid, {})[rid] = count

        # station → [district_ids]  (invert district_assignments)
        station_districts: dict[str, list[str]] = {}
        for did, sid in self.district_assignments.items():
            station_districts.setdefault(sid, []).append(did)

        # Collect every station that appears anywhere in the solution
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
        response_times: "dict[tuple[str, str], float]",
    ) -> dict:
        """Like :meth:`to_dict` but embeds all station and district metadata.

        The resulting document is fully self-contained: the ``src/visualization``
        pipeline can reconstruct a ``MilpResultVisualizer`` from it via
        ``MilpResultVisualizer.from_json()`` without reloading any data source.

        Parameters
        ----------
        problem:
            The same ``FireProtectionProblem`` that was passed to the solver.
            Provides station / district names, coordinates, capacities, and costs.
        response_times:
            Pre-computed ``{(district_id, station_id): minutes}`` matrix from
            ``FireProtectionProblem.response_time_matrix()``.
        """
        base = self.to_dict()

        # station → {region_id: count}
        station_region_breakdown: dict[str, dict[str, int]] = {}
        for (rid, sid), count in self.firetruck_allocations.items():
            if count > 0:
                station_region_breakdown.setdefault(sid, {})[rid] = count

        # station → [district_ids]
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
        path: "Path | str",
        problem: "FireProtectionProblem",
        response_times: "dict[tuple[str, str], float]",
        *,
        indent: int = 2,
    ) -> None:
        """Serialize to a self-contained JSON for the visualization pipeline.

        Equivalent to calling ``to_full_dict()`` then writing to *path*.
        The parent directory is created automatically if it does not exist.
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
    def from_json(cls, path: "Path | str") -> "OptimizationResult":
        """Deserialize a result previously written by :meth:`to_json`.

        Only the fields that appear in the JSON are reconstructed.
        Station / district metadata (names, coordinates) is not stored in the
        JSON and must be reloaded from the original data sources when needed.

        Parameters
        ----------
        path:
            Path to the JSON file produced by :meth:`to_json`.

        Raises
        ------
        KeyError
            If a required top-level key is absent from the file.
        """
        with open(Path(path), encoding="utf-8") as fh:
            data: dict = json.load(fh)

        # Reconstruct firetruck_allocations from the nested region_allocations block.
        allocations: Dict[Tuple[str, str], int] = {}
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

    def to_json(self, path: "Path | str", *, indent: int = 2) -> None:
        """Serialize the result to a JSON file.

        Parameters
        ----------
        path:
            Output file path.
        indent:
            JSON indentation level.
        """
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=indent, ensure_ascii=False)
