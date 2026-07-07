from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from src.shared import cache_snapshot, config, stream_cache


class CacheSnapshotTests(TestCase):
    def test_round_trip_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "snapshot.json"
            messages = [{"facility_code": "ABC", "received_at": 1.0}]
            cache_snapshot.save_snapshot(path, messages)
            restored = cache_snapshot.load_snapshot(path)
            self.assertEqual(restored, messages)

    def test_resolve_snapshot_path_disables_persistence(self) -> None:
        self.assertIsNone(cache_snapshot.resolve_snapshot_path("off"))
        self.assertIsNone(cache_snapshot.resolve_snapshot_path("disabled"))


class StreamCachePersistenceTests(TestCase):
    def test_stream_cache_restores_and_persists_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "snapshot.json"
            first = stream_cache.StreamCache(
                maxlen=5,
                snapshot_path=path,
                persist_every_messages=1,
            )
            first.add_message({"facility_code": "ABC", "power_mw": 12.5})
            second = stream_cache.StreamCache(
                maxlen=5,
                snapshot_path=path,
                persist_every_messages=1,
            )
            restored = second.get_recent_messages()
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0]["facility_code"], "ABC")


class FetchDateConfigTests(TestCase):
    def test_fetch_dates_use_defaults_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                config.get_fetch_date_start(),
                datetime.fromisoformat(config.DEFAULT_FETCH_DATE_START),
            )
            self.assertEqual(
                config.get_fetch_date_end(),
                datetime.fromisoformat(config.DEFAULT_FETCH_DATE_END),
            )

    def test_fetch_dates_parse_iso_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "FETCH_DATE_START": "2025-01-01T00:00:00",
                "FETCH_DATE_END": "2025-01-02T12:30:00",
            },
            clear=True,
        ):
            self.assertEqual(
                config.get_fetch_date_start(),
                datetime(2025, 1, 1, 0, 0, 0),
            )
            self.assertEqual(
                config.get_fetch_date_end(),
                datetime(2025, 1, 2, 12, 30, 0),
            )

    def test_stream_cache_snapshot_path_can_be_disabled(self) -> None:
        with patch.dict(os.environ, {"STREAM_CACHE_SNAPSHOT_PATH": "off"}, clear=True):
            self.assertIsNone(config.get_stream_cache_snapshot_path())
