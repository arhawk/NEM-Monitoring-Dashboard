from __future__ import annotations

import json
import threading
from datetime import datetime
from io import StringIO
from typing import Any

import pandas as pd

from .paths import data_path


CACHE_FILE = data_path("facility_data_cache.json")
cache_lock = threading.Lock()


def load_cache() -> dict[str, dict[str, Any]]:
    """Load cached data from JSON file and restore datetime/DataFrame objects."""
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            for key, value in data.items():
                parts = key.split("|")
                if len(parts) != 4:
                    print(f"Invalid cache key: {key}, skipped")
                    continue
                value["date_start"] = datetime.fromisoformat(value["date_start"])
                value["date_end"] = datetime.fromisoformat(value["date_end"])
                consolidated_io = StringIO(value["consolidated_data"])
                value["consolidated_data"] = pd.read_json(consolidated_io, orient="split")
            return data
    except FileNotFoundError:
        return {}


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    """Save cache to JSON (thread-safe), converting non-serializable objects first."""
    with cache_lock:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable_cache: dict[str, dict[str, Any]] = {}
        for key, value in cache.items():
            serializable_cache[key] = {
                "date_start": value["date_start"].isoformat(),
                "date_end": value["date_end"].isoformat(),
                "consolidated_data": value["consolidated_data"].to_json(orient="split"),
            }
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(serializable_cache, f, indent=2)


__all__ = ["CACHE_FILE", "cache_lock", "load_cache", "save_cache"]
