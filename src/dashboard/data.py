from __future__ import annotations

import ast
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from .settings import ENABLE_FALLBACK_REPLAY, FALLBACK_SAMPLE_PATH, FALLBACK_STALE_SECONDS, FUEL_GROUP_COLORS, RENEWABLE_FUEL_TOKENS, FOSSIL_FUEL_TOKENS, STORAGE_FUEL_TOKENS


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(coerced):
        return None
    return coerced


def _format_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "Never"
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _reason_is_success(reason_code: Any) -> bool:
    if reason_code is None:
        return True
    if hasattr(reason_code, "is_failure"):
        return not reason_code.is_failure
    try:
        return int(reason_code) == 0
    except (TypeError, ValueError):
        return str(reason_code).strip().lower() in {"0", "success"}


def _format_optional_metric(value: Any, unit: str = "") -> str:
    coerced = _coerce_float(value)
    if coerced is None:
        return "N/A"
    text = f"{round(coerced, 2)}"
    return f"{text} {unit}".strip()


def _signature_metric_value(value: Any) -> Optional[float]:
    coerced = _coerce_float(value)
    if coerced is None:
        return None
    return round(coerced, 2)


def _extract_fuel_tokens(fuel_list: Any) -> List[str]:
    if fuel_list is None:
        return []
    if isinstance(fuel_list, (list, tuple, set)):
        return [str(token).strip() for token in fuel_list if str(token).strip()]

    fuel_text = str(fuel_list).strip()
    if not fuel_text:
        return []

    try:
        parsed = ast.literal_eval(fuel_text)
    except (ValueError, SyntaxError):
        return [fuel_text]

    if isinstance(parsed, (list, tuple, set)):
        return [str(token).strip() for token in parsed if str(token).strip()]
    parsed_text = str(parsed).strip()
    return [parsed_text] if parsed_text else []


def _build_fuel_options(snapshot: Dict[str, Dict[str, Any]]) -> List[str]:
    fuel_types = {
        token
        for record in snapshot.values()
        for token in _extract_fuel_tokens(record.get("fuel_list"))
    }
    return ["All", *sorted(fuel_types, key=str.casefold)]


def _classify_fuel_group(fuel_list: Any) -> str:
    tokens = _extract_fuel_tokens(fuel_list)
    if not tokens:
        return "Mixed / Other"

    normalized = {token.casefold() for token in tokens}
    group_matches = []

    if normalized <= RENEWABLE_FUEL_TOKENS:
        group_matches.append("Renewable")
    if normalized <= FOSSIL_FUEL_TOKENS:
        group_matches.append("Fossil / Non-renewable")
    if normalized <= STORAGE_FUEL_TOKENS:
        group_matches.append("Storage")

    if len(group_matches) == 1:
        return group_matches[0]
    return "Mixed / Other"


def _normalize_message(payload: Dict[str, Any], topic: str) -> Optional[Dict[str, Any]]:
    fac_code = str(payload.get("facility_code") or "").strip()
    lat = _coerce_float(payload.get("lat"))
    lng = _coerce_float(payload.get("lng"))
    power_val = _coerce_float(payload.get("power_value"))

    if not fac_code or lat is None or lng is None or power_val is None:
        return None

    record = {
        "facility_code": fac_code,
        "facility_name": payload.get("facility_name") or fac_code,
        "lat": lat,
        "lng": lng,
        "timestamp": payload.get("timestamp") or "",
        "power_value": round(power_val, 2),
        "emission_value": _signature_metric_value(payload.get("emission_value")),
        "price_per_mwh": _signature_metric_value(payload.get("price_per_mwh")),
        "demand_mw": _signature_metric_value(payload.get("demand_mw")),
        "state": payload.get("state") or "Unknown Region",
        "fuel_list": payload.get("fuel_list") or "Unknown",
        "fuel_group": _classify_fuel_group(payload.get("fuel_list")),
        "topic": topic,
    }
    return record


def _build_latest_snapshot(messages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    snapshot: Dict[str, Dict[str, Any]] = {}
    for message in messages:
        fac_code = message.get("facility_code")
        if fac_code:
            snapshot[str(fac_code)] = message
    return snapshot


def _should_use_fallback(runtime: Any) -> bool:
    if not ENABLE_FALLBACK_REPLAY:
        return False
    last_updated_at = runtime.cache.last_updated_at()
    if last_updated_at is None:
        return True
    return (time.time() - last_updated_at) > FALLBACK_STALE_SECONDS


def _load_fallback_messages(limit: int = 200) -> List[Dict[str, Any]]:
    sample_path = FALLBACK_SAMPLE_PATH.strip()
    if not sample_path:
        return []

    try:
        df = pd.read_csv(sample_path)
    except (FileNotFoundError, OSError, pd.errors.EmptyDataError):
        return []

    if df.empty:
        return []

    rows = df.tail(max(1, limit)).to_dict("records")
    fallback_messages: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        payload = {
            "facility_code": row.get("facility_code"),
            "facility_name": row.get("facility_name"),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
            "timestamp": row.get("timestamp"),
            "power_value": row.get("power_value", row.get("Power (MW)")),
            "emission_value": row.get("emission_value", row.get("Emissions (tonnes)")),
            "price_per_mwh": row.get("price_per_mwh", row.get("Price ($/MWh)")),
            "demand_mw": row.get("demand_mw", row.get("Demand (MW)")),
            "state": row.get("state"),
            "fuel_list": row.get("fuel_list"),
        }
        record = _normalize_message(payload, "fallback/sample_replay")
        if record is None:
            continue
        record["received_at"] = float(index + 1)
        record["received_at_iso"] = str(record.get("timestamp") or "")
        fallback_messages.append(record)
    return fallback_messages


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


def _get_latest_trend_message(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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


__all__ = [
    "ast",
    "pd",
    "math",
    "time",
    "_coerce_float",
    "_format_ts",
    "_reason_is_success",
    "_format_optional_metric",
    "_signature_metric_value",
    "_extract_fuel_tokens",
    "_build_fuel_options",
    "_classify_fuel_group",
    "_normalize_message",
    "_build_latest_snapshot",
    "_should_use_fallback",
    "_load_fallback_messages",
    "_resolve_data_source",
    "_calculate_snapshot_stats",
    "_filter_snapshot",
    "_get_latest_trend_message",
    "_build_current_trend_cards",
]
