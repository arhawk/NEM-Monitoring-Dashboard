from __future__ import annotations

import json
import os
import time
import html
import textwrap
import ast
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st
import streamlit.components.v1 as components

from src.nem_map_component import render_nem_facility_map
from src.stream_cache import (
    StreamCache,
    get_max_stream_rows,
    get_refresh_interval_seconds,
    get_reset_interval_hours,
)


st.set_page_config(page_title="NEM Facility Real-time Monitoring Dashboard", layout="wide")

BROKER = os.getenv("MQTT_BROKER") or os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT") or os.getenv("MQTT_BROKER_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "comp5339/task123/measurements/#")
USERNAME = os.getenv("MQTT_USERNAME") or None
PASSWORD = os.getenv("MQTT_PASSWORD") or None
MAX_STREAM_ROWS = get_max_stream_rows()
RESET_INTERVAL_HOURS = get_reset_interval_hours()
REFRESH_INTERVAL_SECONDS = get_refresh_interval_seconds()
CONNECTION_TIMEOUT_SECONDS = 10
RECONNECT_COOLDOWN_SECONDS = 5
FALLBACK_SAMPLE_PATH = os.getenv("FALLBACK_SAMPLE_PATH", "data/data_for_publish.csv")
FALLBACK_STALE_SECONDS = max(1, int(os.getenv("FALLBACK_STALE_SECONDS", "30")))
ENABLE_FALLBACK_REPLAY = os.getenv("ENABLE_FALLBACK_REPLAY", "true").strip().lower() not in {"0", "false", "no", "off"}
DISPLAY_REGION_OPTIONS = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]
READY_NOTICE_SESSION_KEY = "_cache_ready_notice_pending"
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


def _build_fuel_options(snapshot: Dict[str, Dict[str, Any]]) -> List[str]:
    fuel_types = {
        token
        for record in snapshot.values()
        for token in _extract_fuel_tokens(record.get("fuel_list"))
    }
    return ["All", *sorted(fuel_types, key=str.casefold)]


def _classify_fuel_group(fuel_list: Any) -> str:
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


def _marker_color(fuel_list: Any) -> str:
    if fuel_list in FUEL_GROUP_COLORS:
        return FUEL_GROUP_COLORS[str(fuel_list)]
    return FUEL_GROUP_COLORS[_classify_fuel_group(fuel_list)]


def _marker_radius(info: Dict[str, Any], display_mode: str) -> float:
    value = _signature_metric_value(info.get(display_mode))
    if value is None:
        return 6.0
    return max(5.5, min(16.0, 6.0 + abs(value) ** 0.5))


def _marker_tooltip_text(info: Dict[str, Any], fac_code: str, display_mode: str) -> str:
    value = info.get(display_mode)
    unit = "MW" if display_mode == "power_value" else "tCO2e"
    label = "Power" if display_mode == "power_value" else "Emissions"
    return f"{info.get('facility_name', fac_code)} | {label}: {_format_optional_metric(value, unit)}"


def _marker_popup_html(info: Dict[str, Any], fac_code: str) -> str:
    popup = f"""
    <b>{html.escape(str(info.get('facility_name', fac_code)))}</b><br>
    Facility Code: {html.escape(str(fac_code))}<br>
    Region: {html.escape(str(info.get('state', 'Unknown Region')))}<br>
    Fuel Group: {html.escape(str(info.get('fuel_group', _classify_fuel_group(info.get('fuel_list')))))}<br>
    Fuel Type: {html.escape(str(info.get('fuel_list', 'Unknown')))}<br>
    Last Payload Time: {html.escape(str(info.get('timestamp', 'Unknown')))}<br>
    Power Output: {_format_optional_metric(info.get('power_value'), 'MW')}<br>
    CO2 Emissions: {_format_optional_metric(info.get('emission_value'), 'tCO2e')}<br>
    Current Price: {_format_optional_metric(info.get('price_per_mwh'), '$/MWh')}<br>
    Grid Demand: {_format_optional_metric(info.get('demand_mw'), 'MW')}
    """
    return " ".join(popup.split())


def _marker_fingerprint(info: Dict[str, Any], display_mode: str) -> tuple:
    return (
        _signature_metric_value(info.get("power_value")),
        _signature_metric_value(info.get("emission_value")),
        _signature_metric_value(info.get("price_per_mwh")),
        _signature_metric_value(info.get("demand_mw")),
        str(info.get("timestamp", "")),
    )


def _build_static_signature(records: Dict[str, Dict[str, Any]]) -> tuple:
    return tuple(
        sorted(
            (
                fac_code,
                round(lat, 5),
                round(lng, 5),
                str(info.get("state", "")),
                str(info.get("fuel_list", "")),
                str(info.get("facility_name", fac_code)),
            )
            for fac_code, info in records.items()
            if (lat := _coerce_float(info.get("lat"))) is not None
            and (lng := _coerce_float(info.get("lng"))) is not None
        )
    )


def _build_operational_signature(records: Dict[str, Dict[str, Any]]) -> tuple:
    return tuple(
        sorted(
            (
                fac_code,
                str(info.get("timestamp", "")),
                _signature_metric_value(info.get("power_value")),
                _signature_metric_value(info.get("emission_value")),
                _signature_metric_value(info.get("price_per_mwh")),
                _signature_metric_value(info.get("demand_mw")),
            )
            for fac_code, info in records.items()
            if _coerce_float(info.get("lat")) is not None and _coerce_float(info.get("lng")) is not None
        )
    )


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


def _build_latest_snapshot(messages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    snapshot: Dict[str, Dict[str, Any]] = {}
    for message in messages:
        fac_code = message.get("facility_code")
        if fac_code:
            snapshot[str(fac_code)] = message
    return snapshot


def _fallback_enabled() -> bool:
    return ENABLE_FALLBACK_REPLAY


def _should_use_fallback(runtime: "DashboardRuntime") -> bool:
    if not _fallback_enabled():
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


def _resolve_data_source(
    live_messages: List[Dict[str, Any]],
    fallback_messages: List[Dict[str, Any]],
) -> str:
    if live_messages:
        return "live"
    return "fallback"


def _calculate_snapshot_stats(snapshot: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    values = list(snapshot.values())
    if not values:
        return {
            "facility_count": 0,
            "total_power": 0.0,
            "total_emission": None,
            "median_price": None,
            "median_demand": None,
        }

    power_values = [float(item["power_value"]) for item in values if item.get("power_value") is not None]
    emission_values = [float(item["emission_value"]) for item in values if item.get("emission_value") is not None]
    price_values = [float(item["price_per_mwh"]) for item in values if item.get("price_per_mwh") is not None]
    demand_values = [float(item["demand_mw"]) for item in values if item.get("demand_mw") is not None]

    return {
        "facility_count": len(values),
        "total_power": round(sum(power_values), 2) if power_values else 0.0,
        "total_emission": round(sum(emission_values), 2) if emission_values else None,
        "median_price": round(float(pd.Series(price_values).median()), 2) if price_values else None,
        "median_demand": round(float(pd.Series(demand_values).median()), 2) if demand_values else None,
    }


def _filter_snapshot(
    snapshot: Dict[str, Dict[str, Any]],
    selected_fuel: str,
    selected_region: str,
) -> Dict[str, Dict[str, Any]]:
    filtered: Dict[str, Dict[str, Any]] = {}
    for fac_code, record in snapshot.items():
        fuel_tokens = _extract_fuel_tokens(record.get("fuel_list"))
        fuel_match = selected_fuel == "All" or selected_fuel in fuel_tokens
        region_match = selected_region == "All" or selected_region == record.get("state")
        if fuel_match and region_match:
            filtered[fac_code] = record
    return filtered


def _build_map_signature(
    records: Dict[str, Dict[str, Any]],
    display_mode: str,
    selected_fuel: str,
    selected_region: str,
) -> tuple:
    return (_build_static_signature(records), (display_mode, selected_fuel, selected_region, _build_operational_signature(records)))


def _build_marker_payload(
    records: Dict[str, Dict[str, Any]],
    display_mode: str,
    selected_fuel: str,
    selected_region: str,
) -> Dict[str, Any]:
    markers = []
    for fac_code, info in sorted(records.items()):
        lat = _coerce_float(info.get("lat"))
        lng = _coerce_float(info.get("lng"))
        if lat is None or lng is None:
            continue
        markers.append(
            {
                "facility_code": fac_code,
                "facility_name": info.get("facility_name", fac_code),
                "lat": lat,
                "lng": lng,
                "fuel_group": info.get("fuel_group") or _classify_fuel_group(info.get("fuel_list")),
                "color": _marker_color(info.get("fuel_group") or info.get("fuel_list")),
                "radius": round(_marker_radius(info, display_mode), 2),
                "tooltip": _marker_tooltip_text(info, fac_code, display_mode),
                "popup_html": _marker_popup_html(info, fac_code),
                "fingerprint": _marker_fingerprint(info, display_mode),
                "power_value": _signature_metric_value(info.get("power_value")),
                "emission_value": _signature_metric_value(info.get("emission_value")),
            }
        )

    return {
        "static_signature": _build_static_signature(records),
        "operational_signature": _build_operational_signature(records),
        "display_mode": display_mode,
        "selected_fuel": selected_fuel,
        "selected_region": selected_region,
        "legend": [
            {"label": label, "color": color}
            for label, color in FUEL_GROUP_COLORS.items()
        ],
        "markers": markers,
    }


def _get_latest_trend_message(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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


def _build_current_trend_html(message: Dict[str, Any]) -> str:
    facility_name = html.escape(str(message.get("facility_name") or message.get("facility_code") or "Unknown Facility"))
    facility_code = html.escape(str(message.get("facility_code") or ""))
    timestamp = html.escape(str(message.get("timestamp") or ""))
    details = " | ".join(part for part in (facility_code, timestamp) if part)
    cards = _build_current_trend_cards(message)
    card_items = []
    for card in cards:
        card_items.append(
            f"""
            <div style="
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 12px;
                min-width: 0;
            ">
              <div style="font-size: 0.74rem; color: #64748b; font-weight: 600; line-height: 1.2; margin-bottom: 4px;">
                {html.escape(card["label"])}
              </div>
              <div style="font-size: 0.96rem; color: #0f172a; font-weight: 700; line-height: 1.2;">
                {html.escape(card["value"])}
              </div>
            </div>
            """
        )

    detail_html = f'<div style="font-size: 0.8rem; color: #64748b; margin-top: 4px;">{details}</div>' if details else ""
    return textwrap.dedent(
        f"""
        <div style="
            border: 1px solid #dbe4ee;
            border-radius: 14px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding: 12px 14px 14px 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            margin-top: 2px;
        ">
          <div style="font-size: 0.92rem; color: #0f172a; font-weight: 700; line-height: 1.2;">
            Current Facility: {facility_name}
          </div>
          {detail_html}
          <div style="
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
          ">
            {''.join(card_items)}
          </div>
        </div>
        """
    ).strip()


def _render_current_trend(messages: List[Dict[str, Any]]) -> None:
    latest = _get_latest_trend_message(messages)
    if latest is None:
        st.subheader("Current Facility")
        st.info("No MQTT messages available for current trend yet.")
        return

    components.html(_build_current_trend_html(latest), height=220, scrolling=False)


class DashboardRuntime:
    def __init__(self) -> None:
        self.cache = StreamCache(maxlen=MAX_STREAM_ROWS)
        self.client: Optional[mqtt.Client] = None
        self.status = "Connecting"
        self.last_error: Optional[str] = None
        self.started_at = time.monotonic()
        self.last_soft_reset_at = datetime.now(timezone.utc)
        self._last_connect_attempt_at = 0.0
        self._last_status_change_at = time.monotonic()
        self._connected_once = False
        self._build_client()
        if self.client is not None:
            self.client.loop_start()
        self._schedule_connect(initial=True)

    def _build_client(self) -> None:
        self.client = mqtt.Client(
            client_id="nem-facility-monitor-dashboard",
            clean_session=True,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if USERNAME:
            self.client.username_pw_set(USERNAME, PASSWORD)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        if hasattr(self.client, "on_connect_fail"):
            self.client.on_connect_fail = self._on_connect_fail
        self.client.on_message = self._on_message

    def _set_status(self, status: str, error: Optional[str] = None) -> None:
        if self.status != status:
            self._last_status_change_at = time.monotonic()
        self.status = status
        self.last_error = error

    def _schedule_connect(self, initial: bool = False) -> None:
        if self.client is None:
            return
        try:
            self._last_connect_attempt_at = time.monotonic()
            self._set_status("Connecting", None)
            self.client.connect_async(BROKER, PORT, keepalive=60)
        except Exception as exc:
            self._set_status("Error", f"MQTT connect failed: {exc}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if _reason_is_success(reason_code):
            self._connected_once = True
            self.cache.set_last_error(None)
            self._set_status("Connected", None)
            try:
                client.subscribe(TOPIC, qos=0)
            except Exception as exc:
                self._set_status("Error", f"Subscription failed: {exc}")
        else:
            self._set_status("Error", f"MQTT connection rejected: {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        if _reason_is_success(reason_code):
            self._set_status("Disconnected", None)
        else:
            self._set_status("Disconnected", f"MQTT disconnected: {reason_code}")

    def _on_connect_fail(self, client, userdata) -> None:
        self._set_status("Error", "MQTT connection failed")

    def _on_message(self, client, userdata, msg, properties=None) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            record = _normalize_message(payload, msg.topic)
            if record is None:
                return
            self.cache.add_message(record)
            self.cache.set_last_error(None)
        except Exception as exc:
            self.cache.set_last_error(str(exc))
            self.last_error = f"Message processing failed: {exc}"

    def refresh_connection_state(self) -> None:
        if self.status == "Connecting" and (time.monotonic() - self._last_connect_attempt_at) > CONNECTION_TIMEOUT_SECONDS:
            self._set_status("Disconnected", "MQTT connection timed out")

    def ensure_connection(self) -> None:
        self.refresh_connection_state()
        if self.status == "Connected":
            return
        if (time.monotonic() - self._last_connect_attempt_at) < RECONNECT_COOLDOWN_SECONDS:
            return
        self._schedule_connect(initial=False)

    def maybe_soft_reset(self) -> bool:
        if RESET_INTERVAL_HOURS <= 0:
            return False
        if self.cache.uptime_seconds() < (RESET_INTERVAL_HOURS * 3600):
            return False
        current_status = self.status
        self.cache.clear()
        self.last_soft_reset_at = datetime.now(timezone.utc)
        self.last_error = None
        self.cache.set_last_error(None)
        if current_status != "Connected":
            self._set_status("Connecting", None)
            self._schedule_connect(initial=False)
        return True


@st.cache_resource(show_spinner=False)
def get_runtime() -> DashboardRuntime:
    return DashboardRuntime()


def _ensure_session_defaults() -> None:
    if "display_mode" not in st.session_state:
        st.session_state.display_mode = "power_value"
    if "selected_fuel" not in st.session_state:
        st.session_state.selected_fuel = "All"
    if "selected_region" not in st.session_state:
        st.session_state.selected_region = "All"
    if READY_NOTICE_SESSION_KEY not in st.session_state:
        st.session_state[READY_NOTICE_SESSION_KEY] = False


def _render_header(
    runtime: DashboardRuntime,
    stats: Dict[str, Any],
    snapshot: Dict[str, Dict[str, Any]],
) -> None:
    st.title("⚡ National Electricity Market (NEM) Facility Real-time Monitoring Dashboard")
    st.caption("Live MQTT stream with bounded in-memory cache. No live CSV storage is used.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Power Output MW", f"{stats['total_power']}")
    with col2:
        st.metric("Total CO2 Emissions tCO2e", _format_optional_metric(stats["total_emission"], "tCO2e"))
    with col3:
        st.metric("Median Price $/MWh", _format_optional_metric(stats["median_price"], "$/MWh"))
    with col4:
        st.metric("Median Grid Demand MW", _format_optional_metric(stats["median_demand"], "MW"))


def _render_sidebar(
    runtime: DashboardRuntime,
    snapshot: Dict[str, Dict[str, Any]],
    filtered_snapshot: Dict[str, Dict[str, Any]],
    data_source: str,
    fuel_options: List[str],
) -> None:
    st.header("🔧 Control Center")
    st.subheader("MQTT Status")
    if runtime.status == "Connected":
        st.success("Connected")
    elif runtime.status == "Connecting":
        st.info("Connecting")
    elif runtime.status == "Disconnected":
        st.warning("Disconnected")
    else:
        st.error("Error")
    st.write(f"Cache size: {runtime.cache.size()} / {runtime.cache.max_size()}")
    st.write(f"Last soft reset: {_format_ts(runtime.cache.last_reset_at())}")
    if runtime.last_error:
        st.caption(runtime.last_error)

    if data_source == "fallback":
        st.info("Waiting for cache messages. Showing sample replay fallback.")
        st.session_state[READY_NOTICE_SESSION_KEY] = True
    elif st.session_state.get(READY_NOTICE_SESSION_KEY):
        st.success("Real-time data ready")
        st.session_state[READY_NOTICE_SESSION_KEY] = False

    st.subheader("Fuel Type Filter")
    if st.session_state.get("selected_fuel") not in fuel_options:
        st.session_state.selected_fuel = "All"
    st.selectbox("Select Fuel Type", fuel_options, key="selected_fuel")

    st.subheader("Grid Region Filter")
    st.selectbox("Select Region", DISPLAY_REGION_OPTIONS, key="selected_region")

    st.subheader("Data Statistics")
    st.write(f"Facilities in snapshot: {len(snapshot)}")
    st.write(f"Filtered Facilities: {len(filtered_snapshot)}")
    st.write(f"Messages since reset: {runtime.cache.messages_since_reset()}")

    st.subheader("Latest message")
    latest = runtime.cache.get_latest_message()
    if latest:
        st.json(
            {
                "facility_code": latest.get("facility_code"),
                "facility_name": latest.get("facility_name"),
                "state": latest.get("state"),
                "fuel_list": latest.get("fuel_list"),
                "fuel_group": latest.get("fuel_group"),
                "timestamp": latest.get("timestamp"),
                "received_at": latest.get("received_at_iso"),
            }
        )
        st.caption(f"Timestamp: {_format_ts(runtime.cache.last_updated_at())}")
    else:
        st.write("No MQTT messages have arrived yet.")


def _render_table(filtered_snapshot: Dict[str, Dict[str, Any]]) -> None:
    st.subheader("Facility Data Preview")
    if not filtered_snapshot:
        st.info("No matching records in the current cache.")
        return
    preview = pd.DataFrame(filtered_snapshot.values())
    cols = [
        "facility_code",
        "facility_name",
        "state",
        "fuel_group",
        "fuel_list",
        "power_value",
        "emission_value",
        "price_per_mwh",
        "demand_mw",
        "timestamp",
    ]
    existing = [col for col in cols if col in preview.columns]
    st.dataframe(preview[existing].sort_values("facility_code"), width="stretch", height=260)


def _render_map(filtered_snapshot: Dict[str, Dict[str, Any]], display_mode: str) -> None:
    st.subheader("Facility Map")
    st.caption("Green = Renewable | Red = Fossil / Non-renewable | Blue = Storage | Orange = Mixed / Other")
    if not filtered_snapshot:
        st.info("No matching facility data in cache.")
        return
    marker_payload = _build_marker_payload(
        filtered_snapshot,
        display_mode,
        st.session_state.get("selected_fuel", "All"),
        st.session_state.get("selected_region", "All"),
    )
    component_value = render_nem_facility_map(marker_payload, height=730, key="nem-facility-map")
    if isinstance(component_value, dict):
        next_display_mode = component_value.get("display_mode")
        if next_display_mode in {"power_value", "emission_value"}:
            st.session_state.display_mode = next_display_mode


def render_dashboard() -> None:
    runtime = get_runtime()
    _ensure_session_defaults()
    runtime.maybe_soft_reset()
    runtime.ensure_connection()

    live_messages = runtime.cache.get_recent_messages()
    use_fallback = _should_use_fallback(runtime)
    fallback_messages = _load_fallback_messages() if use_fallback else []
    data_source = _resolve_data_source(live_messages, fallback_messages)
    messages = live_messages if live_messages else fallback_messages
    snapshot = _build_latest_snapshot(messages)
    fuel_options = _build_fuel_options(snapshot)
    if st.session_state.get("selected_fuel") not in fuel_options:
        st.session_state.selected_fuel = "All"
    filtered_snapshot = _filter_snapshot(snapshot, st.session_state.selected_fuel, st.session_state.selected_region)
    stats = _calculate_snapshot_stats(snapshot)

    _render_header(runtime, stats, snapshot)
    with st.sidebar:
        _render_sidebar(runtime, snapshot, filtered_snapshot, data_source, fuel_options)
    _render_current_trend(messages)
    _render_map(filtered_snapshot, st.session_state.display_mode)
    _render_table(filtered_snapshot)


def main() -> None:
    render_dashboard()
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
