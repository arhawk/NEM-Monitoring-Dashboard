from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
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
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


task13 = load_module("task13_module", "Task1-3_data&MQTT.py")
task4 = load_module("task4_module", "Task4_appStreamlit.py")
stream_cache = load_module("stream_cache_module", "src/stream_cache.py")


class PublishLogicTests(TestCase):
    def test_normalize_non_negative_replaces_negative_values_only(self) -> None:
        series = pd.Series([5.0, -3.0, None, 0.0, -1.5], name="Power (MW)")
        cleaned = task13.normalize_non_negative(series)
        self.assertEqual(cleaned.iloc[0], 5.0)
        self.assertEqual(cleaned.iloc[1], 0.0)
        self.assertTrue(pd.isna(cleaned.iloc[2]))
        self.assertEqual(cleaned.iloc[3], 0.0)
        self.assertEqual(cleaned.iloc[4], 0.0)

    def test_handle_missing_values_fast_drops_fully_missing_facility(self) -> None:
        group = pd.DataFrame(
            {
                "facility_code": ["A1", "A1"],
                "Power (MW)": [None, None],
                "Emissions (tonnes)": [None, None],
            }
        )
        result = task13.handle_missing_values_fast(group)
        self.assertTrue(result.empty)

    def test_fill_missing_half_ffill_bfill_keeps_partial_gap_semantics(self) -> None:
        series = pd.Series([1.0, None, None, 4.0], name="Power (MW)")
        cleaned = task13.fill_missing_half_ffill_bfill(series)
        self.assertEqual(cleaned.iloc[1], 1.0)
        self.assertEqual(cleaned.iloc[2], 4.0)

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
    def _build_sidebar_runtime(self, status: str = "Connected") -> Mock:
        runtime = Mock()
        runtime.status = status
        runtime.last_error = None
        runtime.cache.messages_since_reset.return_value = 3
        runtime.cache.get_latest_message.return_value = None
        runtime.cache.size.return_value = 2
        runtime.cache.max_size.return_value = 100
        runtime.cache.last_updated_at.return_value = None
        runtime.cache.last_reset_at.return_value = None
        return runtime

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

    def test_static_signature_ignores_operational_changes(self) -> None:
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
                "timestamp": "2026-07-03T00:05:00+10:00",
                "power_value": 12.0,
                "emission_value": 4.0,
            }
        }

        self.assertEqual(task4._build_static_signature(base), task4._build_static_signature(updated))
        self.assertNotEqual(task4._build_operational_signature(base), task4._build_operational_signature(updated))

    def test_resolve_data_source_defaults_to_fallback_without_live_or_fallback(self) -> None:
        self.assertEqual(task4._resolve_data_source([], []), "fallback")

    def test_resolve_data_source_uses_fallback_before_live_messages_arrive(self) -> None:
        fallback_messages = [{"facility_code": "A1"}]
        self.assertEqual(task4._resolve_data_source([], fallback_messages), "fallback")

    def test_resolve_data_source_uses_live_only_when_live_messages_exist(self) -> None:
        live_messages = [{"facility_code": "A1"}]
        fallback_messages = [{"facility_code": "B1"}]
        self.assertEqual(task4._resolve_data_source(live_messages, fallback_messages), "live")

    def test_resolve_data_source_transitions_to_live_after_first_message(self) -> None:
        fallback_messages = [{"facility_code": "B1"}]
        self.assertEqual(task4._resolve_data_source([], fallback_messages), "fallback")

        live_messages = [{"facility_code": "A1"}]
        self.assertEqual(task4._resolve_data_source(live_messages, fallback_messages), "live")

    def test_should_use_fallback_immediately_before_first_live_message(self) -> None:
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = None
        self.assertTrue(task4._should_use_fallback(runtime))

    def test_should_use_fallback_when_live_data_is_stale(self) -> None:
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = 100.0

        with patch.object(task4.time, "time", return_value=100.0 + task4.FALLBACK_STALE_SECONDS + 1):
            self.assertTrue(task4._should_use_fallback(runtime))

    def test_should_not_use_fallback_when_live_data_is_fresh(self) -> None:
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = 100.0

        with patch.object(task4.time, "time", return_value=100.0 + max(0, task4.FALLBACK_STALE_SECONDS - 1)):
            self.assertFalse(task4._should_use_fallback(runtime))

    def test_static_signature_changes_with_location_and_identity_fields(self) -> None:
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
        moved = {
            "A1": {
                **base["A1"],
                "lat": -34.0,
            }
        }

        self.assertNotEqual(task4._build_static_signature(base), task4._build_static_signature(moved))

    def test_marker_payload_reflects_display_mode_and_fingerprint(self) -> None:
        records = {
            "A1": {
                "facility_code": "A1",
                "facility_name": "Alpha",
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "timestamp": "2026-07-03T00:00:00+10:00",
                "power_value": 10.0,
                "emission_value": 2.0,
                "price_per_mwh": 30.0,
                "demand_mw": 40.0,
            }
        }

        payload = task4._build_marker_payload(records, "power_value", "All", "All")
        self.assertEqual(payload["display_mode"], "power_value")
        self.assertEqual(payload["static_signature"], task4._build_static_signature(records))
        self.assertEqual(payload["operational_signature"], task4._build_operational_signature(records))
        self.assertEqual(payload["markers"][0]["facility_code"], "A1")
        self.assertEqual(payload["markers"][0]["fingerprint"][0], "power_value")
        self.assertGreater(payload["markers"][0]["radius"], 5.5)

    def test_get_latest_trend_message_prefers_latest_valid_record(self) -> None:
        messages = [
            {
                "facility_code": "A1",
                "facility_name": "Alpha",
                "power_value": 10.0,
            },
            {
                "facility_code": "",
                "facility_name": "Broken",
                "power_value": 11.0,
            },
            {
                "facility_code": "A2",
                "facility_name": "Beta",
                "power_value": 12.0,
            },
        ]

        latest = task4._get_latest_trend_message(messages)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["facility_code"], "A2")
        self.assertEqual(latest["facility_name"], "Beta")

    def test_build_current_trend_cards_formats_latest_metrics(self) -> None:
        message = {
            "facility_code": "A1",
            "facility_name": "Alpha",
            "power_value": 12.345,
            "emission_value": 6.789,
            "price_per_mwh": 101.234,
            "demand_mw": 21993.5,
        }

        cards = task4._build_current_trend_cards(message)
        self.assertEqual(
            [card["label"] for card in cards],
            [
                "Power Output MW",
                "CO2 Emissions tCO2e",
                "Price $/MWh",
                "Grid Demand MW",
            ],
        )
        self.assertEqual(cards[0]["value"], "12.35 MW")
        self.assertEqual(cards[1]["value"], "6.79 tCO2e")
        self.assertEqual(cards[2]["value"], "101.23 $/MWh")
        self.assertEqual(cards[3]["value"], "21993.5 MW")

    def test_build_current_trend_html_wraps_content_in_small_box(self) -> None:
        message = {
            "facility_code": "WOOLGSF",
            "facility_name": "Woolooga",
            "timestamp": "2025-10-25T08:50:00",
            "power_value": 0.0,
            "emission_value": 0.0,
            "price_per_mwh": 102.16,
            "demand_mw": 23448.02,
        }

        html = task4._build_current_trend_html(message)
        self.assertIn("Current Facility: Woolooga", html)
        self.assertIn("WOOLGSF | 2025-10-25T08:50:00", html)
        self.assertIn("border: 1px solid #dbe4ee", html)
        self.assertIn("font-size: 0.92rem", html)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", html)

    def test_render_current_trend_shows_empty_state_when_no_messages(self) -> None:
        with patch.object(task4.st, "subheader") as subheader_mock, \
            patch.object(task4.st, "info") as info_mock:
            task4._render_current_trend([])

        subheader_mock.assert_called_once_with("Current Facility")
        info_mock.assert_called_once_with("No MQTT messages available for current trend yet.")

    def test_render_current_trend_uses_html_component_for_latest_record(self) -> None:
        messages = [
            {
                "facility_code": "WOOLGSF",
                "facility_name": "Woolooga",
                "timestamp": "2025-10-25T08:50:00",
                "power_value": 0.0,
                "emission_value": 0.0,
                "price_per_mwh": 102.16,
                "demand_mw": 23448.02,
            }
        ]

        with patch.object(task4.components, "html") as html_mock:
            task4._render_current_trend(messages)

        html_mock.assert_called_once()
        self.assertIn("Current Facility: Woolooga", html_mock.call_args.args[0])
        self.assertEqual(html_mock.call_args.kwargs["height"], 220)
        self.assertFalse(html_mock.call_args.kwargs["scrolling"])

    def test_refresh_interval_defaults_to_one_second(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stream_cache.get_refresh_interval_seconds(), 1)

    def test_refresh_interval_prefers_environment_override(self) -> None:
        with patch.dict(os.environ, {"REFRESH_INTERVAL_SECONDS": "7"}, clear=True):
            self.assertEqual(stream_cache.get_refresh_interval_seconds(), 7)

    def test_optional_market_fields_keep_missing_semantics(self) -> None:
        payload = {
            "facility_code": "A2",
            "facility_name": "Beta",
            "lat": -33.1,
            "lng": 151.1,
            "timestamp": "2026-07-03T00:05:00+10:00",
            "power_value": 20.0,
            "emission_value": 8.0,
            "state": "NSW",
            "fuel_list": "Gas",
        }

        record = task4._normalize_message(payload, "topic/test")
        self.assertIsNotNone(record)
        self.assertIsNone(record["price_per_mwh"])
        self.assertIsNone(record["demand_mw"])

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

    def test_load_fallback_messages_normalizes_sample_rows(self) -> None:
        sample = pd.DataFrame(
            [
                {
                    "timestamp": "2026-07-03 00:00:00",
                    "Power (MW)": 10.0,
                    "Emissions (tonnes)": 2.5,
                    "facility_code": "A1",
                    "Price ($/MWh)": 30.0,
                    "Demand (MW)": 40.0,
                    "facility_name": "Alpha",
                    "lat": -33.0,
                    "lng": 151.0,
                    "state": "NSW",
                    "fuel_list": "Gas",
                }
            ]
        )

        with patch.object(task4.pd, "read_csv", return_value=sample):
            records = task4._load_fallback_messages(limit=10)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["topic"], "fallback/sample_replay")
        self.assertEqual(records[0]["power_value"], 10.0)
        self.assertEqual(records[0]["emission_value"], 2.5)
        self.assertEqual(records[0]["price_per_mwh"], 30.0)
        self.assertEqual(records[0]["demand_mw"], 40.0)

    def test_should_use_fallback_when_cache_missing_or_stale(self) -> None:
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = None

        self.assertTrue(task4._should_use_fallback(runtime))

        runtime.cache.last_updated_at.return_value = 10_000.0
        with patch.object(task4.time, "time", return_value=10_010.0):
            self.assertFalse(task4._should_use_fallback(runtime))
        with patch.object(task4.time, "time", return_value=10_100.0):
            self.assertTrue(task4._should_use_fallback(runtime))

    def test_load_fallback_messages_skips_sort_when_timestamps_are_all_invalid(self) -> None:
        sample = pd.DataFrame(
            [
                {
                    "timestamp": "not-a-date",
                    "Power (MW)": 10.0,
                    "facility_code": "A1",
                    "facility_name": "Alpha",
                    "lat": -33.0,
                    "lng": 151.0,
                    "state": "NSW",
                    "fuel_list": "Gas",
                }
            ]
        )

        with patch.object(task4.pd, "read_csv", return_value=sample):
            records = task4._load_fallback_messages(limit=10)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["timestamp"], "not-a-date")

    def test_render_header_no_longer_emits_data_source_status(self) -> None:
        stats = {
            "total_power": 30.0,
            "total_emission": 8.0,
            "median_price": 30.0,
            "median_demand": 5.0,
        }
        column_mocks = [Mock(), Mock(), Mock(), Mock()]
        for column in column_mocks:
            column.__enter__ = Mock(return_value=column)
            column.__exit__ = Mock(return_value=None)

        with patch.object(task4.st, "title"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info") as info_mock, \
            patch.object(task4.st, "success") as success_mock, \
            patch.object(task4.st, "columns", return_value=column_mocks), \
            patch.object(task4.st, "metric"):
            task4._render_header(Mock(), stats, {})

        info_mock.assert_not_called()
        success_mock.assert_not_called()

    def test_render_sidebar_emits_fallback_status_and_keeps_transport_status(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connecting")

        with patch.dict(task4.st.session_state, {"display_mode": "power_value"}, clear=True), \
            patch.object(task4.st, "header"), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "button", return_value=False), \
            patch.object(task4.st, "selectbox"), \
            patch.object(task4.st, "write"), \
            patch.object(task4.st, "json"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info") as info_mock, \
            patch.object(task4.st, "success") as success_mock, \
            patch.object(task4.st, "warning") as warning_mock, \
            patch.object(task4.st, "error") as error_mock:
            task4._render_sidebar(runtime, {}, {}, "fallback")

        info_mock.assert_any_call("Waiting for MQTT messages. Showing sample replay fallback.")
        info_mock.assert_any_call("Connecting")
        success_mock.assert_not_called()
        warning_mock.assert_not_called()
        error_mock.assert_not_called()

    def test_render_sidebar_emits_live_status_and_keeps_transport_status(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")

        with patch.dict(task4.st.session_state, {"display_mode": "power_value"}, clear=True), \
            patch.object(task4.st, "header"), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "button", return_value=False), \
            patch.object(task4.st, "selectbox"), \
            patch.object(task4.st, "write"), \
            patch.object(task4.st, "json"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info") as info_mock, \
            patch.object(task4.st, "success") as success_mock, \
            patch.object(task4.st, "warning") as warning_mock, \
            patch.object(task4.st, "error") as error_mock:
            task4._render_sidebar(runtime, {}, {}, "live")

        success_mock.assert_any_call("Live MQTT stream active")
        success_mock.assert_any_call("Connected")
        info_mock.assert_not_called()
        warning_mock.assert_not_called()
        error_mock.assert_not_called()
