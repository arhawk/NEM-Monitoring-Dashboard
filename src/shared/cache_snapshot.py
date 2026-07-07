from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import cache_data_path


SNAPSHOT_VERSION = 1


def default_snapshot_path() -> Path:
    return cache_data_path("stream_cache_snapshot.json")


def load_snapshot(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    if payload.get("version") != SNAPSHOT_VERSION:
        return []
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    return [dict(item) for item in messages if isinstance(item, dict)]


def save_snapshot(path: Path, messages: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SNAPSHOT_VERSION,
        "messages": [dict(item) for item in messages],
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temp_path.replace(path)


def resolve_snapshot_path(raw_value: Optional[str]) -> Optional[Path]:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized or normalized.lower() in {
        "off",
        "false",
        "0",
        "none",
        "disabled",
    }:
        return None
    return Path(normalized)


__all__ = [
    "SNAPSHOT_VERSION",
    "default_snapshot_path",
    "load_snapshot",
    "resolve_snapshot_path",
    "save_snapshot",
]
