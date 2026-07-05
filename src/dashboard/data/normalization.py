from __future__ import annotations

import ast
import math
from datetime import datetime
from typing import Any, Dict, List, Optional


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


def _classify_fuel_group(fuel_list: Any) -> str:
    from ..settings import (
        FOSSIL_FUEL_TOKENS,
        RENEWABLE_FUEL_TOKENS,
        STORAGE_FUEL_TOKENS,
    )

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


__all__ = [
    "_coerce_float",
    "_format_ts",
    "_reason_is_success",
    "_format_optional_metric",
    "_signature_metric_value",
    "_extract_fuel_tokens",
    "_classify_fuel_group",
    "_normalize_message",
]
