from __future__ import annotations

from typing import Dict

from ..components import nem_map_component
from .._compat import st
from ..map_payload import _get_cached_marker_payload as _get_cached_marker_payload_impl


def _render_map(filtered_snapshot: Dict[str, Dict[str, str]], display_mode: str) -> None:
    st.subheader("Facility Map")
    st.caption("Green = Renewable | Red = Fossil / Non-renewable | Blue = Storage | Orange = Mixed / Other")
    if not filtered_snapshot:
        st.info("No matching facility data in cache.")
        return
    marker_payload = _get_cached_marker_payload_impl(
        filtered_snapshot,
        display_mode,
        st.session_state.get("selected_fuel", "All"),
        st.session_state.get("selected_region", "All"),
    )
    component_value = nem_map_component.render_nem_facility_map(marker_payload, height=730, key="nem-facility-map")
    if isinstance(component_value, dict):
        next_display_mode = component_value.get("display_mode")
        if next_display_mode in {"power_value", "emission_value"}:
            st.session_state.display_mode = next_display_mode


__all__ = ["_render_map"]
