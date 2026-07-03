from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from .._compat import st as compat_st
from . import fallback as fallback_module
from .normalization import (
    _format_optional_metric,
    _extract_fuel_tokens,
)


def _build_latest_snapshot(messages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    snapshot: Dict[str, Dict[str, Any]] = {}
    for message in messages:
        fac_code = message.get("facility_code")
        if fac_code:
            snapshot[str(fac_code)] = message
    return snapshot


def _build_fuel_options(snapshot: Dict[str, Dict[str, Any]]) -> List[str]:
    fuel_types = {
        token
        for record in snapshot.values()
        for token in _extract_fuel_tokens(record.get("fuel_list"))
    }
    return ["All", *sorted(fuel_types, key=str.casefold)]


def _calculate_snapshot_stats(snapshot: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    values = list(snapshot.values())
    if not values:
        return {
            "facility_count": 0,
            "total_power": 0.0,
            "total_emission": None,
            "median_price": None,
            "median_demand": None,
        }

    power_values = [float(item["power_value"]) for item in values if item.get("power_value") is not None]
    emission_values = [float(item["emission_value"]) for item in values if item.get("emission_value") is not None]
    price_values = [float(item["price_per_mwh"]) for item in values if item.get("price_per_mwh") is not None]
    demand_values = [float(item["demand_mw"]) for item in values if item.get("demand_mw") is not None]

    return {
        "facility_count": len(values),
        "total_power": round(sum(power_values), 2) if power_values else 0.0,
        "total_emission": round(sum(emission_values), 2) if emission_values else None,
        "median_price": round(float(pd.Series(price_values).median()), 2) if price_values else None,
        "median_demand": round(float(pd.Series(demand_values).median()), 2) if demand_values else None,
    }


def _filter_snapshot(snapshot: Dict[str, Dict[str, Any]], selected_fuel: str, selected_region: str) -> Dict[str, Dict[str, Any]]:
    filtered: Dict[str, Dict[str, Any]] = {}
    for fac_code, record in snapshot.items():
        fuel_tokens = _extract_fuel_tokens(record.get("fuel_list"))
        fuel_match = selected_fuel == "All" or selected_fuel in fuel_tokens
        region_match = selected_region == "All" or selected_region == record.get("state")
        if fuel_match and region_match:
            filtered[fac_code] = record
    return filtered


def _get_latest_trend_message(messages: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("facility_code"):
            return message
    return None


def _build_current_trend_cards(message: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"label": "Power Output MW", "value": _format_optional_metric(message.get("power_value"), "MW")},
        {"label": "CO2 Emissions tCO2e", "value": _format_optional_metric(message.get("emission_value"), "tCO2e")},
        {"label": "Price $/MWh", "value": _format_optional_metric(message.get("price_per_mwh"), "$/MWh")},
        {"label": "Grid Demand MW", "value": _format_optional_metric(message.get("demand_mw"), "MW")},
    ]


def _resolve_data_source(
    live_messages: List[Dict[str, Any]],
    *,
    use_fallback: bool = False,
    fallback_messages: List[Dict[str, Any]] | None = None,
) -> str:
    if use_fallback:
        if fallback_messages:
            return "fallback"
        if live_messages:
            return "stale_live_replaced"
        return "fallback"
    return "live" if live_messages else "empty"


def _ensure_session_defaults() -> None:
    if "display_mode" not in compat_st.session_state:
        compat_st.session_state.display_mode = "power_value"
    if "selected_fuel" not in compat_st.session_state:
        compat_st.session_state.selected_fuel = "All"
    if "selected_region" not in compat_st.session_state:
        compat_st.session_state.selected_region = "All"
    from ..settings import READY_NOTICE_SESSION_KEY

    if READY_NOTICE_SESSION_KEY not in compat_st.session_state:
        compat_st.session_state[READY_NOTICE_SESSION_KEY] = False


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
    from ..runtime import get_active_runtime

    runtime = get_active_runtime()
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
    "_build_latest_snapshot",
    "_build_fuel_options",
    "_calculate_snapshot_stats",
    "_filter_snapshot",
    "_get_latest_trend_message",
    "_build_current_trend_cards",
    "_resolve_data_source",
    "_ensure_session_defaults",
    "_build_dashboard_context_signature",
    "_build_dashboard_context_payload",
    "_build_dashboard_context",
]
