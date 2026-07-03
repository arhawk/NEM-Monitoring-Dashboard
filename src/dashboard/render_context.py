from __future__ import annotations

from typing import Any, Dict

from ._compat import st as compat_st
from . import runtime as runtime_module
from .settings import READY_NOTICE_SESSION_KEY
from .data import fallback as fallback_module
from .data.aggregation import (
    _build_fuel_options,
    _build_latest_snapshot,
    _calculate_snapshot_stats,
    _filter_snapshot,
)


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
    if use_fallback:
        if fallback_messages:
            return "fallback"
        if live_messages:
            return "stale_live_replaced"
        return "fallback"
    return "live" if live_messages else "empty"


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
        cache.messages_since_reset(),
        cache.size(),
        last_updated_at,
        last_reset_at,
        fallback_module._should_use_fallback(runtime),
    )


def _build_dashboard_context_payload(runtime: Any) -> Dict[str, Any]:
    live_messages = runtime.cache.get_recent_messages()
    use_fallback = fallback_module._should_use_fallback(runtime)
    fallback_messages = fallback_module._load_fallback_messages() if use_fallback else []
    messages = fallback_messages if use_fallback and fallback_messages else live_messages
    data_source = _resolve_data_source(live_messages, use_fallback=use_fallback, fallback_messages=fallback_messages)

    snapshot = _build_latest_snapshot(messages)
    fuel_options = _build_fuel_options(snapshot)
    if compat_st.session_state.get("selected_fuel") not in fuel_options:
        compat_st.session_state.selected_fuel = "All"
    filtered_snapshot = _filter_snapshot(snapshot, compat_st.session_state.selected_fuel, compat_st.session_state.selected_region)
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
    runtime = runtime_module.get_active_runtime()
    _ensure_session_defaults()
    next_signature = _build_dashboard_context_signature(runtime)
    cached = compat_st.session_state.get("_dashboard_render_context")
    if isinstance(cached, dict) and cached.get("signature") == next_signature:
        payload = cached.get("payload")
        if isinstance(payload, dict):
            return payload

    payload = _build_dashboard_context_payload(runtime)
    compat_st.session_state["_dashboard_render_context"] = {"signature": next_signature, "payload": payload}
    return payload


__all__ = [
    "_ensure_session_defaults",
    "_resolve_data_source",
    "_build_dashboard_context_signature",
    "_build_dashboard_context_payload",
    "_build_dashboard_context",
]
