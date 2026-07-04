from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal


@dataclass(frozen=True)
class DataSourceDecision:
    kind: Literal["live", "empty"]
    messages: List[Dict[str, Any]]


def _resolve_data_source(
    live_messages: list[Dict[str, Any]],
) -> str:
    return "live" if live_messages else "empty"


def _resolve_dashboard_messages(
    live_messages: list[Dict[str, Any]],
) -> DataSourceDecision:
    data_source = _resolve_data_source(live_messages)
    if data_source == "live":
        return DataSourceDecision(kind="live", messages=live_messages)
    return DataSourceDecision(kind="empty", messages=[])


__all__ = [
    "DataSourceDecision",
    "_resolve_data_source",
    "_resolve_dashboard_messages",
]
