from __future__ import annotations

import textwrap
from typing import Dict, List

from ..data import _format_ts
from .._compat import st
from ..runtime import DashboardRuntime, _soft_reset_runtime
from ..settings import DISPLAY_REGION_OPTIONS, READY_NOTICE_SESSION_KEY, SIDEBAR_HEADER_TITLE


def _render_sidebar(
    runtime: DashboardRuntime,
    snapshot: Dict[str, Dict[str, str]],
    filtered_snapshot: Dict[str, Dict[str, str]],
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
    elif data_source == "stale_live_replaced":
        st.info("Live cache is stale. Showing sample replay fallback.")
        st.session_state[READY_NOTICE_SESSION_KEY] = True
    elif data_source == "empty":
        st.info("Waiting for cache messages.")
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


__all__ = ["_render_sidebar"]
