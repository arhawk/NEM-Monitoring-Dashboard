from __future__ import annotations

from src.shared.config import (
    get_auto_start_cooldown_seconds,
    get_auto_start_publisher,
    get_enable_github_actions_control,
    get_github_owner,
    get_github_ref,
    get_github_repo,
    get_github_token,
    get_github_workflow_file,
    get_max_stream_rows,
    get_main_refresh_interval_seconds,
    get_mqtt_broker,
    get_mqtt_monitor_interval_seconds,
    get_mqtt_password,
    get_mqtt_port,
    get_mqtt_tls,
    get_mqtt_username,
    get_reset_interval_hours,
    get_sidebar_refresh_interval_seconds,
    get_subscribe_topic_filter,
)


BROKER = get_mqtt_broker()
PORT = get_mqtt_port()
SUBSCRIBE_TOPIC_FILTER = get_subscribe_topic_filter()
USERNAME = get_mqtt_username()
PASSWORD = get_mqtt_password()
MQTT_TLS = get_mqtt_tls()
MAX_STREAM_ROWS = get_max_stream_rows()
RESET_INTERVAL_HOURS = get_reset_interval_hours()
MAIN_REFRESH_INTERVAL_SECONDS = get_main_refresh_interval_seconds()
SIDEBAR_REFRESH_INTERVAL_SECONDS = get_sidebar_refresh_interval_seconds()
CONNECTION_TIMEOUT_SECONDS = 10
RECONNECT_COOLDOWN_SECONDS = 5
MONITOR_INTERVAL_SECONDS = get_mqtt_monitor_interval_seconds()
ENABLE_GITHUB_ACTIONS_CONTROL = get_enable_github_actions_control()
AUTO_START_PUBLISHER = get_auto_start_publisher()
AUTO_START_COOLDOWN_SECONDS = get_auto_start_cooldown_seconds()
GITHUB_TOKEN = get_github_token()
GITHUB_OWNER = get_github_owner()
GITHUB_REPO = get_github_repo()
GITHUB_WORKFLOW_FILE = get_github_workflow_file()
GITHUB_REF = get_github_ref()
DISPLAY_REGION_OPTIONS = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]
CACHE_FRESHNESS_STALE_AFTER_SECONDS = 3
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
