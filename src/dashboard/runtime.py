from __future__ import annotations

from datetime import datetime, timezone
import time as pytime
from typing import Optional

import paho.mqtt.client as mqtt
import streamlit as st

from src.shared.stream_cache import StreamCache

from .data import _normalize_message, _reason_is_success
from .settings import (
    BROKER,
    CONNECTION_TIMEOUT_SECONDS,
    MAX_STREAM_ROWS,
    PASSWORD,
    PORT,
    RECONNECT_COOLDOWN_SECONDS,
    RESET_INTERVAL_HOURS,
    TOPIC,
    USERNAME,
)


class DashboardRuntime:
    def __init__(self) -> None:
        self.cache = StreamCache(maxlen=MAX_STREAM_ROWS)
        self.client: Optional[mqtt.Client] = None
        self.status = "Connecting"
        self.last_error: Optional[str] = None
        self.last_soft_reset_at = datetime.now(timezone.utc)
        self._last_connect_attempt_at = 0.0
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
        self.status = status
        self.last_error = error

    def _schedule_connect(self, initial: bool = False) -> None:
        if self.client is None:
            return
        try:
            self._last_connect_attempt_at = pytime.monotonic()
            self._set_status("Connecting", None)
            self.client.connect_async(BROKER, PORT, keepalive=60)
        except Exception as exc:
            self._set_status("Error", f"MQTT connect failed: {exc}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if _reason_is_success(reason_code):
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
            import json

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
        if self.status == "Connecting" and (pytime.monotonic() - self._last_connect_attempt_at) > CONNECTION_TIMEOUT_SECONDS:
            self._set_status("Disconnected", "MQTT connection timed out")

    def ensure_connection(self) -> None:
        self.refresh_connection_state()
        if self.status == "Connected":
            return
        if (pytime.monotonic() - self._last_connect_attempt_at) < RECONNECT_COOLDOWN_SECONDS:
            return
        self._schedule_connect(initial=False)

    def maybe_soft_reset(self) -> bool:
        if RESET_INTERVAL_HOURS <= 0:
            return False
        if self.cache.uptime_seconds() < (RESET_INTERVAL_HOURS * 3600):
            return False
        _soft_reset_runtime(self)
        return True


@st.cache_resource(show_spinner=False)
def get_runtime() -> DashboardRuntime:
    return DashboardRuntime()


def _soft_reset_runtime(runtime: object) -> None:
    current_status = getattr(runtime, "status", None)
    cache = getattr(runtime, "cache", None)
    if cache is None:
        return
    cache.clear()
    if hasattr(runtime, "last_soft_reset_at"):
        runtime.last_soft_reset_at = datetime.now(timezone.utc)
    if hasattr(runtime, "last_error"):
        runtime.last_error = None
    if hasattr(cache, "set_last_error"):
        cache.set_last_error(None)
    if current_status != "Connected":
        if hasattr(runtime, "_set_status"):
            runtime._set_status("Connecting", None)
        if hasattr(runtime, "_schedule_connect"):
            runtime._schedule_connect(initial=False)


__all__ = [
    "DashboardRuntime",
    "get_runtime",
    "_soft_reset_runtime",
]
