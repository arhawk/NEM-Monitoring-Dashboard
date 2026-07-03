from __future__ import annotations

import time
from typing import Any, Dict, List

import pandas as pd

from ..settings import ENABLE_FALLBACK_REPLAY, FALLBACK_SAMPLE_PATH, FALLBACK_STALE_SECONDS
from .normalization import _normalize_message


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


__all__ = ["_should_use_fallback", "_load_fallback_messages"]
