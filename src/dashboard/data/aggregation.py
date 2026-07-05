from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

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
            "total_power": None,
            "total_emission": None,
            "median_price": None,
            "median_demand": None,
        }

    power_values = [
        float(item["power_value"])
        for item in values
        if item.get("power_value") is not None
    ]
    emission_values = [
        float(item["emission_value"])
        for item in values
        if item.get("emission_value") is not None
    ]
    price_values = [
        float(item["price_per_mwh"])
        for item in values
        if item.get("price_per_mwh") is not None
    ]
    demand_values = [
        float(item["demand_mw"]) for item in values if item.get("demand_mw") is not None
    ]

    return {
        "facility_count": len(values),
        "total_power": round(sum(power_values), 2) if power_values else None,
        "total_emission": round(sum(emission_values), 2) if emission_values else None,
        "median_price": round(float(pd.Series(price_values).median()), 2)
        if price_values
        else None,
        "median_demand": round(float(pd.Series(demand_values).median()), 2)
        if demand_values
        else None,
    }


def _filter_snapshot(
    snapshot: Dict[str, Dict[str, Any]], selected_fuel: str, selected_region: str
) -> Dict[str, Dict[str, Any]]:
    filtered: Dict[str, Dict[str, Any]] = {}
    for fac_code, record in snapshot.items():
        fuel_tokens = _extract_fuel_tokens(record.get("fuel_list"))
        fuel_match = selected_fuel == "All" or selected_fuel in fuel_tokens
        region_match = selected_region == "All" or selected_region == record.get(
            "state"
        )
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
        {
            "label": "Power Output MW",
            "value": _format_optional_metric(message.get("power_value"), "MW"),
        },
        {
            "label": "CO2 Emissions tCO2e",
            "value": _format_optional_metric(message.get("emission_value"), "tCO2e"),
        },
        {
            "label": "Price $/MWh",
            "value": _format_optional_metric(message.get("price_per_mwh"), "$/MWh"),
        },
        {
            "label": "Grid Demand MW",
            "value": _format_optional_metric(message.get("demand_mw"), "MW"),
        },
    ]


__all__ = [
    "_build_latest_snapshot",
    "_build_fuel_options",
    "_calculate_snapshot_stats",
    "_filter_snapshot",
    "_get_latest_trend_message",
    "_build_current_trend_cards",
]
