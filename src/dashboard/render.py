from __future__ import annotations

import html
import textwrap

import pandas as pd

from .components.nem_map_component import render_nem_facility_map
from ._compat import components, st
from .context import (
    _build_dashboard_context,
    _build_dashboard_context_payload,
    _build_dashboard_context_signature,
    _ensure_session_defaults,
    _resolve_data_source,
)
from .data import _load_fallback_messages
from .runtime import DashboardRuntime, get_active_runtime, _soft_reset_runtime
from .views.header import _build_current_trend_html, _render_current_trend, _render_header
from .views.map import _render_map
from .views.sidebar import _render_sidebar
from .views.table import _render_table
from .settings import READY_NOTICE_SESSION_KEY, REFRESH_INTERVAL_SECONDS


def configure_page() -> None:
    st.set_page_config(page_title="NEM Facility Real-time Monitoring Dashboard", layout="wide")


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
    "READY_NOTICE_SESSION_KEY",
    "configure_page",
    "_build_current_trend_html",
    "_render_current_trend",
    "_render_header",
    "_render_sidebar",
    "_render_table",
    "_render_map",
    "_build_dashboard_context",
    "_ensure_session_defaults",
    "_build_dashboard_context_signature",
    "_build_dashboard_context_payload",
    "_load_fallback_messages",
    "_resolve_data_source",
    "_render_dashboard_main",
    "_render_dashboard_sidebar",
    "render_dashboard",
]
