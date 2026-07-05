from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .mqtt_topics import MQTT_PUBLISH_TOPIC_TEMPLATE, MQTT_SUBSCRIBE_TOPIC_FILTER
from .paths import raw_data_path


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
    return Path(raw_value) if raw_value is not None else DEFAULT_FACILITY_METADATA_DATA_DIR


def get_open_electricity_api_key() -> str:
    api_key = get_env_str("OPEN_ELECTRICITY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPEN_ELECTRICITY_API_KEY is required to fetch data from the Open Electricity API."
        )
    return api_key


__all__ = [
    "DEFAULT_AUTO_START_COOLDOWN_SECONDS",
    "DEFAULT_AUTO_START_PUBLISHER",
    "DEFAULT_ENABLE_GITHUB_ACTIONS_CONTROL",
    "DEFAULT_FACILITY_METADATA_DATA_DIR",
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
    "get_env_bool",
    "get_env_float",
    "get_env_int",
    "get_env_str",
    "get_facility_metadata_data_dir",
    "get_github_owner",
    "get_github_ref",
    "get_github_repo",
    "get_github_token",
    "get_github_workflow_file",
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
    "get_subscribe_topic_filter",
    "parse_bool",
]
