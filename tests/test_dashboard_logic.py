from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, relative_path: str):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


task13 = load_module("task13_module", "Task1-3_data&MQTT.py")
task4 = load_module("task4_module", "Task4_appStreamlit.py")


class PublishLogicTests(TestCase):
    def test_safe_publish_stream_requires_confirmed_publish(self) -> None:
        class DummyInfo:
            def __init__(self, rc: int, published: bool) -> None:
                self.rc = rc
                self._published = published
                self.wait_called = False

            def wait_for_publish(self, timeout: int = 5) -> None:
                self.wait_called = True

            def is_published(self) -> bool:
                return self._published

        client = Mock()
        client.publish.return_value = DummyInfo(task13.mqtt.MQTT_ERR_SUCCESS, True)
        self.assertTrue(task13.safe_publish_stream(client, "topic", {"x": 1}))
        client.publish.return_value = DummyInfo(task13.mqtt.MQTT_ERR_SUCCESS, False)
        self.assertFalse(task13.safe_publish_stream(client, "topic", {"x": 1}))

    def test_publish_new_since_stops_on_failed_publish(self) -> None:
        rows = [
            {
                "_ts_dt": pd.Timestamp("2026-07-03T00:00:00+10:00"),
                "_ts_iso": "2026-07-03T00:00:00+10:00",
                "facility_code": "A1",
                "facility_name": "Alpha",
                "state": "NSW",
                "fuel_list": "Gas",
                "power_value": 10.0,
                "emission_value": None,
                "price_per_mwh": None,
                "demand_mw": None,
                "lat": -33.0,
                "lng": 151.0,
                "unit": "MW",
            },
            {
                "_ts_dt": pd.Timestamp("2026-07-03T00:05:00+10:00"),
                "_ts_iso": "2026-07-03T00:05:00+10:00",
                "facility_code": "A2",
                "facility_name": "Beta",
                "state": "NSW",
                "fuel_list": "Gas",
                "power_value": 20.0,
                "emission_value": None,
                "price_per_mwh": None,
                "demand_mw": None,
                "lat": -33.1,
                "lng": 151.1,
                "unit": "MW",
            },
        ]
        state = {"seq": 0, "last_ts": None, "last_fac": ""}

        with patch.object(task13, "safe_publish_stream", return_value=False) as publish_mock, \
            patch.object(task13, "sleep_until_ns", return_value=None), \
            patch.object(task13, "perf_counter_ns", return_value=0):
            task13.publish_new_since(Mock(), rows, state)

        self.assertEqual(state, {"seq": 0, "last_ts": None, "last_fac": ""})
        self.assertEqual(publish_mock.call_count, 1)

    def test_publish_new_since_commits_only_after_success(self) -> None:
        rows = [
            {
                "_ts_dt": pd.Timestamp("2026-07-03T00:00:00+10:00"),
                "_ts_iso": "2026-07-03T00:00:00+10:00",
                "facility_code": "A1",
                "facility_name": "Alpha",
                "state": "NSW",
                "fuel_list": "Gas",
                "power_value": 10.0,
                "emission_value": None,
                "price_per_mwh": None,
                "demand_mw": None,
                "lat": -33.0,
                "lng": 151.0,
                "unit": "MW",
            }
        ]
        state = {"seq": 0, "last_ts": None, "last_fac": ""}

        with patch.object(task13, "safe_publish_stream", return_value=True), \
            patch.object(task13, "sleep_until_ns", return_value=None), \
            patch.object(task13, "perf_counter_ns", return_value=0):
            task13.publish_new_since(Mock(), rows, state)

        self.assertEqual(state["seq"], 1)
        self.assertEqual(state["last_fac"], "A1")
        self.assertEqual(state["last_ts"], rows[0]["_ts_dt"])


class DashboardLogicTests(TestCase):
    def test_normalize_message_preserves_missing_optional_metrics(self) -> None:
        payload = {
            "facility_code": "A1",
            "facility_name": "Alpha",
            "lat": -33.0,
            "lng": 151.0,
            "timestamp": "2026-07-03T00:00:00+10:00",
            "power_value": 12.345,
            "state": "NSW",
            "fuel_list": "Gas",
        }

        record = task4._normalize_message(payload, "topic/test")
        self.assertIsNotNone(record)
        self.assertEqual(record["power_value"], 12.35)
        self.assertIsNone(record["emission_value"])
        self.assertIsNone(record["price_per_mwh"])
        self.assertIsNone(record["demand_mw"])

    def test_build_map_signature_changes_with_metric_values(self) -> None:
        base = {
            "A1": {
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "facility_name": "Alpha",
                "timestamp": "2026-07-03T00:00:00+10:00",
                "power_value": 10.0,
                "emission_value": None,
                "price_per_mwh": None,
                "demand_mw": None,
            }
        }
        updated = {
            "A1": {
                **base["A1"],
                "emission_value": 5.0,
                "timestamp": "2026-07-03T00:05:00+10:00",
            }
        }

        sig1 = task4._build_map_signature(base, "power_value", "All", "All")
        sig2 = task4._build_map_signature(updated, "power_value", "All", "All")
        self.assertNotEqual(sig1, sig2)

    def test_build_trend_frame_keeps_missing_values_as_nan(self) -> None:
        messages = [
            {
                "received_at": 1,
                "facility_code": "A1",
                "state": "NSW",
                "power_value": 10.0,
                "emission_value": None,
                "price_per_mwh": None,
                "demand_mw": None,
            },
            {
                "received_at": 2,
                "facility_code": "A1",
                "state": "NSW",
                "power_value": 12.0,
                "emission_value": 4.0,
                "price_per_mwh": 20.0,
                "demand_mw": 30.0,
            },
        ]

        frame = task4._build_trend_frame(messages)
        self.assertTrue(pd.isna(frame.loc[0, "emission_value"]))
        self.assertTrue(pd.isna(frame.loc[0, "price_per_mwh"]))
        self.assertTrue(pd.isna(frame.loc[0, "demand_mw"]))
        self.assertEqual(frame.loc[1, "emission_value"], 4.0)

    def test_snapshot_stats_ignore_missing_optional_values(self) -> None:
        snapshot = {
            "A1": {
                "power_value": 10.0,
                "emission_value": None,
                "price_per_mwh": None,
                "demand_mw": 5.0,
            },
            "A2": {
                "power_value": 20.0,
                "emission_value": 8.0,
                "price_per_mwh": 30.0,
                "demand_mw": None,
            },
        }

        stats = task4._calculate_snapshot_stats(snapshot)
        self.assertEqual(stats["total_power"], 30.0)
        self.assertEqual(stats["total_emission"], 8.0)
        self.assertEqual(stats["median_price"], 30.0)
        self.assertEqual(stats["median_demand"], 5.0)
