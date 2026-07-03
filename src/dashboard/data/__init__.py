from __future__ import annotations

import ast
import math
import time

import pandas as pd

from .aggregation import (
    _build_current_trend_cards,
    _build_dashboard_context,
    _build_dashboard_context_payload,
    _build_dashboard_context_signature,
    _build_fuel_options,
    _build_latest_snapshot,
    _calculate_snapshot_stats,
    _ensure_session_defaults,
    _filter_snapshot,
    _get_latest_trend_message,
    _resolve_data_source,
)
from .fallback import _load_fallback_messages, _should_use_fallback
from .normalization import (
    _classify_fuel_group,
    _coerce_float,
    _format_optional_metric,
    _format_ts,
    _normalize_message,
    _reason_is_success,
    _signature_metric_value,
    _extract_fuel_tokens,
)


__all__ = [
    "ast",
    "math",
    "pd",
    "time",
    "FALLBACK_STALE_SECONDS",
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
    "_build_dashboard_context",
    "_ensure_session_defaults",
    "_build_dashboard_context_signature",
    "_build_dashboard_context_payload",
]

from ..settings import FALLBACK_STALE_SECONDS
