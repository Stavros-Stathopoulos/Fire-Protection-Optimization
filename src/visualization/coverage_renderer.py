"""Folium renderer for operational fire-station coverage maps.

Refactored from ``test2.py`` lines 304–397.  Produces an interactive HTML
map with:
  * Colour-coded coverage polygons (community-unit and municipality layers).
  * Fire-station markers with type-specific iconography (ΠΣ / ΠΥ / ΠΚ).
  * Legend overlay and layer controls.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import folium
import geopandas as gpd

from .models import CoverageAssignment, StationRecord


# ---------------------------------------------------------------------------
# Colour generation
# ---------------------------------------------------------------------------

_PALETTE: tuple[str, ...] = (
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#a65628", "#f781bf", "#66c2a5", "#fc8d62", "#8da0cb",
    "#e78ac3", "#a6d854", "#1b9e77", "#d95f02", "#7570b3",
)

_UNASSIGNED_COLOUR = "#8c8c8c"

# Station-type → marker colour
_ICON_COLOUR: dict[str, str] = {
    "ΠΣ": "red",
    "ΠΥ": "orange",
    "ΠΚ": "darkblue",
}


def get_distinct_color(station_id: str) -> str:
    """Return a stable hex colour for *station_id* via MD5 hashing."""
    if station_id == "unknown":
        return _UNASSIGNED_COLOUR
    idx = int(hashlib.md5(station_id.encode()).hexdigest(), 16) % len(_PALETTE)
    return _PALETTE[idx]


# ---------------------------------------------------------------------------
# Polygon / marker rendering helpers
# ---------------------------------------------------------------------------

def _render_coverage_polygon(
    row: CoverageAssignment,
    target: folium.FeatureGroup,
    *,
    opacity: float = 0.55,
) -> None:
    """Add a single coverage polygon to the Folium layer."""
    color = get_distinct_color(row.station_id)
    popup_html = (
        f'<div style="font-family:\'Segoe UI\', sans-serif; min-width:220px; font-size:12px;">'
        f'<h4 style="margin:0; padding:6px; background:{color}; color:white; '
        f'border-radius:4px 4px 0 0;">{row.unit_name}</h4>'
        f'<div style="padding:8px; border:1px solid #ddd; border-top:none; background:white;">'
        f"<b>Δήμος:</b> {row.mun_name}<br>"
        f'<b>Σταθμός:</b> <span style="color:{color}; font-weight:bold;">'
        f"{row.station_name}</span><br>"
        f"<b>Τύπος:</b> {row.station_type}<br>"
        f'<small style="color:#777;">Μέθοδος: {row.match_method}</small>'
        f"</div></div>"
    )
    folium.GeoJson(
        data=row.geometry.__geo_interface__,
        style_function=lambda _, c=color, o=opacity: {
            "fillColor": c,
            "color": "white",
            "weight": 1.0,
            "fillOpacity": o,
        },
        highlight_function=lambda _: {
            "weight": 2.5,
            "color": "#222",
            "fillOpacity": 0.8,
        },
        tooltip=folium.Tooltip(
            f"<b>{row.unit_name}</b> ({row.mun_name})<br>→ {row.station_name}"
        ),
        popup=folium.Popup(popup_html, max_width=300),
    ).add_to(target)


def _render_station_markers(
    stations: list[StationRecord],
    target: folium.FeatureGroup,
) -> None:
    """Add fire-station markers to the Folium layer."""
    for station in stations:
        if not station.lat or not station.lon:
            continue

        muns_html = "<br>".join(f"• {m}" for m in station.assigned_municipalities)
        comms_html = ""
        if station.assigned_communities:
            comms_html = (
                "<hr style='margin:4px 0; border-color:#eee;'>"
                "<b>Τομέας Ευθύνης (Κοινότητες):</b><br>"
                "<small style='color:#555;'>"
                + "<br>".join(f"• {c}" for c in station.assigned_communities)
                + "</small>"
            )

        popup_html = (
            f"<div style=\"font-family:'Segoe UI',sans-serif; font-size:12px; max-width:250px;\">"
            f"<b style='font-size:13px;'>🚒 {station.name}</b><br>"
            f"<b>Τύπος:</b> {station.station_type}<br>"
            f"<hr style='margin:4px 0; border-color:#eee;'>"
            f"<b>Τομέας Ευθύνης (Δήμοι):</b><br>"
            f"<small style='color:#555;'>{muns_html}</small>"
            f"{comms_html}"
            f"</div>"
        )

        folium.Marker(
            location=[station.lat, station.lon],
            tooltip=folium.Tooltip(f"🚒 {station.name}"),
            popup=folium.Popup(popup_html, max_width=260),
            icon=folium.Icon(
                color=_ICON_COLOUR.get(station.station_type, "gray"),
                icon="fire",
                prefix="fa",
            ),
        ).add_to(target)


def _render_legend() -> folium.Element:
    """Build the fixed-position HTML legend overlay."""
    return folium.Element(
        '<div style="position:fixed; bottom:36px; left:12px; z-index:9999; background:white;'
        " padding:10px 14px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.25);"
        " font-family:'Segoe UI',sans-serif; font-size:12px; line-height:1.9\">"
        '<b style="font-size:13px">Υπόμνημα Σταθμών</b><br>'
        '<span style="color:#dc2626">●</span> <b>Δομές ΠΣ</b> — Πυροσβεστικός Σταθμός<br>'
        '<span style="color:#ea580c">●</span> <b>Δομές ΠΥ</b> — Πυροσβεστική Υπηρεσία<br>'
        '<span style="color:#1d4ed8">●</span> <b>Δομές ΠΚ</b> — Πυροσβεστικό Κλιμάκιο<br>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CoverageMapRenderer:
    """Renders the operational coverage map to interactive HTML.

    Parameters
    ----------
    center:
        ``(lat, lon)`` map centre.
    zoom_start:
        Initial zoom level.
    """

    def __init__(
        self,
        center: tuple[float, float] = (38.05, 23.75),
        zoom_start: int = 10,
    ) -> None:
        self._center = list(center)
        self._zoom = zoom_start

    def render(
        self,
        community_assignments: list[CoverageAssignment],
        municipality_assignments: list[CoverageAssignment],
        stations: list[StationRecord],
        output_path: Path | str,
    ) -> folium.Map:
        """Build and save the coverage map.

        Parameters
        ----------
        community_assignments:
            One ``CoverageAssignment`` per OSM community unit.
        municipality_assignments:
            Base-layer municipality polygons for gap-filling.
        stations:
            Parsed ``StationRecord`` objects for marker rendering.
        output_path:
            File path for the saved HTML.

        Returns
        -------
        folium.Map
            The constructed map object (also saved to *output_path*).
        """
        m = folium.Map(
            location=self._center,
            zoom_start=self._zoom,
            tiles="CartoDB positron",
        )

        # -- Coverage layer --------------------------------------------------
        coverage_layer = folium.FeatureGroup(
            name="📍 Αρμοδιότητα (Υβριδική Ανάλυση)", show=True
        )

        # Municipality base layer first (background)
        for assignment in municipality_assignments:
            _render_coverage_polygon(assignment, coverage_layer, opacity=0.40)

        # Community units on top
        for assignment in community_assignments:
            _render_coverage_polygon(assignment, coverage_layer, opacity=0.55)

        coverage_layer.add_to(m)

        # -- Station markers -------------------------------------------------
        station_layer = folium.FeatureGroup(
            name="🚒 Πυροσβεστικοί Σταθμοί", show=True
        )
        _render_station_markers(stations, station_layer)
        station_layer.add_to(m)

        # -- Legend & controls -----------------------------------------------
        m.get_root().html.add_child(_render_legend())
        folium.LayerControl(collapsed=False).add_to(m)

        # -- Save ------------------------------------------------------------
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(output))
        print(f"✅ Coverage map saved → {output}")

        return m
