from __future__ import annotations

import json
import os
import time
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import folium
import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st
from streamlit_folium import st_folium

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
DISPLAY_FUEL_OPTIONS = ["All", "Solar", "Wind", "Hydro", "Gas", "Coal", "Battery", "Biomass"]
DISPLAY_REGION_OPTIONS = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        "emission_value": round(_coerce_float(payload.get("emission_value")) or 0.0, 2),
        "price_per_mwh": round(_coerce_float(payload.get("price_per_mwh")) or 0.0, 2),
        "demand_mw": round(_coerce_float(payload.get("demand_mw")) or 0.0, 2),
        "state": payload.get("state") or "Unknown Region",
        "fuel_list": payload.get("fuel_list") or "Unknown",
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


def _calculate_snapshot_stats(snapshot: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    values = list(snapshot.values())
    if not values:
        return {
            "facility_count": 0,
            "total_power": 0.0,
            "total_emission": 0.0,
            "median_price": 0.0,
            "median_demand": 0.0,
        }

    total_power = sum(float(item.get("power_value", 0.0)) for item in values)
    total_emission = sum(float(item.get("emission_value", 0.0)) for item in values)

    valid_prices = [float(item.get("price_per_mwh", 0.0)) for item in values if float(item.get("price_per_mwh", 0.0)) > 0]
    valid_demands = [float(item.get("demand_mw", 0.0)) for item in values if float(item.get("demand_mw", 0.0)) > 0]

    return {
        "facility_count": len(values),
        "total_power": round(total_power, 2),
        "total_emission": round(total_emission, 2),
        "median_price": round(float(pd.Series(valid_prices).median()) if valid_prices else 0.0, 2),
        "median_demand": round(float(pd.Series(valid_demands).median()) if valid_demands else 0.0, 2),
    }


def _filter_snapshot(
    snapshot: Dict[str, Dict[str, Any]],
    selected_fuel: str,
    selected_region: str,
) -> Dict[str, Dict[str, Any]]:
    filtered: Dict[str, Dict[str, Any]] = {}
    for fac_code, record in snapshot.items():
        fuel_match = selected_fuel == "All" or selected_fuel in str(record.get("fuel_list", ""))
        region_match = selected_region == "All" or selected_region == record.get("state")
        if fuel_match and region_match:
            filtered[fac_code] = record
    return filtered


def _build_map(records: Dict[str, Dict[str, Any]], display_mode: str) -> folium.Map:
    if not records:
        return folium.Map(location=[-27.5, 133.8], zoom_start=4, tiles="OpenStreetMap")

    m = folium.Map(location=[-27.5, 133.8], zoom_start=4, tiles="OpenStreetMap")
    for fac_code, info in records.items():
        value = info.get(display_mode, 0)
        unit = "MW" if display_mode == "power_value" else "tCO2e"
        label = "Power" if display_mode == "power_value" else "Emissions"
        tooltip_text = f"{info.get('facility_name', fac_code)} | {label}: {value} {unit}"
        popup_html = f"""
        <b>{info.get('facility_name', fac_code)}</b><br>
        Facility Code: {fac_code}<br>
        Region: {info.get('state', 'Unknown Region')}<br>
        Fuel Type: {info.get('fuel_list', 'Unknown')}<br>
        Last Payload Time: {info.get('timestamp', 'Unknown')}<br>
        Power Output: {info.get('power_value', 0)} MW<br>
        CO2 Emissions: {info.get('emission_value', 0)} tCO2e<br>
        Current Price: {info.get('price_per_mwh', 0)} $/MWh<br>
        Grid Demand: {info.get('demand_mw', 0)} MW
        """
        fuel_text = str(info.get("fuel_list", ""))
        fuel_color = "green" if any(token in fuel_text for token in ("Solar", "Wind", "Hydro")) else "orange" if "Gas" in fuel_text else "red"
        folium.CircleMarker(
            location=[info["lat"], info["lng"]],
            radius=8,
            color=fuel_color,
            fill=True,
            fill_color=fuel_color,
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=tooltip_text,
        ).add_to(m)
    return m


def _build_trend_frame(messages: List[Dict[str, Any]]) -> pd.DataFrame:
    if not messages:
        return pd.DataFrame()
    df = pd.DataFrame(messages)
    if "received_at" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["received_at"] = pd.to_datetime(df["received_at"], unit="s", utc=True)
    numeric_cols = ["power_value", "emission_value", "price_per_mwh", "demand_mw"]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0.0
    return df[["received_at", "facility_code", "state", *numeric_cols]]


def _build_trend_svg(messages: List[Dict[str, Any]]) -> str:
    df = _build_trend_frame(messages)
    if df.empty:
        return ""

    df = df.tail(120).copy()
    width = 1200
    height = 300
    padding_x = 55
    padding_y = 28
    plot_w = width - padding_x * 2
    plot_h = height - padding_y * 2
    metrics = [
        ("power_value", "#0f766e", "Power"),
        ("emission_value", "#b45309", "Emissions"),
        ("price_per_mwh", "#2563eb", "Price"),
        ("demand_mw", "#7c3aed", "Demand"),
    ]
    all_values = []
    for metric, _, _ in metrics:
        all_values.extend([float(v) for v in df[metric].tolist() if pd.notna(v)])
    if not all_values:
        return ""

    min_y = min(all_values)
    max_y = max(all_values)
    if max_y == min_y:
        max_y = min_y + 1.0

    def scale_x(index: int, total: int) -> float:
        if total <= 1:
            return padding_x
        return padding_x + (plot_w * index / (total - 1))

    def scale_y(value: float) -> float:
        normalized = (value - min_y) / (max_y - min_y)
        return padding_y + plot_h - normalized * plot_h

    def polyline(metric: str) -> str:
        points = []
        values = [float(v) for v in df[metric].tolist()]
        total = len(values)
        for idx, value in enumerate(values):
            points.append(f"{scale_x(idx, total):.1f},{scale_y(value):.1f}")
        return " ".join(points)

    grid_lines = []
    for step in range(5):
        y = padding_y + plot_h * step / 4
        grid_lines.append(f'<line x1="{padding_x}" y1="{y:.1f}" x2="{width - padding_x}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1" />')

    legend_items = []
    legend_x = padding_x
    legend_y = 18
    for metric, color, label in metrics:
        legend_items.append(
            f'<rect x="{legend_x}" y="{legend_y - 10}" width="10" height="10" fill="{color}" />'
            f'<text x="{legend_x + 14}" y="{legend_y}" font-size="12" fill="#334155">{html.escape(label)}</text>'
        )
        legend_x += 120

    y_labels = []
    for step in range(5):
        value = max_y - (max_y - min_y) * step / 4
        y = padding_y + plot_h * step / 4 + 4
        y_labels.append(f'<text x="8" y="{y:.1f}" font-size="11" fill="#64748b">{value:.0f}</text>')

    x_labels = []
    if len(df) > 1:
        positions = [0, len(df) // 2, len(df) - 1]
        seen = set()
        for pos in positions:
            if pos in seen:
                continue
            seen.add(pos)
            label = df.iloc[pos]["received_at"].strftime("%H:%M:%S")
            x = scale_x(pos, len(df))
            x_labels.append(f'<text x="{x:.1f}" y="{height - 6}" font-size="11" text-anchor="middle" fill="#64748b">{html.escape(label)}</text>')

    path_elements = []
    for metric, color, _ in metrics:
        path_elements.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{polyline(metric)}" />'
        )

    svg = f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Recent MQTT trend chart">
      <rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="#ffffff" stroke="#e2e8f0" />
      {"".join(grid_lines)}
      {"".join(y_labels)}
      {"".join(x_labels)}
      {"".join(legend_items)}
      {"".join(path_elements)}
    </svg>
    """
    return svg


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


def _render_header(runtime: DashboardRuntime, stats: Dict[str, float], snapshot: Dict[str, Dict[str, Any]]) -> None:
    st.title("⚡ National Electricity Market (NEM) Facility Real-time Monitoring Dashboard")
    st.caption("Live MQTT stream with bounded in-memory cache. No live CSV storage is used.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Power Output MW", f"{stats['total_power']}")
    with col2:
        st.metric("Total CO2 Emissions tCO2e", f"{stats['total_emission']}")
    with col3:
        st.metric("Median Price $/MWh", f"{stats['median_price']}")
    with col4:
        st.metric("Median Grid Demand MW", f"{stats['median_demand']}")


def _render_sidebar(runtime: DashboardRuntime, snapshot: Dict[str, Dict[str, Any]], filtered_snapshot: Dict[str, Dict[str, Any]]) -> None:
    st.header("🔧 Control Center")
    st.subheader("Display Mode")
    display_mode = st.session_state.get("display_mode", "power_value")
    if st.button("📊 Show Power", type="primary" if display_mode == "power_value" else "secondary"):
        st.session_state.display_mode = "power_value"
    if st.button("🌍 Show Emissions", type="primary" if display_mode == "emission_value" else "secondary"):
        st.session_state.display_mode = "emission_value"

    st.subheader("Fuel Type Filter")
    st.selectbox("Select Fuel Type", DISPLAY_FUEL_OPTIONS, key="selected_fuel")

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
                "timestamp": latest.get("timestamp"),
                "received_at": latest.get("received_at_iso"),
            }
        )
    else:
        st.write("No MQTT messages have arrived yet.")

    st.subheader("Stream Status")
    if runtime.status == "Connected":
        st.success("Connected")
    elif runtime.status == "Connecting":
        st.info("Connecting")
    elif runtime.status == "Disconnected":
        st.warning("Disconnected")
    else:
        st.error("Error")
    st.write(f"Cache size: {runtime.cache.size()} / {runtime.cache.max_size()}")
    st.write(f"Last message: {_format_ts(runtime.cache.last_updated_at())}")
    st.write(f"Last soft reset: {_format_ts(runtime.cache.last_reset_at())}")
    if runtime.last_error:
        st.caption(runtime.last_error)


def _render_chart(messages: List[Dict[str, Any]]) -> None:
    st.subheader("Recent Trend")
    svg = _build_trend_svg(messages)
    if not svg:
        st.info("No MQTT messages available for trend chart yet.")
        return
    st.markdown(svg, unsafe_allow_html=True)


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
    if not filtered_snapshot:
        st.info("No matching facility data in cache.")
        return
    map_key = (
        display_mode,
        tuple(
            sorted(
                (
                    code,
                    round(info.get("lat", 0.0), 5),
                    round(info.get("lng", 0.0), 5),
                    info.get("state", ""),
                    str(info.get("fuel_list", "")),
                    round(info.get("power_value", 0.0), 2),
                    round(info.get("emission_value", 0.0), 2),
                )
                for code, info in filtered_snapshot.items()
            )
        ),
    )
    if st.session_state.get("_map_cache_key") != map_key:
        st.session_state._map_cache_key = map_key
        st.session_state._cached_map = _build_map(filtered_snapshot, display_mode)
    if "_cached_map" in st.session_state:
        st_folium(st.session_state._cached_map, width=1200, height=700)


def render_dashboard() -> None:
    runtime = get_runtime()
    _ensure_session_defaults()
    runtime.maybe_soft_reset()
    runtime.ensure_connection()

    messages = runtime.cache.get_recent_messages()
    snapshot = _build_latest_snapshot(messages)
    filtered_snapshot = _filter_snapshot(snapshot, st.session_state.selected_fuel, st.session_state.selected_region)
    stats = _calculate_snapshot_stats(snapshot)

    _render_header(runtime, stats, snapshot)
    with st.sidebar:
        _render_sidebar(runtime, snapshot, filtered_snapshot)
    _render_chart(messages)
    _render_table(filtered_snapshot)
    _render_map(filtered_snapshot, st.session_state.display_mode)


def main() -> None:
    render_dashboard()
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
