from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .cache_snapshot import default_snapshot_path, resolve_snapshot_path
from .mqtt_topics import MQTT_PUBLISH_TOPIC_TEMPLATE, MQTT_SUBSCRIBE_TOPIC_FILTER
from .paths import cache_data_path, raw_data_path


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}

DEFAULT_MQTT_BROKER = "127.0.0.1"
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_TLS = False
DEFAULT_MQTT_SUBSCRIBE_TOPIC_FILTER = MQTT_SUBSCRIBE_TOPIC_FILTER
DEFAULT_MQTT_PUBLISH_TOPIC_TEMPLATE = MQTT_PUBLISH_TOPIC_TEMPLATE
DEFAULT_PUBLISH_DURATION_SECONDS = 0
DEFAULT_MAX_STREAM_ROWS = 5520
DEFAULT_RESET_INTERVAL_HOURS = 6.0
DEFAULT_MAIN_REFRESH_INTERVAL_SECONDS = 1
DEFAULT_SIDEBAR_REFRESH_INTERVAL_SECONDS = 1
DEFAULT_MQTT_MONITOR_INTERVAL_SECONDS = 5
DEFAULT_ENABLE_GITHUB_ACTIONS_CONTROL = False
DEFAULT_AUTO_START_PUBLISHER = False
DEFAULT_AUTO_START_COOLDOWN_SECONDS = 600
DEFAULT_GITHUB_OWNER = "arhawk"
DEFAULT_GITHUB_REPO = "NEM-Monitoring-Dashboard"
DEFAULT_GITHUB_WORKFLOW_FILE = "publish-mqtt-on-demand.yml"
DEFAULT_GITHUB_REF = "main"
DEFAULT_FACILITY_METADATA_DATA_DIR = raw_data_path("facility_metadata")
DEFAULT_FETCH_DATE_START = "2025-10-24T23:00:00"
DEFAULT_FETCH_DATE_END = "2025-10-31T22:59:59"
DEFAULT_STREAM_CACHE_SNAPSHOT_PATH = str(default_snapshot_path())
DEFAULT_STREAM_CACHE_PERSIST_EVERY_MESSAGES = 100
DEFAULT_ENABLE_LLM_ANALYTICS = False
DEFAULT_GOOGLE_AI_MODEL = "gemini-2.0-flash"
DEFAULT_LLM_MAX_ROWS = 5000
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_LLM_AUDIT_DIR = str(cache_data_path("llm_runs"))


def _read_env(name: str) -> Optional[str]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value if value else None


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if not normalized:
        return default
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def get_env_str(name: str, default: str | None = None) -> str | None:
    value = _read_env(name)
    return default if value is None else value


def get_env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw_value = _read_env(name)
    if raw_value is None:
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def get_env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw_value = _read_env(name)
    if raw_value is None:
        value = default
    else:
        try:
            value = float(raw_value)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def get_env_bool(name: str, default: bool = False) -> bool:
    return parse_bool(os.getenv(name), default=default)


def get_mqtt_broker() -> str:
    return (
        get_env_str("MQTT_BROKER")
        or get_env_str("MQTT_BROKER_HOST")
        or DEFAULT_MQTT_BROKER
    )


def get_mqtt_port() -> int:
    raw_port = get_env_str("MQTT_PORT") or get_env_str("MQTT_BROKER_PORT")
    if raw_port is None:
        return DEFAULT_MQTT_PORT
    try:
        return int(raw_port)
    except ValueError:
        return DEFAULT_MQTT_PORT


def get_mqtt_username() -> str | None:
    return get_env_str("MQTT_USERNAME")


def get_mqtt_password() -> str | None:
    return get_env_str("MQTT_PASSWORD")


def get_mqtt_tls() -> bool:
    return get_env_bool("MQTT_TLS", DEFAULT_MQTT_TLS)


def get_subscribe_topic_filter() -> str:
    return (
        get_env_str("MQTT_SUBSCRIBE_TOPIC_FILTER")
        or DEFAULT_MQTT_SUBSCRIBE_TOPIC_FILTER
    )


def get_publish_topic_template() -> str:
    return (
        get_env_str("MQTT_PUBLISH_TOPIC_TEMPLATE")
        or DEFAULT_MQTT_PUBLISH_TOPIC_TEMPLATE
    )


def get_publish_duration_seconds() -> int:
    return get_env_int(
        "PUBLISH_DURATION_SECONDS",
        DEFAULT_PUBLISH_DURATION_SECONDS,
        minimum=0,
    )


def get_max_stream_rows() -> int:
    return get_env_int("MAX_STREAM_ROWS", DEFAULT_MAX_STREAM_ROWS, minimum=1)


def get_reset_interval_hours() -> float:
    return get_env_float(
        "RESET_INTERVAL_HOURS",
        DEFAULT_RESET_INTERVAL_HOURS,
        minimum=0.0,
    )


def get_main_refresh_interval_seconds() -> int:
    return get_env_int(
        "MAIN_REFRESH_INTERVAL_SECONDS",
        DEFAULT_MAIN_REFRESH_INTERVAL_SECONDS,
        minimum=1,
    )


def get_sidebar_refresh_interval_seconds() -> int:
    return get_env_int(
        "SIDEBAR_REFRESH_INTERVAL_SECONDS",
        DEFAULT_SIDEBAR_REFRESH_INTERVAL_SECONDS,
        minimum=1,
    )


def get_mqtt_monitor_interval_seconds() -> int:
    return get_env_int(
        "MQTT_MONITOR_INTERVAL_SECONDS",
        DEFAULT_MQTT_MONITOR_INTERVAL_SECONDS,
        minimum=1,
    )


def get_enable_github_actions_control() -> bool:
    return get_env_bool(
        "ENABLE_GITHUB_ACTIONS_CONTROL",
        DEFAULT_ENABLE_GITHUB_ACTIONS_CONTROL,
    )


def get_auto_start_publisher() -> bool:
    return get_env_bool("AUTO_START_PUBLISHER", DEFAULT_AUTO_START_PUBLISHER)


def get_auto_start_cooldown_seconds() -> int:
    return get_env_int(
        "AUTO_START_COOLDOWN_SECONDS",
        DEFAULT_AUTO_START_COOLDOWN_SECONDS,
        minimum=0,
    )


def get_github_token() -> str | None:
    return get_env_str("GITHUB_TOKEN")


def get_github_owner() -> str:
    return get_env_str("GITHUB_OWNER") or DEFAULT_GITHUB_OWNER


def get_github_repo() -> str:
    return get_env_str("GITHUB_REPO") or DEFAULT_GITHUB_REPO


def get_github_workflow_file() -> str:
    return get_env_str("GITHUB_WORKFLOW_FILE") or DEFAULT_GITHUB_WORKFLOW_FILE


def get_github_ref() -> str:
    return get_env_str("GITHUB_REF") or DEFAULT_GITHUB_REF


def get_facility_metadata_data_dir() -> Path:
    raw_value = get_env_str("FACILITY_METADATA_DATA_DIR")
    return (
        Path(raw_value) if raw_value is not None else DEFAULT_FACILITY_METADATA_DATA_DIR
    )


def get_open_electricity_api_key() -> str:
    api_key = get_env_str("OPEN_ELECTRICITY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPEN_ELECTRICITY_API_KEY is required to fetch data from the Open Electricity API."
        )
    return api_key


def _parse_fetch_datetime(raw_value: str | None, default: datetime) -> datetime:
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    if not normalized:
        return default
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return default


def get_fetch_date_start() -> datetime:
    return _parse_fetch_datetime(
        get_env_str("FETCH_DATE_START"),
        datetime.fromisoformat(DEFAULT_FETCH_DATE_START),
    )


def get_fetch_date_end() -> datetime:
    return _parse_fetch_datetime(
        get_env_str("FETCH_DATE_END"),
        datetime.fromisoformat(DEFAULT_FETCH_DATE_END),
    )


def get_stream_cache_snapshot_path() -> Path | None:
    raw_value = get_env_str("STREAM_CACHE_SNAPSHOT_PATH")
    if raw_value is None:
        return default_snapshot_path()
    return resolve_snapshot_path(raw_value)


def get_stream_cache_persist_every_messages() -> int:
    return get_env_int(
        "STREAM_CACHE_PERSIST_EVERY_MESSAGES",
        DEFAULT_STREAM_CACHE_PERSIST_EVERY_MESSAGES,
        minimum=1,
    )


def get_enable_llm_analytics() -> bool:
    return get_env_bool("ENABLE_LLM_ANALYTICS", DEFAULT_ENABLE_LLM_ANALYTICS)


def get_google_ai_api_key() -> str:
    api_key = get_env_str("GOOGLE_AI_API_KEY") or get_env_str("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_AI_API_KEY is required for LLM analytics. "
            "Set ENABLE_LLM_ANALYTICS=true and provide a Google AI Studio API key."
        )
    return api_key


def get_google_ai_model() -> str:
    return get_env_str("GOOGLE_AI_MODEL") or DEFAULT_GOOGLE_AI_MODEL


def get_llm_max_rows() -> int:
    return get_env_int("LLM_MAX_ROWS", DEFAULT_LLM_MAX_ROWS, minimum=1)


def get_llm_request_timeout_seconds() -> int:
    return get_env_int(
        "LLM_REQUEST_TIMEOUT_SECONDS",
        DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        minimum=5,
    )


def get_llm_audit_dir() -> Path:
    raw_value = get_env_str("LLM_AUDIT_DIR")
    return Path(raw_value) if raw_value is not None else Path(DEFAULT_LLM_AUDIT_DIR)


__all__ = [
    "DEFAULT_AUTO_START_COOLDOWN_SECONDS",
    "DEFAULT_AUTO_START_PUBLISHER",
    "DEFAULT_ENABLE_GITHUB_ACTIONS_CONTROL",
    "DEFAULT_ENABLE_LLM_ANALYTICS",
    "DEFAULT_LLM_AUDIT_DIR",
    "DEFAULT_LLM_MAX_ROWS",
    "DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_GOOGLE_AI_MODEL",
    "DEFAULT_FACILITY_METADATA_DATA_DIR",
    "DEFAULT_FETCH_DATE_END",
    "DEFAULT_FETCH_DATE_START",
    "DEFAULT_STREAM_CACHE_PERSIST_EVERY_MESSAGES",
    "DEFAULT_STREAM_CACHE_SNAPSHOT_PATH",
    "DEFAULT_GITHUB_OWNER",
    "DEFAULT_GITHUB_REF",
    "DEFAULT_GITHUB_REPO",
    "DEFAULT_GITHUB_WORKFLOW_FILE",
    "DEFAULT_MAIN_REFRESH_INTERVAL_SECONDS",
    "DEFAULT_MAX_STREAM_ROWS",
    "DEFAULT_MQTT_BROKER",
    "DEFAULT_MQTT_MONITOR_INTERVAL_SECONDS",
    "DEFAULT_MQTT_PORT",
    "DEFAULT_MQTT_PUBLISH_TOPIC_TEMPLATE",
    "DEFAULT_MQTT_SUBSCRIBE_TOPIC_FILTER",
    "DEFAULT_MQTT_TLS",
    "DEFAULT_PUBLISH_DURATION_SECONDS",
    "DEFAULT_RESET_INTERVAL_HOURS",
    "DEFAULT_SIDEBAR_REFRESH_INTERVAL_SECONDS",
    "FALSE_VALUES",
    "TRUE_VALUES",
    "get_auto_start_cooldown_seconds",
    "get_auto_start_publisher",
    "get_enable_github_actions_control",
    "get_enable_llm_analytics",
    "get_env_bool",
    "get_env_float",
    "get_env_int",
    "get_env_str",
    "get_facility_metadata_data_dir",
    "get_fetch_date_end",
    "get_fetch_date_start",
    "get_github_owner",
    "get_github_ref",
    "get_github_repo",
    "get_github_token",
    "get_github_workflow_file",
    "get_google_ai_api_key",
    "get_google_ai_model",
    "get_llm_audit_dir",
    "get_llm_max_rows",
    "get_llm_request_timeout_seconds",
    "get_main_refresh_interval_seconds",
    "get_max_stream_rows",
    "get_mqtt_broker",
    "get_mqtt_monitor_interval_seconds",
    "get_mqtt_password",
    "get_mqtt_port",
    "get_mqtt_tls",
    "get_mqtt_username",
    "get_open_electricity_api_key",
    "get_publish_duration_seconds",
    "get_publish_topic_template",
    "get_reset_interval_hours",
    "get_sidebar_refresh_interval_seconds",
    "get_stream_cache_persist_every_messages",
    "get_stream_cache_snapshot_path",
    "get_subscribe_topic_filter",
    "parse_bool",
]
