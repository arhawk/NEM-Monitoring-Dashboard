from __future__ import annotations

from ._compat import st
from .render_context import _build_dashboard_context, _build_map_model, _build_sidebar_model
from .views.header import _render_current_trend, _render_header
from .views.map import _render_map
from .views.sidebar import _render_sidebar
from .views.table import _render_table
from .settings import REFRESH_INTERVAL_SECONDS


def configure_page() -> None:
    st.set_page_config(page_title="NEM Facility Real-time Monitoring Dashboard", layout="wide")


@st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
def _render_dashboard_main() -> None:
    context = _build_dashboard_context()
    map_model = _build_map_model(context)
    _render_header(context.runtime, context.stats, context.snapshot)
    _render_current_trend(context.messages)
    _render_map(map_model)
    _render_table(context.filtered_snapshot)


@st.fragment(run_every=REFRESH_INTERVAL_SECONDS)
def _render_dashboard_sidebar() -> None:
    context = _build_dashboard_context()
    sidebar_model = _build_sidebar_model(context)
    _render_sidebar(sidebar_model)


def render_dashboard() -> None:
    _render_dashboard_main()
    with st.sidebar:
        _render_dashboard_sidebar()


__all__ = [
    "configure_page",
    "render_dashboard",
]
