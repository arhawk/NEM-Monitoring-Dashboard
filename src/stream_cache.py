from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from time import time
import os
from typing import Any, Deque, Dict, List, Optional


DEFAULT_MAX_STREAM_ROWS = 1000
DEFAULT_RESET_INTERVAL_HOURS = 6
DEFAULT_REFRESH_INTERVAL_SECONDS = 3


def _get_env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def get_max_stream_rows() -> int:
    return max(1, _get_env_int("MAX_STREAM_ROWS", DEFAULT_MAX_STREAM_ROWS))


def get_reset_interval_hours() -> float:
    return max(0.0, _get_env_float("RESET_INTERVAL_HOURS", DEFAULT_RESET_INTERVAL_HOURS))


def get_refresh_interval_seconds() -> int:
    return max(1, _get_env_int("REFRESH_INTERVAL_SECONDS", DEFAULT_REFRESH_INTERVAL_SECONDS))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StreamCache:
    maxlen: int = DEFAULT_MAX_STREAM_ROWS

    def __post_init__(self) -> None:
        self._messages: Deque[Dict[str, Any]] = deque(maxlen=self.maxlen)
        self._lock = RLock()
        self._created_at = time()
        self._last_reset_at = self._created_at
        self._last_updated_at: Optional[float] = None
        self._messages_since_reset = 0
        self._last_error: Optional[str] = None

    def add_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        record = dict(message)
        now = time()
        record.setdefault("received_at", now)
        record.setdefault("received_at_iso", utc_now_iso())
        with self._lock:
            self._messages.append(record)
            self._messages_since_reset += 1
            self._last_updated_at = float(record["received_at"])
        return record

    def get_latest_message(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._messages:
                return None
            return dict(self._messages[-1])

    def get_recent_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._messages)
        if limit is not None:
            items = items[-max(0, limit):]
        return [dict(item) for item in items]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._messages_since_reset = 0
            self._last_updated_at = None
            self._last_error = None
            self._last_reset_at = time()

    def size(self) -> int:
        with self._lock:
            return len(self._messages)

    def max_size(self) -> int:
        return self.maxlen

    def last_updated_at(self) -> Optional[float]:
        with self._lock:
            return self._last_updated_at

    def last_updated_at_iso(self) -> Optional[str]:
        ts = self.last_updated_at()
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def last_reset_at(self) -> float:
        with self._lock:
            return self._last_reset_at

    def last_reset_at_iso(self) -> str:
        return datetime.fromtimestamp(self.last_reset_at(), tz=timezone.utc).isoformat()

    def messages_since_reset(self) -> int:
        with self._lock:
            return self._messages_since_reset

    def uptime_seconds(self) -> float:
        return time() - self.last_reset_at()

    def set_last_error(self, error: Optional[str]) -> None:
        with self._lock:
            self._last_error = error

    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

