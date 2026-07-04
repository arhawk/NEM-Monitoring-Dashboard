from __future__ import annotations

import time as pytime
from types import SimpleNamespace
from typing import Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - exercised in dependency-light test envs
    class _MissingMQTTClient:
        def __init__(self, *args, **kwargs):
            raise ModuleNotFoundError("paho-mqtt is required for dashboard runtime")

    mqtt = SimpleNamespace(
        Client=_MissingMQTTClient,
        MQTT_ERR_SUCCESS=0,
        CallbackAPIVersion=SimpleNamespace(VERSION2=2),
    )

from ..data import _normalize_message, _reason_is_success
from ..settings import BROKER, PASSWORD, PORT, SUBSCRIBE_TOPIC_FILTER, USERNAME


class MqttConnectionManager:
    def __init__(self, runtime: object) -> None:
        self.runtime = runtime
        self.client: Optional[mqtt.Client] = None
        self._build_client()

    def _build_client(self) -> None:
        self.client = mqtt.Client(
            client_id="nem-facility-monitor-dashboard",
            clean_session=True,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if USERNAME:
            self.client.username_pw_set(USERNAME, PASSWORD)
        self.client.reconnect_delay_set(min_delay=5, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        if hasattr(self.client, "on_connect_fail"):
            self.client.on_connect_fail = self._on_connect_fail
        self.client.on_message = self._on_message

    def start(self) -> None:
        if self.client is not None:
            self.client.loop_start()

    def schedule_connect(self) -> None:
        if self.client is None:
            return
        try:
            self.runtime._last_connect_attempt_at = pytime.monotonic()
            self.runtime._set_status("Connecting", None)
            self.client.connect_async(BROKER, PORT, keepalive=60)
        except Exception as exc:
            self.runtime._set_status("Error", f"MQTT connect failed: {exc}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if _reason_is_success(reason_code):
            self.runtime.cache.set_last_error(None)
            self.runtime._set_status("Connected", None)
            try:
                client.subscribe(SUBSCRIBE_TOPIC_FILTER, qos=0)
            except Exception as exc:
                self.runtime._set_status("Error", f"Subscription failed: {exc}")
        else:
            self.runtime._set_status("Error", f"MQTT connection rejected: {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        if _reason_is_success(reason_code):
            self.runtime._set_status("Disconnected", None)
        else:
            self.runtime._set_status("Disconnected", f"MQTT disconnected: {reason_code}")

    def _on_connect_fail(self, client, userdata) -> None:
        self.runtime._set_status("Error", "MQTT connection failed")

    def _on_message(self, client, userdata, msg, properties=None) -> None:
        try:
            import json

            payload = json.loads(msg.payload.decode("utf-8"))
            record = _normalize_message(payload, msg.topic)
            if record is None:
                return
            self.runtime.cache.add_message(record)
            self.runtime.cache.set_last_error(None)
        except Exception as exc:
            self.runtime.cache.set_last_error(str(exc))
            self.runtime.last_error = f"Message processing failed: {exc}"

    def refresh_connection_state(self) -> None:
        from ..settings import CONNECTION_TIMEOUT_SECONDS

        if self.runtime.status == "Connecting" and (pytime.monotonic() - self.runtime._last_connect_attempt_at) > CONNECTION_TIMEOUT_SECONDS:
            self.runtime._set_status("Disconnected", "MQTT connection timed out")

    def ensure_connection(self) -> None:
        from ..settings import RECONNECT_COOLDOWN_SECONDS

        self.refresh_connection_state()
        if self.runtime.status == "Connected":
            return
        if (pytime.monotonic() - self.runtime._last_connect_attempt_at) < RECONNECT_COOLDOWN_SECONDS:
            return
        self.schedule_connect()

    def stop(self) -> None:
        if self.client is not None:
            self.client.loop_stop()


__all__ = ["MqttConnectionManager"]
