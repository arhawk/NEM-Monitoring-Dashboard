from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Dict, List, Literal

import pandas as pd

from ..settings import ENABLE_FALLBACK_REPLAY, FALLBACK_SAMPLE_PATH, FALLBACK_STALE_SECONDS
from .normalization import _normalize_message


@dataclass(frozen=True)
class DataSourceDecision:
    kind: Literal["live", "fallback", "empty", "stale_live_replaced"]
    messages: List[Dict[str, Any]]


def _should_use_fallback(runtime: Any) -> bool:
    if not ENABLE_FALLBACK_REPLAY:
        return False
    last_updated_at = runtime.cache.last_updated_at()
    if last_updated_at is None:
        return True
    return (time.time() - last_updated_at) > FALLBACK_STALE_SECONDS


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


def _resolve_dashboard_messages(
    live_messages: list[Dict[str, Any]],
    *,
    use_fallback: bool = False,
    fallback_messages: list[Dict[str, Any]] | None = None,
) -> DataSourceDecision:
    fallback_messages = fallback_messages or []
    data_source = _resolve_data_source(live_messages, use_fallback=use_fallback, fallback_messages=fallback_messages)
    if data_source == "fallback" and fallback_messages:
        return DataSourceDecision(kind="fallback", messages=fallback_messages)
    if data_source == "stale_live_replaced":
        return DataSourceDecision(kind="stale_live_replaced", messages=live_messages)
    if data_source == "fallback":
        return DataSourceDecision(kind="fallback", messages=[])
    if data_source == "live":
        return DataSourceDecision(kind="live", messages=live_messages)
    return DataSourceDecision(kind="empty", messages=[])


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


__all__ = [
    "DataSourceDecision",
    "_should_use_fallback",
    "_resolve_data_source",
    "_resolve_dashboard_messages",
    "_load_fallback_messages",
]
