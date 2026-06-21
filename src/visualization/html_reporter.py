"""Production-grade HTML Executive Dashboard for MILP optimization results.

Generates a fully-standalone, responsive, tabbed HTML dashboard.
All HTML/CSS/JS is isolated in this module; main.py only calls generate_report().

Tab layout
----------
  Tab 1 — Γενικά Στατιστικά : Global KPIs + ΔΙΠΥ regional deployment
  Tab 2 — Σταθμοί           : All candidate stations (open highlighted, inactive compact)
  Tab 3 — Χρόνοι Ανταπόκρισης : Full district response-time datatable
"""

from __future__ import annotations

import html as _html
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities import FireStation, IncidentDistrict
    from domain.problem import FireProtectionProblem
    from optimization.result import OptimizationResult


# ---------------------------------------------------------------------------
# Module-level formatting helpers
# ---------------------------------------------------------------------------

def _e(value: object) -> str:
    """HTML-escape *value* cast to ``str``.

    Parameters
    ----------
    value : object
        Any Python object.

    Returns
    -------
    str
        HTML-escaped string, safe for insertion into HTML attribute values
        and text content.  Handles Greek and all Unicode characters.
    """
    return _html.escape(str(value))


def _fmt_eur(value: float) -> str:
    """Format a float as a human-readable EUR string.

    Parameters
    ----------
    value : float
        Monetary value in EUR.

    Returns
    -------
    str
        String of the form ``"1,200,000 EUR"``.
    """
    return f"{value:,.0f} EUR"


def _rt_classes(minutes: float) -> tuple[str, str]:
    """Return a Tailwind CSS colour pair for a response-time value.

    Parameters
    ----------
    minutes : float
        Response time in minutes.

    Returns
    -------
    tuple[str, str]
        ``(bg_class, text_class)`` Tailwind CSS classes encoding urgency:
        emerald (≤ 10) → green (≤ 15) → amber (≤ 20) → orange (≤ 25) →
        rose (> 25).
    """
    if minutes <= 10.0:
        return "bg-emerald-900", "text-emerald-300"
    if minutes <= 15.0:
        return "bg-green-900", "text-green-300"
    if minutes <= 20.0:
        return "bg-amber-900", "text-amber-300"
    if minutes <= 25.0:
        return "bg-orange-900", "text-orange-300"
    return "bg-rose-900", "text-rose-300"


def _risk_classes(risk: float) -> tuple[str, str]:
    """Return a Tailwind CSS colour pair for a wildfire-risk value.

    Parameters
    ----------
    risk : float
        Wildfire risk factor (``1.0`` – ``5.0``).

    Returns
    -------
    tuple[str, str]
        ``(bg_class, text_class)`` Tailwind CSS classes: emerald (≤ 1.5)
        → amber (≤ 2.5) → orange (≤ 3.5) → rose (> 3.5).
    """
    if risk <= 1.5:
        return "bg-emerald-900", "text-emerald-300"
    if risk <= 2.5:
        return "bg-amber-900", "text-amber-300"
    if risk <= 3.5:
        return "bg-orange-900", "text-orange-300"
    return "bg-rose-900", "text-rose-300"


def _badge(label: str, bg: str, text: str) -> str:
    """Render a small Tailwind pill badge.

    Parameters
    ----------
    label : str
        Badge text content.
    bg : str
        Tailwind background colour class (e.g. ``"bg-emerald-900"``).
    text : str
        Tailwind text colour class (e.g. ``"text-emerald-300"``).

    Returns
    -------
    str
        HTML ``<span>`` string for a coloured pill badge.
    """
    return (
        f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs '
        f'font-semibold {bg} {text}">{label}</span>'
    )


def _rt_badge(minutes: float) -> str:
    """Render a response-time pill badge with automatic colour coding.

    Parameters
    ----------
    minutes : float
        Response time in minutes.

    Returns
    -------
    str
        HTML ``<span>`` badge string.
    """
    bg, txt = _rt_classes(minutes)
    return _badge(f"{minutes:.1f} min", bg, txt)


def _risk_badge(risk: float) -> str:
    """Render a wildfire-risk pill badge with automatic colour coding.

    Parameters
    ----------
    risk : float
        Wildfire risk factor (``1.0`` – ``5.0``).

    Returns
    -------
    str
        HTML ``<span>`` badge string.
    """
    bg, txt = _risk_classes(risk)
    return _badge(f"{risk:.1f}", bg, txt)


# ---------------------------------------------------------------------------
# Reporter class
# ---------------------------------------------------------------------------

class MilpHtmlReporter:
    """Renders a standalone responsive 3-tab HTML dashboard from MILP results.

    Parameters
    ----------
    result:
        Solved MILP result carrying all assignment and allocation data.
    problem:
        The original problem definition (stations, districts, regions).
    response_times:
        Pre-computed ``{(district_id, station_id): minutes}`` matrix.
    """

    def __init__(
        self,
        result: OptimizationResult,
        problem: FireProtectionProblem,
        response_times: dict[tuple[str, str], float],
    ) -> None:
        self._result = result
        self._problem = problem
        self._rt = response_times
        self._station_map: dict[str, FireStation] = {
            s.id: s for s in problem.stations
        }
        self._district_map: dict[str, IncidentDistrict] = {
            d.id: d for d in problem.districts
        }

    # ------------------------------------------------------------------ public

    def generate_report(self, output_path: Path) -> None:
        """Render and write the HTML dashboard to *output_path*.

        Parameters
        ----------
        output_path : Path
            Destination file path.  Parent directories are created
            automatically.

        Returns
        -------
        None
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._render_html(), encoding="utf-8")

    # ----------------------------------------------------------------- helpers

    def _risk_weighted_avg(self) -> float:
        """Compute the demand-and-risk weighted average response time.

        Returns
        -------
        float
            Weighted average response time (minutes), or ``0.0`` if there
            are no assignments.
        """
        assignments = self._result.district_assignments
        d_meta = self._district_map
        total_weight = sum(
            d_meta[did].demand * d_meta[did].wildfire_risk
            for did in assignments
            if did in d_meta
        )
        if not total_weight:
            return 0.0
        return sum(
            d_meta[did].demand * d_meta[did].wildfire_risk * self._rt.get((did, sid), 0.0)
            for did, sid in assignments.items()
            if did in d_meta
        ) / total_weight

    def _station_avg_rt(self, sid: str) -> float:
        """Compute the average response time for all districts assigned to *sid*.

        Parameters
        ----------
        sid : str
            Station identifier.

        Returns
        -------
        float
            Arithmetic mean response time in minutes, or ``0.0`` if no
            districts are assigned to the station.
        """
        covered = [
            did for did, asid in self._result.district_assignments.items()
            if asid == sid
        ]
        return (
            sum(self._rt.get((did, sid), 0.0) for did in covered) / len(covered)
            if covered else 0.0
        )

    # ----------------------------------------------------------- static assets
    # These methods return plain (non-f) strings so CSS/JS braces need no escaping.

    @staticmethod
    def _styles() -> str:
        return """<style>
  /* Suppress native <details> disclosure triangle in all browsers */
  details > summary { list-style: none; }
  details > summary::-webkit-details-marker { display: none; }

  /* Tab button states — defined in <style> so JS class-swaps work reliably */
  .tab-btn {
    padding: 0.75rem 1.5rem;
    font-size: 0.8125rem;
    font-weight: 600;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    cursor: pointer;
    white-space: nowrap;
    transition: color 0.15s, border-color 0.15s;
  }
  .tab-btn-active  { color: rgb(56 189 248);  border-bottom-color: rgb(56 189 248); }
  .tab-btn-inactive { color: rgb(148 163 184); }
  .tab-btn-inactive:hover { color: rgb(226 232 240); border-bottom-color: rgb(71 85 105); }

  /* Shared section heading */
  .section-title {
    display: flex;
    align-items: center;
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgb(148 163 184);
    margin-bottom: 1rem;
  }
</style>"""

    @staticmethod
    def _tab_script() -> str:
        """Minimal vanilla JS for tab switching — no external dependencies."""
        return """<script>
function showTab(panelId, btn) {
  document.querySelectorAll('.tab-panel').forEach(function(p) {
    p.classList.add('hidden');
  });
  document.querySelectorAll('.tab-btn').forEach(function(b) {
    b.classList.remove('tab-btn-active');
    b.classList.add('tab-btn-inactive');
  });
  document.getElementById(panelId).classList.remove('hidden');
  btn.classList.remove('tab-btn-inactive');
  btn.classList.add('tab-btn-active');
}
</script>"""

    @staticmethod
    def _sort_script() -> str:
        """Locale-aware column sort for the district datatable."""
        return """<script>
(function() {
  var tbody = document.getElementById('districts-tbody');
  if (!tbody) return;
  var state = { col: -1, asc: true };

  document.querySelectorAll('th.sortable').forEach(function(th) {
    th.addEventListener('click', function() {
      var col = parseInt(th.dataset.col, 10);
      state.asc = (state.col === col) ? !state.asc : true;
      state.col = col;

      document.querySelectorAll('th.sortable .sort-icon').forEach(function(ic) {
        ic.textContent = '↕';
        ic.style.color = '';
      });
      var icon = th.querySelector('.sort-icon');
      icon.textContent = state.asc ? '↑' : '↓';
      icon.style.color = 'rgb(56 189 248)';

      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b) {
        var ta = ((a.cells[col] || {}).textContent || '').trim();
        var tb = ((b.cells[col] || {}).textContent || '').trim();
        var na = parseFloat(ta.replace(/[^0-9.\-]/g, ''));
        var nb = parseFloat(tb.replace(/[^0-9.\-]/g, ''));
        var cmp = (!isNaN(na) && !isNaN(nb)) ? na - nb : ta.localeCompare(tb, 'el');
        return state.asc ? cmp : -cmp;
      });
      rows.forEach(function(r) { tbody.appendChild(r); });
    });
  });
}());
</script>"""

    # -------------------------------------------------------------- header

    def _render_header(self) -> str:
        status = _e(self._result.status)
        status_cls = (
            "bg-emerald-800 text-emerald-200 border border-emerald-700"
            if self._result.status == "Optimal"
            else "bg-rose-800 text-rose-200 border border-rose-700"
        )
        ts = datetime.now(tz=timezone.utc).strftime("%d %b %Y · %H:%M UTC")
        return (
            f'<header class="bg-slate-900 border-b border-slate-700 px-6 py-4 '
            f'sticky top-0 z-50 shadow-xl">'
            f'<div class="max-w-screen-xl mx-auto flex flex-wrap items-center '
            f'justify-between gap-3">'
            f'<div class="flex items-center gap-3">'
            f'<div class="w-10 h-10 bg-rose-700 rounded-lg flex items-center '
            f'justify-center shadow-lg text-xl select-none">&#128293;</div>'
            f'<div>'
            f'<h1 class="text-base font-bold tracking-tight leading-snug">'
            f'Attica Fire Protection &#8212; MILP Executive Report</h1>'
            f'<p class="text-xs text-slate-400 leading-none mt-0.5">'
            f'Multi-region optimisation &middot; &#913;&#964;&#964;&#953;&#954;&#942; '
            f'&middot; 4 &#916;&#921;&#928;&#933; directorates</p>'
            f'</div></div>'
            f'<div class="flex items-center gap-3">'
            f'<span class="px-2.5 py-1 rounded-full text-xs font-semibold {status_cls}">'
            f'{status}</span>'
            f'<span class="text-xs text-slate-500">{_e(ts)}</span>'
            f'</div></div></header>'
        )

    # --------------------------------------------------------------- tab nav

    def _render_tab_nav(self) -> str:
        tabs: list[tuple[str, str, bool]] = [
            ("tab-general",  "&#128202; &#915;&#949;&#957;&#953;&#954;&#940; &#931;&#964;&#945;&#964;&#953;&#963;&#964;&#953;&#954;&#940;", True),
            ("tab-stations", "&#127968; &#931;&#964;&#945;&#952;&#956;&#959;&#943;",                                                         False),
            ("tab-response", "&#9201; &#935;&#961;&#972;&#957;&#959;&#953; &#913;&#957;&#964;&#945;&#960;&#972;&#954;&#961;&#953;&#963;&#951;&#962;", False),
        ]
        buttons = "".join(
            f'<button class="tab-btn {"tab-btn-active" if active else "tab-btn-inactive"}" '
            f'onclick="showTab(\'{panel_id}\', this)">{label}</button>'
            for panel_id, label, active in tabs
        )
        return (
            f'<div class="max-w-screen-xl mx-auto px-4 sm:px-6 pt-2">'
            f'<div class="flex border-b border-slate-700 overflow-x-auto">'
            f'{buttons}</div></div>'
        )

    # ----------------------------------------- Tab 1: General Statistics

    def _render_kpi_cards(self) -> str:
        res = self._result
        n_open  = len(res.open_stations)
        n_total = len(self._problem.stations)
        activation_pct = n_open / n_total * 100 if n_total else 0.0
        rw_avg  = self._risk_weighted_avg()
        _, rw_txt  = _rt_classes(rw_avg)
        _, avg_txt = _rt_classes(res.avg_response_time_min)
        cost_txt = "text-amber-300" if res.total_operational_cost > 5_000_000 else "text-emerald-300"

        def _card(icon: str, label: str, value: str, sub: str, accent: str) -> str:
            sub_row = (
                f'<p class="text-xs text-slate-500 mt-1 leading-tight">{_e(sub)}</p>'
                if sub else ""
            )
            return (
                f'<div class="bg-slate-800 rounded-xl p-5 border border-slate-700 '
                f'shadow flex flex-col gap-1">'
                f'<div class="flex items-center gap-1.5 text-slate-400 text-xs '
                f'font-semibold uppercase tracking-widest">'
                f'<span class="select-none">{icon}</span><span>{_e(label)}</span></div>'
                f'<div class="text-2xl font-extrabold {accent} leading-tight mt-1">{value}</div>'
                f'{sub_row}</div>'
            )

        cards = "".join([
            _card("&#10003;", "Solver Status", _e(res.status), "",
                  "text-emerald-300" if res.status == "Optimal" else "text-rose-400"),
            _card("&#128176;", "Operational Cost",
                  f"{res.total_operational_cost:,.0f}", "EUR / year", cost_txt),
            _card("&#127968;", "Active Stations", f"{n_open} / {n_total}",
                  f"{activation_pct:.0f}% of candidates activated", "text-sky-300"),
            _card("&#9201;", "Avg Response Time",
                  f"{res.avg_response_time_min:.1f} min",
                  "Simple average, all districts", avg_txt),
            _card("&#9889;", "Risk-Weighted Avg",
                  f"{rw_avg:.1f} min",
                  "Weighted by demand × wildfire risk", rw_txt),
        ])
        return (
            f'<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">'
            f'{cards}</div>'
        )

    def _render_regional_grid(self) -> str:
        deployed_map = self._result.region_total_deployed
        cards: list[str] = []
        for region in self._problem.regions:
            deployed = deployed_map.get(region.id, 0)
            total    = region.total_firetrucks
            pct      = deployed / total * 100 if total else 0.0
            bar_w    = min(100, int(pct))
            if pct >= 95:
                bar_cls, pct_cls = "bg-emerald-500", "text-emerald-400"
            elif pct >= 70:
                bar_cls, pct_cls = "bg-amber-500",   "text-amber-400"
            else:
                bar_cls, pct_cls = "bg-rose-500",    "text-rose-400"
            cards.append(
                f'<div class="bg-slate-800 rounded-xl p-5 border border-slate-700 shadow">'
                f'<div class="flex items-start justify-between mb-3">'
                f'<div><p class="text-sm font-semibold text-slate-100 leading-tight">'
                f'{_e(region.name)}</p>'
                f'<p class="text-xs text-slate-500 mt-0.5 font-mono">{_e(region.id)}</p></div>'
                f'<span class="text-xl font-black {pct_cls} tabular-nums">{deployed}'
                f'<span class="text-slate-500 text-sm font-normal">/{total}</span></span></div>'
                f'<div class="w-full bg-slate-700 rounded-full h-2">'
                f'<div class="{bar_cls} h-2 rounded-full" style="width:{bar_w}%"></div></div>'
                f'<p class="mt-2 text-xs text-slate-500">{pct:.1f}% of regional fleet deployed</p>'
                f'</div>'
            )
        return (
            f'<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">'
            f'{"".join(cards)}</div>'
        )

    def _render_tab_general(self) -> str:
        return (
            f'<div class="space-y-10">'
            f'<section><h2 class="section-title">Global KPIs</h2>'
            f'{self._render_kpi_cards()}</section>'
            f'<section>'
            f'<h2 class="section-title">Regional Fleet Deployment &#8212; &#916;&#921;&#928;&#933;</h2>'
            f'{self._render_regional_grid()}</section>'
            f'</div>'
        )

    # ----------------------------------------------- Tab 2: Fire Stations

    def _render_open_station_card(self, sid: str) -> str:
        res     = self._result
        station = self._station_map.get(sid)
        if station is None:
            return ""

        trucks       = res.station_total_trucks.get(sid, 0)
        covered_dids = [
            did for did, asid in res.district_assignments.items() if asid == sid
        ]
        avg_rt = self._station_avg_rt(sid)

        # Region allocation pills (non-f string value, safe to interpolate)
        region_pills = "".join(
            f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs '
            f'bg-slate-700 text-slate-300 font-mono border border-slate-600">'
            f'{_e(rid)}={count}</span>'
            for (rid, s_id), count in sorted(res.firetruck_allocations.items())
            if s_id == sid and count > 0
        )

        # District sub-table rows, sorted by wildfire risk descending
        districts_sorted = sorted(
            (did for did in covered_dids if did in self._district_map),
            key=lambda did: self._district_map[did].wildfire_risk,
            reverse=True,
        )
        rows: list[str] = []
        for did in districts_sorted:
            d  = self._district_map[did]
            dt = self._rt.get((did, sid), 0.0)
            rows.append(
                f'<tr class="border-t border-slate-700 hover:bg-slate-700/30 transition-colors">'
                f'<td class="px-3 py-2 text-sm text-slate-200 whitespace-nowrap">{_e(d.name)}</td>'
                f'<td class="px-3 py-2 text-center">{_risk_badge(d.wildfire_risk)}</td>'
                f'<td class="px-3 py-2 text-right font-mono text-sm text-slate-300">'
                f'{d.area_km2:.1f}</td>'
                f'<td class="px-3 py-2 text-right font-mono text-sm text-slate-300">'
                f'{d.demand:.1f}</td>'
                f'<td class="px-3 py-2 text-center">{_rt_badge(dt)}</td></tr>'
            )
        tbody = "".join(rows) or (
            '<tr><td colspan="5" class="px-3 py-4 text-center text-slate-500 text-sm">'
            'No districts assigned</td></tr>'
        )

        return (
            f'<details class="bg-slate-800 rounded-xl border border-slate-700 shadow group">'
            f'<summary class="flex items-center justify-between px-5 py-4 '
            f'cursor-pointer select-none">'
            # Left: icon + name
            f'<div class="flex items-center gap-3 min-w-0">'
            f'<div class="w-8 h-8 shrink-0 bg-rose-900 rounded-lg flex items-center '
            f'justify-center text-sm select-none">&#128658;</div>'
            f'<div class="min-w-0">'
            f'<p class="text-sm font-semibold text-slate-100 leading-tight truncate">'
            f'{_e(station.name)}</p>'
            f'<p class="text-xs text-slate-500 mt-0.5 font-mono">{_e(sid)}</p>'
            f'</div></div>'
            # Right: badge + meta + chevron
            f'<div class="flex items-center gap-3 shrink-0 ml-4">'
            f'{_rt_badge(avg_rt)}'
            f'<span class="text-xs text-slate-400 font-mono hidden sm:inline">'
            f'{trucks} trucks &middot; {len(covered_dids)} districts</span>'
            f'<svg class="w-4 h-4 text-slate-500 group-open:rotate-180 transition-transform '
            f'shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            f'd="M19 9l-7 7-7-7"/></svg></div></summary>'
            # Expanded body
            f'<div class="border-t border-slate-700 px-5 pb-5">'
            f'<div class="flex flex-wrap items-center gap-2 py-3 text-xs text-slate-500">'
            f'<span>Truck allocation:</span>{region_pills}'
            f'<span class="text-slate-600">&middot;</span>'
            f'<span>Capacity: <strong class="text-slate-300">{station.capacity}</strong></span>'
            f'<span class="text-slate-600">&middot;</span>'
            f'<span>Annual cost: '
            f'<strong class="text-slate-300">{_e(_fmt_eur(station.cost))}</strong></span>'
            f'</div>'
            f'<div class="overflow-x-auto rounded-lg border border-slate-700">'
            f'<table class="w-full text-left"><thead>'
            f'<tr class="bg-slate-900 text-xs text-slate-400 uppercase tracking-wider">'
            f'<th class="px-3 py-2.5 font-medium">District</th>'
            f'<th class="px-3 py-2.5 font-medium text-center">Risk</th>'
            f'<th class="px-3 py-2.5 font-medium text-right">Area km&#178;</th>'
            f'<th class="px-3 py-2.5 font-medium text-right">Demand</th>'
            f'<th class="px-3 py-2.5 font-medium text-center">Response</th>'
            f'</tr></thead><tbody>{tbody}</tbody></table></div>'
            f'</div></details>'
        )

    def _render_inactive_mini(self, s: FireStation) -> str:
        return (
            f'<div class="bg-slate-800/40 rounded-lg p-3 border border-slate-700/50">'
            f'<p class="text-xs font-semibold text-slate-400 leading-tight truncate">'
            f'{_e(s.name)}</p>'
            f'<p class="text-xs text-slate-600 font-mono mt-0.5">{_e(s.id)}</p>'
            f'<p class="text-xs text-slate-600 mt-1">Cap: {s.capacity} &middot; '
            f'{_e(_fmt_eur(s.cost))}</p></div>'
        )

    def _render_tab_stations(self) -> str:
        res = self._result
        open_sids  = sorted(res.open_stations, key=self._station_avg_rt)
        inactive   = [s for s in self._problem.stations if s.id not in res.open_stations]
        n_open     = len(open_sids)
        n_inactive = len(inactive)
        n_total    = n_open + n_inactive

        active_pill = (
            f'<span class="ml-2 px-2 py-0.5 rounded-full text-xs bg-emerald-900 '
            f'text-emerald-300 normal-case tracking-normal font-mono font-normal">'
            f'{n_open} / {n_total} active</span>'
        )
        inactive_pill = (
            f'<span class="ml-2 px-2 py-0.5 rounded-full text-xs bg-slate-700 '
            f'text-slate-400 normal-case tracking-normal font-mono font-normal">'
            f'{n_inactive}</span>'
        )

        active_cards   = "".join(self._render_open_station_card(sid) for sid in open_sids)
        inactive_minis = "".join(self._render_inactive_mini(s) for s in inactive)

        return (
            f'<div class="space-y-8">'
            f'<section><h2 class="section-title">Active Stations{active_pill}</h2>'
            f'<div class="space-y-3">{active_cards}</div></section>'
            f'<section>'
            f'<h2 class="section-title">Not Activated Candidates{inactive_pill}</h2>'
            f'<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">'
            f'{inactive_minis}</div></section>'
            f'</div>'
        )

    # ----------------------------------------- Tab 3: Response Times

    def _render_tab_response(self) -> str:
        res              = self._result
        station_name_map = {s.id: s.name for s in self._problem.stations}

        rows: list[str] = []
        for d in sorted(
            self._problem.districts, key=lambda x: x.wildfire_risk, reverse=True
        ):
            sid   = res.district_assignments.get(d.id, "")
            rt    = self._rt.get((d.id, sid), 0.0) if sid else 0.0
            sname = station_name_map.get(sid, "&#8212;")

            # Subtle row warning tint for response time > 20 min
            row_extra = (
                ' style="background-color:rgba(154,52,18,0.15);"'
                if rt > 20.0 and sid else ""
            )
            response_cell = (
                _rt_badge(rt) if sid
                else '<span class="text-slate-500 text-xs italic">unassigned</span>'
            )

            rows.append(
                f'<tr class="border-t border-slate-700/50 hover:bg-slate-700/20 '
                f'transition-colors text-sm"{row_extra}>'
                f'<td class="px-4 py-2.5 text-slate-200">{_e(d.name)}</td>'
                f'<td class="px-4 py-2.5 text-right font-mono text-slate-300">'
                f'{d.area_km2:.1f}</td>'
                f'<td class="px-4 py-2.5 text-center">{_risk_badge(d.wildfire_risk)}</td>'
                f'<td class="px-4 py-2.5 text-right font-mono text-slate-300">'
                f'{d.demand:.1f}</td>'
                f'<td class="px-4 py-2.5 text-slate-300">{_e(sname)}</td>'
                f'<td class="px-4 py-2.5 text-center">{response_cell}</td></tr>'
            )

        n_covered = sum(1 for d in self._problem.districts if d.id in res.district_assignments)
        n_total   = len(self._problem.districts)
        covered_pill = (
            f'<span class="ml-2 px-2 py-0.5 rounded-full text-xs bg-slate-700 '
            f'text-slate-300 normal-case tracking-normal font-mono font-normal">'
            f'{n_covered}/{n_total} covered</span>'
        )

        # Column headers with sortable markers
        def _th(label: str, col: int, align: str = "") -> str:
            align_cls = f" {align}" if align else ""
            return (
                f'<th class="px-4 py-3 font-medium sortable cursor-pointer '
                f'hover:text-slate-200 select-none whitespace-nowrap{align_cls}" '
                f'data-col="{col}">{label} '
                f'<span class="sort-icon text-slate-600">&#8597;</span></th>'
            )

        thead = (
            f'<tr class="bg-slate-900 text-xs text-slate-400 uppercase tracking-wider">'
            + _th("District", 0)
            + _th("Area km&#178;", 1, "text-right")
            + _th("Risk", 2, "text-center")
            + _th("Demand", 3, "text-right")
            + '<th class="px-4 py-3 font-medium">Assigned Station</th>'
            + _th("Response", 5, "text-center")
            + "</tr>"
        )

        return (
            f'<section>'
            f'<h2 class="section-title">Incident District Profiles{covered_pill}</h2>'
            f'<p class="text-xs text-slate-500 mb-4">'
            f'Rows highlighted in amber indicate response times exceeding 20 minutes. '
            f'Click any column header to sort.</p>'
            f'<div class="bg-slate-800 rounded-xl border border-slate-700 shadow overflow-hidden">'
            f'<div class="overflow-x-auto">'
            f'<table class="w-full text-left" id="districts-table">'
            f'<thead>{thead}</thead>'
            f'<tbody id="districts-tbody">{"".join(rows)}</tbody>'
            f'</table></div></div></section>'
        )

    # ---------------------------------------------------------------- assembly

    def _render_html(self) -> str:
        header     = self._render_header()
        tab_nav    = self._render_tab_nav()
        tab1       = self._render_tab_general()
        tab2       = self._render_tab_stations()
        tab3       = self._render_tab_response()
        styles     = self._styles()
        tab_script = self._tab_script()
        sort_script = self._sort_script()

        return f"""<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MILP Fire Protection Report &#8212; Attica</title>
  <script src="https://cdn.tailwindcss.com"></script>
  {styles}
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased">

{header}
{tab_nav}

<main class="max-w-screen-xl mx-auto px-4 sm:px-6 py-8">
  <div id="tab-general"  class="tab-panel">{tab1}</div>
  <div id="tab-stations" class="tab-panel hidden">{tab2}</div>
  <div id="tab-response" class="tab-panel hidden">{tab3}</div>
</main>

<footer class="mt-16 border-t border-slate-800 py-6">
  <div class="max-w-screen-xl mx-auto px-6 text-center text-xs text-slate-600">
    Fire-Protection-Optimization &middot; MILP Pipeline &middot; Attica Region
  </div>
</footer>

{tab_script}
{sort_script}
</body>
</html>"""
