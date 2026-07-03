from __future__ import annotations

import html
import textwrap
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .components.nem_map_component import render_nem_facility_map
from .data import (
    _build_current_trend_cards,
    _build_fuel_options,
    _build_latest_snapshot,
    _calculate_snapshot_stats,
    _filter_snapshot,
    _format_optional_metric,
    _format_ts,
    _get_latest_trend_message,
    _load_fallback_messages,
    _resolve_data_source,
    _should_use_fallback,
)
from .map_payload import _get_cached_marker_payload as _get_cached_marker_payload_impl
from .runtime import DashboardRuntime, get_active_runtime, _soft_reset_runtime
from .settings import (
    DISPLAY_REGION_OPTIONS,
    READY_NOTICE_SESSION_KEY,
    REFRESH_INTERVAL_SECONDS,
    SIDEBAR_HEADER_TITLE,
)

_DASHBOARD_CONTEXT_CACHE_KEY = "_dashboard_render_context"


def configure_page() -> None:
    st.set_page_config(page_title="NEM Facility Real-time Monitoring Dashboard", layout="wide")


def _build_current_trend_html(message: Dict[str, Any]) -> str:
    facility_name = html.escape(str(message.get("facility_name") or message.get("facility_code") or "Unknown Facility"))
    facility_code = html.escape(str(message.get("facility_code") or ""))
    timestamp = html.escape(str(message.get("timestamp") or ""))
    details = " | ".join(part for part in (facility_code, timestamp) if part)
    cards = _build_current_trend_cards(message)
    card_items = []
    for card in cards:
        card_items.append(
            f"""
            <div style="
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 12px;
                min-width: 0;
            ">
              <div style="font-size: 0.74rem; color: #64748b; font-weight: 600; line-height: 1.2; margin-bottom: 4px;">
                {html.escape(card["label"])}
              </div>
              <div style="font-size: 0.96rem; color: #0f172a; font-weight: 700; line-height: 1.2;">
                {html.escape(card["value"])}
              </div>
            </div>
            """
        )

    detail_html = f'<div style="font-size: 0.8rem; color: #64748b; margin-top: 4px;">{details}</div>' if details else ""
    return textwrap.dedent(
        f"""
        <div style="
            border: 1px solid #dbe4ee;
            border-radius: 14px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding: 12px 14px 14px 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            margin-top: 2px;
        ">
          <div style="font-size: 0.92rem; color: #0f172a; font-weight: 700; line-height: 1.2;">
            Current Facility: {facility_name}
          </div>
          {detail_html}
          <div style="
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
          ">
            {''.join(card_items)}
          </div>
        </div>
        """
    ).strip()


def _render_current_trend(messages: List[Dict[str, Any]]) -> None:
    latest = _get_latest_trend_message(messages)
    if latest is None:
        st.subheader("Current Facility")
        st.info("No MQTT messages available for current trend yet.")
        return

    components.html(_build_current_trend_html(latest), height=220, scrolling=False)


def _render_header(runtime: DashboardRuntime, stats: Dict[str, Any], snapshot: Dict[str, Dict[str, Any]]) -> None:
    st.title("⚡ National Electricity Market (NEM) Facility Real-time Monitoring Dashboard")
    st.caption("Live MQTT stream with bounded in-memory cache. No live CSV storage is used.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Power Output MW", f"{stats['total_power']}")
    with col2:
        st.metric("Total CO2 Emissions tCO2e", _format_optional_metric(stats["total_emission"], "tCO2e"))
    with col3:
        st.metric("Median Price $/MWh", _format_optional_metric(stats["median_price"], "$/MWh"))
    with col4:
        st.metric("Median Grid Demand MW", _format_optional_metric(stats["median_demand"], "MW"))


def _render_sidebar(
    runtime: DashboardRuntime,
    snapshot: Dict[str, Dict[str, Any]],
    filtered_snapshot: Dict[str, Dict[str, Any]],
    data_source: str,
    fuel_options: List[str],
) -> None:
    st.markdown(
        textwrap.dedent(
            f"""
            <style>
              section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarHeader"] {{
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: 0.5rem;
                margin-bottom: 0 !important;
              }}

              section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarHeader"]::before {{
                content: "{SIDEBAR_HEADER_TITLE}";
                flex: 1 1 auto;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: 1.25rem;
                font-weight: 700;
                line-height: 1.2;
                color: inherit;
              }}

              section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"]::before {{
                content: "";
              }}

              section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarHeader"] > :first-child {{
                flex: 0 0 auto;
                min-width: 0;
              }}

              section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"] {{
                margin-left: auto;
                display: inline-flex;
                align-items: center;
              }}

              section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"] button {{
                padding: 0;
              }}

              section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
                overflow-y: hidden !important;
              }}

              section[data-testid="stSidebar"] [data-testid="stSidebarContent"] > div:first-child {{
                margin-top: 0 !important;
              }}

              section[data-testid="stSidebar"] [data-testid="stSidebarContent"] h2:first-of-type,
              section[data-testid="stSidebar"] [data-testid="stSidebarContent"] h3:first-of-type {{
                margin-top: 0 !important;
              }}
            </style>
            """
        ).strip(),
        unsafe_allow_html=True,
    )
    st.subheader("MQTT Status")
    if runtime.status == "Connected":
        st.success("Connected")
    elif runtime.status == "Connecting":
        st.info("Connecting")
    elif runtime.status == "Disconnected":
        st.warning("Disconnected")
    else:
        st.error("Error")
    st.write(f"Messages since reset: {runtime.cache.messages_since_reset()}")
    if runtime.last_error:
        st.caption(runtime.last_error)

    if data_source == "fallback":
        st.info("Waiting for cache messages. Showing sample replay fallback.")
        st.session_state[READY_NOTICE_SESSION_KEY] = True
    elif st.session_state.get(READY_NOTICE_SESSION_KEY):
        st.success("Real-time data ready")
        st.session_state[READY_NOTICE_SESSION_KEY] = False

    st.subheader("Grid Region Filter")
    st.selectbox("Select Region", DISPLAY_REGION_OPTIONS, key="selected_region")

    st.subheader("Fuel Type Filter")
    if st.session_state.get("selected_fuel") not in fuel_options:
        st.session_state.selected_fuel = "All"
    st.selectbox("Select Fuel Type", fuel_options, key="selected_fuel")
    selected_count = len(filtered_snapshot)
    selected_label = "facility selected" if selected_count == 1 else "facilities selected"
    st.caption(f"{selected_count} {selected_label}")

    st.subheader("Data Statistics")
    st.write(f"Facilities in snapshot: {len(snapshot)}")
    st.write(f"MQTT cache size: {runtime.cache.size()} / {runtime.cache.max_size()}")

    if st.button("Reset Cache", key="reset_cache"):
        _soft_reset_runtime(runtime)

    st.write(f"Last soft reset: {_format_ts(runtime.last_soft_reset_at.timestamp())}")


def _render_table(filtered_snapshot: Dict[str, Dict[str, Any]]) -> None:
    st.subheader("Facility Data Preview")
    if not filtered_snapshot:
        st.info("No matching records in the current cache.")
        return
    preview = pd.DataFrame(filtered_snapshot.values())
    cols = [
        "facility_code",
        "facility_name",
        "state",
        "fuel_group",
        "fuel_list",
        "power_value",
        "emission_value",
        "price_per_mwh",
        "demand_mw",
        "timestamp",
    ]
    existing = [col for col in cols if col in preview.columns]
    st.dataframe(preview[existing].sort_values("facility_code"), width="stretch", height=260)


def _render_map(filtered_snapshot: Dict[str, Dict[str, Any]], display_mode: str) -> None:
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
    component_value = render_nem_facility_map(marker_payload, height=730, key="nem-facility-map")
    if isinstance(component_value, dict):
        next_display_mode = component_value.get("display_mode")
        if next_display_mode in {"power_value", "emission_value"}:
            st.session_state.display_mode = next_display_mode


def _build_dashboard_context_signature(runtime: DashboardRuntime) -> tuple:
    cache = runtime.cache
    last_updated_at = cache.last_updated_at()
    last_reset_at = cache.last_reset_at()
    return (
        runtime.status,
        runtime.last_error,
        st.session_state.get("display_mode", "power_value"),
        st.session_state.get("selected_fuel", "All"),
        st.session_state.get("selected_region", "All"),
        cache.messages_since_reset(),
        cache.size(),
        last_updated_at,
        last_reset_at,
        _should_use_fallback(runtime),
    )


def _build_dashboard_context_payload(runtime: DashboardRuntime) -> Dict[str, Any]:
    live_messages = runtime.cache.get_recent_messages()
    use_fallback = _should_use_fallback(runtime)
    fallback_messages = _load_fallback_messages() if use_fallback else []
    data_source = _resolve_data_source(live_messages)
    messages = live_messages if live_messages else fallback_messages
    snapshot = _build_latest_snapshot(messages)
    fuel_options = _build_fuel_options(snapshot)
    if st.session_state.get("selected_fuel") not in fuel_options:
        st.session_state.selected_fuel = "All"
    filtered_snapshot = _filter_snapshot(snapshot, st.session_state.selected_fuel, st.session_state.selected_region)
    stats = _calculate_snapshot_stats(snapshot)
    return {
        "runtime": runtime,
        "data_source": data_source,
        "messages": messages,
        "snapshot": snapshot,
        "filtered_snapshot": filtered_snapshot,
        "fuel_options": fuel_options,
        "stats": stats,
    }


def _build_dashboard_context() -> Dict[str, Any]:
    runtime = get_active_runtime()
    _ensure_session_defaults()
    next_signature = _build_dashboard_context_signature(runtime)
    cached = st.session_state.get(_DASHBOARD_CONTEXT_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("signature") == next_signature:
        payload = cached.get("payload")
        if isinstance(payload, dict):
            return payload

    payload = _build_dashboard_context_payload(runtime)
    st.session_state[_DASHBOARD_CONTEXT_CACHE_KEY] = {"signature": next_signature, "payload": payload}
    return payload


def _ensure_session_defaults() -> None:
    if "display_mode" not in st.session_state:
        st.session_state.display_mode = "power_value"
    if "selected_fuel" not in st.session_state:
        st.session_state.selected_fuel = "All"
    if "selected_region" not in st.session_state:
        st.session_state.selected_region = "All"
    if READY_NOTICE_SESSION_KEY not in st.session_state:
        st.session_state[READY_NOTICE_SESSION_KEY] = False


@st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
def _render_dashboard_main() -> None:
    context = _build_dashboard_context()
    _render_header(context["runtime"], context["stats"], context["snapshot"])
    _render_current_trend(context["messages"])
    _render_map(context["filtered_snapshot"], st.session_state.display_mode)
    _render_table(context["filtered_snapshot"])


@st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
def _render_dashboard_sidebar() -> None:
    context = _build_dashboard_context()
    _render_sidebar(
        context["runtime"],
        context["snapshot"],
        context["filtered_snapshot"],
        context["data_source"],
        context["fuel_options"],
    )


def render_dashboard() -> None:
    _render_dashboard_main()
    with st.sidebar:
        _render_dashboard_sidebar()


__all__ = [
    "html",
    "textwrap",
    "pd",
    "st",
    "components",
    "render_nem_facility_map",
    "configure_page",
    "_build_current_trend_html",
    "_render_current_trend",
    "_render_header",
    "_render_sidebar",
    "_render_table",
    "_render_map",
    "_build_dashboard_context",
    "_ensure_session_defaults",
    "_render_dashboard_main",
    "_render_dashboard_sidebar",
    "render_dashboard",
]
