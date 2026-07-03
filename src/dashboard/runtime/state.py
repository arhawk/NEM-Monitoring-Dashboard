from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Optional

from .._compat import st
from ..settings import MAX_STREAM_ROWS, MONITOR_INTERVAL_SECONDS, RESET_INTERVAL_HOURS
from src.shared.stream_cache import StreamCache
from .mqtt import MqttConnectionManager


class DashboardRuntime:
    def __init__(self) -> None:
        self.cache = StreamCache(maxlen=MAX_STREAM_ROWS)
        self.status = "Connecting"
        self.last_error: Optional[str] = None
        self.last_soft_reset_at = datetime.now(timezone.utc)
        self._last_connect_attempt_at = 0.0
        self._monitor_stop = Event()
        self._monitor_lock = Lock()
        self._monitor_thread: Optional[Thread] = None
        self.connection_manager = MqttConnectionManager(self)
        self.client = self.connection_manager.client
        self.connection_manager.start()
        self._schedule_connect(initial=True)
        self._start_background_monitor()

    def _set_status(self, status: str, error: Optional[str] = None) -> None:
        self.status = status
        self.last_error = error

    def _schedule_connect(self, initial: bool = False) -> None:
        self.connection_manager.schedule_connect()

    def refresh_connection_state(self) -> None:
        self.connection_manager.refresh_connection_state()

    def ensure_connection(self) -> None:
        self.connection_manager.ensure_connection()

    def _background_monitor_loop(self) -> None:
        while not self._monitor_stop.wait(MONITOR_INTERVAL_SECONDS):
            try:
                self.maybe_soft_reset()
                self.ensure_connection()
            except Exception as exc:
                self.last_error = f"MQTT monitor failed: {exc}"

    def _start_background_monitor(self) -> None:
        with self._monitor_lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._monitor_stop.clear()
            self._monitor_thread = Thread(
                target=self._background_monitor_loop,
                name="nem-dashboard-mqtt-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def stop(self) -> None:
        self._monitor_stop.set()
        self.connection_manager.stop()
        thread = self._monitor_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)

    def maybe_soft_reset(self) -> bool:
        if RESET_INTERVAL_HOURS <= 0:
            return False
        if self.cache.uptime_seconds() < (RESET_INTERVAL_HOURS * 3600):
            return False
        _soft_reset_runtime(self)
        return True


_ACTIVE_RUNTIME: Optional[DashboardRuntime] = None


def set_active_runtime(runtime: DashboardRuntime) -> None:
    global _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = runtime


def get_active_runtime() -> DashboardRuntime:
    if _ACTIVE_RUNTIME is None:
        raise RuntimeError("Dashboard runtime has not been initialised")
    return _ACTIVE_RUNTIME


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
    "get_active_runtime",
    "set_active_runtime",
    "_soft_reset_runtime",
]
