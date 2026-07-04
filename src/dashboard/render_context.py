from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ._compat import st as compat_st
from . import runtime as runtime_module
from .data import fallback as fallback_module
from .data.aggregation import _build_fuel_options, _build_latest_snapshot, _calculate_snapshot_stats, _filter_snapshot
from .data.map_payload import _build_map_signature
from .settings import READY_NOTICE_SESSION_KEY


@dataclass(frozen=True)
class DashboardContext:
    runtime: Any
    data_source: str
    messages: List[Dict[str, Any]]
    snapshot: Dict[str, Dict[str, Any]]
    filtered_snapshot: Dict[str, Dict[str, Any]]
    fuel_options: List[str]
    stats: Dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class SidebarModel:
    runtime: Any
    data_source: str
    status: str
    last_error: Optional[str]
    messages_since_reset: int
    cache_size: int
    cache_max_size: int
    last_soft_reset_at: datetime
    snapshot_count: int
    selected_count: int
    selected_fuel: str
    selected_region: str
    fuel_options: List[str]
    notice_tone: Optional[str]
    notice_message: Optional[str]


@dataclass(frozen=True)
class MapModel:
    filtered_snapshot: Dict[str, Dict[str, Any]]
    display_mode: str
    selected_fuel: str
    selected_region: str
    cache_signature: tuple


def _ensure_session_defaults() -> None:
    if "display_mode" not in compat_st.session_state:
        compat_st.session_state.display_mode = "power_value"
    if "selected_fuel" not in compat_st.session_state:
        compat_st.session_state.selected_fuel = "All"
    if "selected_region" not in compat_st.session_state:
        compat_st.session_state.selected_region = "All"
    if READY_NOTICE_SESSION_KEY not in compat_st.session_state:
        compat_st.session_state[READY_NOTICE_SESSION_KEY] = False


def _resolve_data_source(
    live_messages: list[Dict[str, Any]],
    *,
    use_fallback: bool = False,
    fallback_messages: list[Dict[str, Any]] | None = None,
) -> str:
    return fallback_module._resolve_data_source(
        live_messages,
        use_fallback=use_fallback,
        fallback_messages=fallback_messages,
    )


def _build_dashboard_context_signature(runtime: Any) -> tuple:
    cache = runtime.cache
    last_updated_at = cache.last_updated_at()
    last_reset_at = cache.last_reset_at()
    return (
        runtime.status,
        runtime.last_error,
        compat_st.session_state.get("display_mode", "power_value"),
        compat_st.session_state.get("selected_fuel", "All"),
        compat_st.session_state.get("selected_region", "All"),
        cache.size(),
        last_updated_at,
        last_reset_at,
        fallback_module._should_use_fallback(runtime),
    )


def _build_dashboard_context_payload(runtime: Any) -> DashboardContext:
    live_messages = runtime.cache.get_recent_messages()
    use_fallback = fallback_module._should_use_fallback(runtime)
    fallback_messages = fallback_module._load_fallback_messages() if use_fallback else []
    decision = fallback_module._resolve_dashboard_messages(
        live_messages,
        use_fallback=use_fallback,
        fallback_messages=fallback_messages,
    )
    messages = decision.messages
    data_source = decision.kind

    snapshot = _build_latest_snapshot(messages)
    fuel_options = _build_fuel_options(snapshot)
    if compat_st.session_state.get("selected_fuel") not in fuel_options:
        compat_st.session_state.selected_fuel = "All"
    filtered_snapshot = _filter_snapshot(
        snapshot,
        compat_st.session_state.selected_fuel,
        compat_st.session_state.selected_region,
    )
    stats = _calculate_snapshot_stats(snapshot)
    return DashboardContext(
        runtime=runtime,
        data_source=data_source,
        messages=messages,
        snapshot=snapshot,
        filtered_snapshot=filtered_snapshot,
        fuel_options=fuel_options,
        stats=stats,
    )


def _build_sidebar_model(context: DashboardContext) -> SidebarModel:
    runtime = context.runtime
    selected_fuel = compat_st.session_state.get("selected_fuel", "All")
    selected_region = compat_st.session_state.get("selected_region", "All")
    notice_tone: Optional[str] = None
    notice_message: Optional[str] = None

    if context.data_source == "fallback":
        notice_tone = "info"
        notice_message = "Waiting for cache messages. Showing sample replay fallback."
        compat_st.session_state[READY_NOTICE_SESSION_KEY] = True
    elif context.data_source == "stale_live_replaced":
        notice_tone = "info"
        notice_message = "Live cache is stale. Showing sample replay fallback."
        compat_st.session_state[READY_NOTICE_SESSION_KEY] = True
    elif compat_st.session_state.get(READY_NOTICE_SESSION_KEY):
        notice_tone = "success"
        notice_message = "Real-time data ready"
        compat_st.session_state[READY_NOTICE_SESSION_KEY] = False

    return SidebarModel(
        runtime=runtime,
        data_source=context.data_source,
        status=runtime.status,
        last_error=runtime.last_error,
        messages_since_reset=runtime.cache.messages_since_reset(),
        cache_size=runtime.cache.size(),
        cache_max_size=runtime.cache.max_size(),
        last_soft_reset_at=runtime.last_soft_reset_at,
        snapshot_count=len(context.snapshot),
        selected_count=len(context.filtered_snapshot),
        selected_fuel=selected_fuel,
        selected_region=selected_region,
        fuel_options=context.fuel_options,
        notice_tone=notice_tone,
        notice_message=notice_message,
    )


def _build_map_model(context: DashboardContext) -> MapModel:
    display_mode = compat_st.session_state.get("display_mode", "power_value")
    selected_fuel = compat_st.session_state.get("selected_fuel", "All")
    selected_region = compat_st.session_state.get("selected_region", "All")
    return MapModel(
        filtered_snapshot=context.filtered_snapshot,
        display_mode=display_mode,
        selected_fuel=selected_fuel,
        selected_region=selected_region,
        cache_signature=_build_map_signature(context.filtered_snapshot, display_mode, selected_fuel, selected_region),
    )


def _build_dashboard_context() -> DashboardContext:
    runtime = runtime_module.get_active_runtime()
    _ensure_session_defaults()
    next_signature = _build_dashboard_context_signature(runtime)
    cached = compat_st.session_state.get("_dashboard_render_context")
    if isinstance(cached, dict) and cached.get("signature") == next_signature:
        payload = cached.get("payload")
        if isinstance(payload, DashboardContext):
            return payload

    payload = _build_dashboard_context_payload(runtime)
    compat_st.session_state["_dashboard_render_context"] = {"signature": next_signature, "payload": payload}
    return payload


__all__ = [
    "DashboardContext",
    "SidebarModel",
    "MapModel",
    "_ensure_session_defaults",
    "_resolve_data_source",
    "_build_dashboard_context_signature",
    "_build_dashboard_context_payload",
    "_build_sidebar_model",
    "_build_map_model",
    "_build_dashboard_context",
]
