from __future__ import annotations

import textwrap
from typing import Dict, List

from .._compat import st
from ..data import _format_ts
from ..actions import (
    describe_publisher_workflow_status,
    get_last_runs,
    get_last_trigger_result,
    get_recent_or_running_publisher_runs,
    AUTO_START_PUBLISHER,
    is_github_actions_control_enabled,
    maybe_auto_start_publisher,
)
from ..render_context import SidebarModel
from ..runtime import DashboardRuntime, _soft_reset_runtime
from ..settings import DISPLAY_REGION_OPTIONS, SIDEBAR_HEADER_TITLE


def _coerce_sidebar_model(
    model_or_runtime: SidebarModel | DashboardRuntime,
    snapshot: Dict[str, Dict[str, str]] | None = None,
    filtered_snapshot: Dict[str, Dict[str, str]] | None = None,
    data_source: str | None = None,
    fuel_options: List[str] | None = None,
) -> SidebarModel:
    if isinstance(model_or_runtime, SidebarModel):
        return model_or_runtime

    runtime = model_or_runtime
    snapshot = snapshot or {}
    filtered_snapshot = filtered_snapshot or {}
    data_source = data_source or ("live" if snapshot else "empty")
    fuel_options = fuel_options or ["All"]
    selected_fuel = st.session_state.get("selected_fuel", "All")
    selected_region = st.session_state.get("selected_region", "All")
    return SidebarModel(
        runtime=runtime,
        data_source=data_source,
        status=runtime.status,
        last_error=runtime.last_error,
        messages_since_reset=runtime.cache.messages_since_reset(),
        cache_size=runtime.cache.size(),
        cache_max_size=runtime.cache.max_size(),
        last_soft_reset_at=runtime.last_soft_reset_at,
        snapshot_count=len(snapshot),
        selected_count=len(filtered_snapshot),
        selected_fuel=selected_fuel,
        selected_region=selected_region,
        fuel_options=fuel_options,
    )


def _render_sidebar(
    model_or_runtime: SidebarModel | DashboardRuntime,
    snapshot: Dict[str, Dict[str, str]] | None = None,
    filtered_snapshot: Dict[str, Dict[str, str]] | None = None,
    data_source: str | None = None,
    fuel_options: List[str] | None = None,
) -> None:
    model = _coerce_sidebar_model(model_or_runtime, snapshot, filtered_snapshot, data_source, fuel_options)
    github_control_enabled = is_github_actions_control_enabled()
    if github_control_enabled and AUTO_START_PUBLISHER:
        maybe_auto_start_publisher()
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
    if model.status == "Connected":
        st.success("Connected")
    elif model.status == "Connecting":
        st.info("Connecting")
    elif model.status == "Disconnected":
        st.warning("Disconnected")
    else:
        st.error("Error")
    st.write(f"Messages since reset: {model.messages_since_reset}")
    if model.last_error:
        st.caption(model.last_error)

    st.subheader("Grid Region Filter")
    st.selectbox("Select Region", DISPLAY_REGION_OPTIONS, key="selected_region")

    st.subheader("Fuel Type Filter")
    if st.session_state.get("selected_fuel") not in model.fuel_options:
        st.session_state.selected_fuel = "All"
    st.selectbox("Select Fuel Type", model.fuel_options, key="selected_fuel")
    selected_label = "facility selected" if model.selected_count == 1 else "facilities selected"
    st.caption(f"{model.selected_count} {selected_label}")

    st.subheader("Data Statistics")
    st.write(f"Facilities in snapshot: {model.snapshot_count}")
    st.write(f"MQTT cache size: {model.cache_size} / {model.cache_max_size}")

    st.markdown(
        textwrap.dedent(
            """
            <style>
              div[data-testid="stButton"] > button[kind="primary"] {
                background: #dc2626;
                border: 1px solid #b91c1c;
                color: #ffffff;
              }

              div[data-testid="stButton"] > button[kind="primary"]:hover {
                background: #b91c1c;
                border-color: #991b1b;
                color: #ffffff;
              }

              div[data-testid="stButton"] > button[kind="primary"]:focus:not(:active) {
                border-color: #fca5a5;
                box-shadow: 0 0 0 0.15rem rgba(220, 38, 38, 0.25);
              }
            </style>
            """
        ).strip(),
        unsafe_allow_html=True,
    )
    if st.button("Reset Cache", key="reset_cache", type="primary"):
        _soft_reset_runtime(model.runtime)

    st.write(f"Last soft reset: {_format_ts(model.runtime.last_soft_reset_at.timestamp())}")

    if not github_control_enabled:
        return

    st.subheader("Cloud Deployment Publisher")
    st.caption("The GitHub Actions publisher runs for 10 minutes and then stops automatically.")

    st.write(f"Auto-start: {'Enabled' if AUTO_START_PUBLISHER else 'Disabled'}")

    try:
        current_runs = get_recent_or_running_publisher_runs()
    except Exception as exc:
        current_runs = get_last_runs()
        if not current_runs:
            st.warning(f"Unable to load GitHub Actions workflow status: {exc}")

    workflow_status = describe_publisher_workflow_status()
    if workflow_status:
        st.write(f"Publisher workflow status: {workflow_status}")
    else:
        st.write("Publisher workflow status: unavailable")

    last_trigger = get_last_trigger_result()
    if last_trigger:
        message = last_trigger.get("message") or "No trigger message recorded."
        if last_trigger.get("error"):
            st.warning(f"{message} {last_trigger['error']}")
        elif last_trigger.get("triggered"):
            st.success(message)
        else:
            st.info(message)
    else:
        st.caption("Last trigger result: unavailable")

    active_runs = [run for run in current_runs if run.get("status") in {"queued", "in_progress"}]
    st.write(f"Active workflow runs: {len(active_runs)}")


__all__ = ["_render_sidebar"]
