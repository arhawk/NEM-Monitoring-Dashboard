from src.dashboard.settings import *  # noqa: F401,F403
from src.dashboard.data import *  # noqa: F401,F403
from src.dashboard.map_payload import *  # noqa: F401,F403
from src.dashboard.render import *  # noqa: F401,F403
from src.dashboard.runtime import *  # noqa: F401,F403
from src.shared.stream_cache import (  # noqa: F401
    DEFAULT_MAX_STREAM_ROWS,
    DEFAULT_REFRESH_INTERVAL_SECONDS,
    DEFAULT_RESET_INTERVAL_HOURS,
    StreamCache,
    get_max_stream_rows,
    get_refresh_interval_seconds,
    get_reset_interval_hours,
    utc_now_iso,
)


def _get_cached_marker_payload(records, display_mode, selected_fuel, selected_region):
    cache_key = "_nem_map_marker_payload_cache"
    next_signature = _build_map_signature(records, display_mode, selected_fuel, selected_region)
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == next_signature:
        payload = cached.get("payload")
        if isinstance(payload, dict):
            return payload

    payload = _build_marker_payload(records, display_mode, selected_fuel, selected_region)
    st.session_state[cache_key] = {
        "signature": next_signature,
        "payload": payload,
    }
    return payload


def _render_map(filtered_snapshot, display_mode):
    st.subheader("Facility Map")
    st.caption("Green = Renewable | Red = Fossil / Non-renewable | Blue = Storage | Orange = Mixed / Other")
    if not filtered_snapshot:
        st.info("No matching facility data in cache.")
        return
    marker_payload = _get_cached_marker_payload(
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


def _render_sidebar(runtime, snapshot, filtered_snapshot, data_source, fuel_options):
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


def render_dashboard():
    _render_dashboard_main()
    with st.sidebar:
        _render_dashboard_sidebar()


def main():
    set_active_runtime(get_runtime())
    render_dashboard()


if __name__ == "__main__":
    main()
