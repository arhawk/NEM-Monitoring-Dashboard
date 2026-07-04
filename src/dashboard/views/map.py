from __future__ import annotations

from typing import Any, Dict

from .._compat import st
from ..components import nem_map_component
from ..data.map_payload import (
    _build_map_signature,
    _build_marker_payload,
    _build_operational_signature,
    _build_static_signature,
    _marker_color,
    _marker_fingerprint,
    _marker_popup_html,
    _marker_radius,
)
from ..render_context import MapModel


def _get_cached_marker_payload(
    records: Dict[str, Dict[str, Any]],
    display_mode: str,
    selected_fuel: str,
    selected_region: str,
    signature: tuple | None = None,
) -> Dict[str, Any]:
    cache_key = "_nem_map_marker_payload_cache"
    next_signature = signature or _build_map_signature(records, display_mode, selected_fuel, selected_region)
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == next_signature:
        payload = cached.get("payload")
        if isinstance(payload, dict):
            return payload

    payload = _build_marker_payload(records, display_mode, selected_fuel, selected_region)
    st.session_state[cache_key] = {"signature": next_signature, "payload": payload}
    return payload


def _coerce_map_model(
    model_or_records: MapModel | Dict[str, Dict[str, Any]],
    display_mode: str | None = None,
    selected_fuel: str | None = None,
    selected_region: str | None = None,
) -> MapModel:
    if isinstance(model_or_records, MapModel):
        return model_or_records
    return MapModel(
        filtered_snapshot=model_or_records,
        display_mode=display_mode or st.session_state.get("display_mode", "power_value"),
        selected_fuel=selected_fuel or st.session_state.get("selected_fuel", "All"),
        selected_region=selected_region or st.session_state.get("selected_region", "All"),
        cache_signature=_build_map_signature(
            model_or_records,
            display_mode or st.session_state.get("display_mode", "power_value"),
            selected_fuel or st.session_state.get("selected_fuel", "All"),
            selected_region or st.session_state.get("selected_region", "All"),
        ),
    )


def _render_map(
    model_or_records: MapModel | Dict[str, Dict[str, Any]],
    display_mode: str | None = None,
) -> None:
    model = _coerce_map_model(model_or_records, display_mode=display_mode)
    st.subheader("Facility Map")
    if not model.filtered_snapshot:
        st.info("No matching facility data in cache.")
        return
    marker_payload = _get_cached_marker_payload(
        model.filtered_snapshot,
        model.display_mode,
        model.selected_fuel,
        model.selected_region,
        model.cache_signature,
    )
    component_value = nem_map_component.render_nem_facility_map(marker_payload, height=730, key="nem-facility-map")
    if isinstance(component_value, dict):
        next_display_mode = component_value.get("display_mode")
        if next_display_mode in {"power_value", "emission_value"}:
            st.session_state.display_mode = next_display_mode


__all__ = [
    "_marker_color",
    "_marker_radius",
    "_marker_popup_html",
    "_marker_fingerprint",
    "_build_static_signature",
    "_build_operational_signature",
    "_build_map_signature",
    "_build_marker_payload",
    "_get_cached_marker_payload",
    "_render_map",
]
