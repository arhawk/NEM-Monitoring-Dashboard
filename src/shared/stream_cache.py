from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Deque, Dict, List, Optional

from .cache_snapshot import load_snapshot, save_snapshot
from .config import (
    DEFAULT_MAX_STREAM_ROWS,
    get_main_refresh_interval_seconds as _get_main_refresh_interval_seconds,
    get_max_stream_rows as _get_max_stream_rows,
    get_reset_interval_hours as _get_reset_interval_hours,
    get_sidebar_refresh_interval_seconds as _get_sidebar_refresh_interval_seconds,
    get_stream_cache_persist_every_messages as _get_stream_cache_persist_every_messages,
    get_stream_cache_snapshot_path as _get_stream_cache_snapshot_path,
)


def get_max_stream_rows() -> int:
    return _get_max_stream_rows()


def get_reset_interval_hours() -> float:
    return _get_reset_interval_hours()


def get_main_refresh_interval_seconds() -> int:
    return _get_main_refresh_interval_seconds()


def get_sidebar_refresh_interval_seconds() -> int:
    return _get_sidebar_refresh_interval_seconds()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StreamCache:
    maxlen: int = DEFAULT_MAX_STREAM_ROWS
    snapshot_path: Optional[Path] = field(default=None, repr=False)
    persist_every_messages: int = field(default=100, repr=False)

    def __post_init__(self) -> None:
        if self.snapshot_path is None:
            self.snapshot_path = _get_stream_cache_snapshot_path()
        if self.persist_every_messages <= 0:
            self.persist_every_messages = _get_stream_cache_persist_every_messages()
        self._messages: Deque[Dict[str, Any]] = deque(maxlen=self.maxlen)
        self._lock = RLock()
        self._created_at = time()
        self._last_reset_at = self._created_at
        self._last_updated_at: Optional[float] = None
        self._messages_since_reset = 0
        self._last_error: Optional[str] = None
        self._messages_since_persist = 0
        self._hydrate_from_snapshot()

    def add_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        record = dict(message)
        now = time()
        record.setdefault("received_at", now)
        record.setdefault("received_at_iso", utc_now_iso())
        with self._lock:
            self._messages.append(record)
            self._messages_since_reset += 1
            self._last_updated_at = float(record["received_at"])
            self._messages_since_persist += 1
            should_persist = (
                self.snapshot_path is not None
                and self._messages_since_persist >= self.persist_every_messages
            )
            if should_persist:
                self._messages_since_persist = 0
                messages = list(self._messages)
        if should_persist:
            self._persist_messages(messages)
        return record

    def get_recent_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._messages)
        if limit is not None:
            items = items[-max(0, limit) :]
        return [dict(item) for item in items]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._messages_since_reset = 0
            self._last_updated_at = None
            self._last_error = None
            self._last_reset_at = time()
            self._messages_since_persist = 0
        self._persist_messages([])

    def utilization_ratio(self) -> float:
        with self._lock:
            if self.maxlen <= 0:
                return 0.0
            return len(self._messages) / self.maxlen

    def throughput_per_minute(self) -> float:
        uptime_minutes = max(self.uptime_seconds() / 60.0, 1.0 / 60.0)
        return self.messages_since_reset() / uptime_minutes

    def snapshot_enabled(self) -> bool:
        return self.snapshot_path is not None

    def _hydrate_from_snapshot(self) -> None:
        if self.snapshot_path is None:
            return
        restored = load_snapshot(self.snapshot_path)
        if not restored:
            return
        with self._lock:
            for message in restored[-self.maxlen :]:
                self._messages.append(dict(message))
            self._messages_since_reset = len(self._messages)
            if self._messages:
                last_received_at = self._messages[-1].get("received_at")
                if isinstance(last_received_at, (int, float)):
                    self._last_updated_at = float(last_received_at)

    def _persist_messages(self, messages: List[Dict[str, Any]]) -> None:
        if self.snapshot_path is None:
            return
        try:
            save_snapshot(self.snapshot_path, messages)
        except OSError as exc:
            self.set_last_error(f"Snapshot persist failed: {exc}")

    def size(self) -> int:
        with self._lock:
            return len(self._messages)

    def max_size(self) -> int:
        return self.maxlen

    def last_updated_at(self) -> Optional[float]:
        with self._lock:
            return self._last_updated_at

    def last_reset_at(self) -> float:
        with self._lock:
            return self._last_reset_at

    def messages_since_reset(self) -> int:
        with self._lock:
            return self._messages_since_reset

    def uptime_seconds(self) -> float:
        return time() - self.last_reset_at()

    def set_last_error(self, error: Optional[str]) -> None:
        with self._lock:
            self._last_error = error
