from __future__ import annotations

import os

from src.shared.mqtt_topics import MQTT_SUBSCRIBE_TOPIC_FILTER as DEFAULT_SUBSCRIBE_TOPIC_FILTER
from src.shared.stream_cache import (
    get_max_stream_rows,
    get_refresh_interval_seconds,
    get_reset_interval_hours,
)


BROKER = os.getenv("MQTT_BROKER") or os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT") or os.getenv("MQTT_BROKER_PORT", "1883"))
SUBSCRIBE_TOPIC_FILTER = os.getenv("MQTT_SUBSCRIBE_TOPIC_FILTER") or DEFAULT_SUBSCRIBE_TOPIC_FILTER
USERNAME = os.getenv("MQTT_USERNAME") or None
PASSWORD = os.getenv("MQTT_PASSWORD") or None
MQTT_TLS = os.getenv("MQTT_TLS", "false").strip().lower() in {"1", "true", "yes", "on"}
MAX_STREAM_ROWS = get_max_stream_rows()
RESET_INTERVAL_HOURS = get_reset_interval_hours()
REFRESH_INTERVAL_SECONDS = get_refresh_interval_seconds()
CONNECTION_TIMEOUT_SECONDS = 10
RECONNECT_COOLDOWN_SECONDS = 5
MONITOR_INTERVAL_SECONDS = max(1, int(os.getenv("MQTT_MONITOR_INTERVAL_SECONDS", "5")))
FALLBACK_SAMPLE_PATH = os.getenv("FALLBACK_SAMPLE_PATH", "data/data_for_publish.csv")
FALLBACK_STALE_SECONDS = max(1, int(os.getenv("FALLBACK_STALE_SECONDS", "30")))
ENABLE_FALLBACK_REPLAY = os.getenv("ENABLE_FALLBACK_REPLAY", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
DISPLAY_REGION_OPTIONS = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]
READY_NOTICE_SESSION_KEY = "_cache_ready_notice_pending"
SIDEBAR_HEADER_TITLE = "🔧 Control Center"
FUEL_GROUP_COLORS = {
    "Renewable": "#16a34a",
    "Fossil / Non-renewable": "#dc2626",
    "Storage": "#2563eb",
    "Mixed / Other": "#f59e0b",
}
RENEWABLE_FUEL_TOKENS = {
    "solar",
    "wind",
    "hydro",
    "biomass",
    "bagasse",
    "wood",
    "landfill gas",
}
FOSSIL_FUEL_TOKENS = {
    "coal",
    "black coal",
    "brown coal",
    "gas",
    "gas/diesel",
    "diesel",
    "kerosene",
    "liquid fuel",
    "coal seam methane",
    "waste coal mine gas",
}
STORAGE_FUEL_TOKENS = {"battery"}
