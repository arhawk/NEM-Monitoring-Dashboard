from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
        runtime.last_soft_reset_at = datetime(2026, 7, 3, 23, 56, 37, tzinfo=timezone.utc)
        runtime.cache.messages_since_reset.return_value = 3
        runtime.cache.size.return_value = 2
        runtime.cache.max_size.return_value = 100
        runtime.cache.last_updated_at.return_value = None
        runtime.cache.last_reset_at.return_value = None
        return runtime

    def test_soft_reset_clears_current_cache_and_updates_timestamp(self) -> None:
        runtime = Mock()
        runtime.status = "Connected"
        runtime.last_error = "stale error"
        runtime.last_soft_reset_at = datetime(2026, 7, 3, 23, 56, 37, tzinfo=timezone.utc)
        runtime.cache = stream_cache.StreamCache(maxlen=10)
        runtime._set_status = Mock()
        runtime._schedule_connect = Mock()

        runtime.cache.add_message({"facility_code": "A1"})
        previous_reset_at = runtime.cache.last_reset_at()
        previous_soft_reset_at = runtime.last_soft_reset_at
        task4._soft_reset_runtime(runtime)

        self.assertEqual(runtime.cache.size(), 0)
        self.assertEqual(runtime.cache.messages_since_reset(), 0)
        self.assertIsNone(runtime.cache.last_updated_at())
        self.assertGreater(runtime.cache.last_reset_at(), previous_reset_at)
        self.assertIsNone(runtime.last_error)
        self.assertNotEqual(runtime.last_soft_reset_at, previous_soft_reset_at)
        runtime._set_status.assert_not_called()
        runtime._schedule_connect.assert_not_called()

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
        self.assertEqual(record["fuel_group"], "Fossil / Non-renewable")
        self.assertIsNone(record["emission_value"])
        self.assertIsNone(record["price_per_mwh"])
        self.assertIsNone(record["demand_mw"])

    def test_normalize_message_rejects_non_finite_coordinates(self) -> None:
        payload = {
            "facility_code": "A1",
            "facility_name": "Alpha",
            "lat": float("nan"),
            "lng": 151.0,
            "timestamp": "2026-07-03T00:00:00+10:00",
            "power_value": 12.0,
            "state": "NSW",
            "fuel_list": "Gas",
        }

        self.assertIsNone(task4._normalize_message(payload, "topic/test"))

    def test_classify_fuel_group_covers_four_way_mapping(self) -> None:
        self.assertEqual(task4._classify_fuel_group("['Solar', 'Wind', 'Solar']"), "Renewable")
        self.assertEqual(task4._classify_fuel_group("['Black Coal']"), "Fossil / Non-renewable")
        self.assertEqual(task4._classify_fuel_group("['Battery']"), "Storage")
        self.assertEqual(task4._classify_fuel_group("['Gas', 'Solar']"), "Mixed / Other")

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

    def test_get_cached_marker_payload_reuses_payload_for_same_signature(self) -> None:
        records = {
            "A1": {
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "facility_name": "Alpha",
                "timestamp": "2026-07-03T00:00:00+10:00",
                "power_value": 10.0,
                "emission_value": 2.0,
                "price_per_mwh": 30.0,
                "demand_mw": 40.0,
            }
        }
        fake_state = {
            "_nem_map_marker_payload_cache": None,
        }

        with patch.object(task4.st, "session_state", fake_state), \
            patch.object(task4, "_build_marker_payload", wraps=task4._build_marker_payload) as build_mock:
            payload1 = task4._get_cached_marker_payload(records, "power_value", "All", "All")
            payload2 = task4._get_cached_marker_payload(records, "power_value", "All", "All")

        self.assertIs(payload1, payload2)
        self.assertEqual(build_mock.call_count, 1)
        self.assertIn("_nem_map_marker_payload_cache", fake_state)

    def test_get_cached_marker_payload_invalidates_on_signature_change(self) -> None:
        base = {
            "A1": {
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "facility_name": "Alpha",
                "timestamp": "2026-07-03T00:00:00+10:00",
                "power_value": 10.0,
                "emission_value": 2.0,
                "price_per_mwh": 30.0,
                "demand_mw": 40.0,
            }
        }
        updated = {
            "A1": {
                **base["A1"],
                "emission_value": 5.0,
                "timestamp": "2026-07-03T00:05:00+10:00",
            }
        }
        fake_state = {}

        with patch.object(task4.st, "session_state", fake_state), \
            patch.object(task4, "_build_marker_payload", wraps=task4._build_marker_payload) as build_mock:
            payload1 = task4._get_cached_marker_payload(base, "power_value", "All", "All")
            payload2 = task4._get_cached_marker_payload(updated, "power_value", "All", "All")

        self.assertIsNot(payload1, payload2)
        self.assertEqual(build_mock.call_count, 2)

    def test_build_fuel_options_uses_all_tokens_from_snapshot(self) -> None:
        snapshot = {
            "A1": {
                "fuel_list": "['Gas', 'Solar']",
            },
            "A2": {
                "fuel_list": "['Battery']",
            },
            "A3": {
                "fuel_list": "['Wind', 'Solar']",
            },
        }

        self.assertEqual(
            task4._build_fuel_options(snapshot),
            ["All", "Battery", "Gas", "Solar", "Wind"],
        )

    def test_filter_snapshot_uses_raw_fuel_tokens(self) -> None:
        snapshot = {
            "A1": {
                "state": "NSW",
                "fuel_list": "['Gas', 'Solar']",
                "fuel_group": "Mixed / Other",
            },
            "A2": {
                "state": "NSW",
                "fuel_list": "['Solar']",
                "fuel_group": "Renewable",
            },
        }

        filtered = task4._filter_snapshot(snapshot, "Gas", "NSW")
        self.assertEqual(list(filtered.keys()), ["A1"])

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
        self.assertEqual(payload["markers"][0]["facility_name"], "Alpha")
        self.assertEqual(payload["markers"][0]["fuel_group"], "Fossil / Non-renewable")
        self.assertEqual(payload["markers"][0]["power_value"], 10.0)
        self.assertEqual(payload["markers"][0]["emission_value"], 2.0)
        self.assertEqual(payload["markers"][0]["fingerprint"][0], 10.0)
        self.assertGreater(payload["markers"][0]["radius"], 5.5)

    def test_marker_payload_skips_records_with_invalid_coordinates(self) -> None:
        records = {
            "A1": {
                "facility_code": "A1",
                "facility_name": "Alpha",
                "lat": float("nan"),
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "timestamp": "2026-07-03T00:00:00+10:00",
                "power_value": 10.0,
                "emission_value": 2.0,
                "price_per_mwh": 30.0,
                "demand_mw": 40.0,
            },
            "A2": {
                "facility_code": "A2",
                "facility_name": "Beta",
                "lat": -34.0,
                "lng": 150.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "timestamp": "2026-07-03T00:05:00+10:00",
                "power_value": 12.0,
                "emission_value": 3.0,
                "price_per_mwh": 31.0,
                "demand_mw": 41.0,
            },
        }

        payload = task4._build_marker_payload(records, "power_value", "All", "All")
        self.assertEqual([marker["facility_code"] for marker in payload["markers"]], ["A2"])

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

    def test_max_stream_rows_defaults_to_five_thousand_five_hundred_twenty(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stream_cache.get_max_stream_rows(), 5520)

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
            patch.object(task4.st, "markdown"), \
            patch.object(task4.st, "header"), \
            patch.object(task4.st, "subheader") as subheader_mock, \
            patch.object(task4.st, "button", return_value=False), \
            patch.object(task4.st, "selectbox"), \
            patch.object(task4.st, "write") as write_mock, \
            patch.object(task4.st, "json"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info") as info_mock, \
            patch.object(task4.st, "success") as success_mock, \
            patch.object(task4.st, "warning") as warning_mock, \
            patch.object(task4.st, "error") as error_mock:
            task4._render_sidebar(runtime, {}, {}, "fallback", ["All", "Gas"])

        self.assertGreaterEqual(len(subheader_mock.call_args_list), 1)
        self.assertEqual(
            [call.args[0] for call in subheader_mock.call_args_list[:5]],
            [
                "MQTT Status",
                "Grid Region Filter",
                "Fuel Type Filter",
                "Data Statistics",
            ],
        )
        write_lines = [str(call.args[0]) for call in write_mock.call_args_list]
        self.assertLess(
            next(i for i, line in enumerate(write_lines) if line.startswith("Messages since reset:")),
            next(i for i, line in enumerate(write_lines) if line.startswith("MQTT cache size:")),
        )
        info_mock.assert_any_call("Waiting for cache messages. Showing sample replay fallback.")
        info_mock.assert_any_call("Connecting")
        success_mock.assert_not_called()
        warning_mock.assert_not_called()
        error_mock.assert_not_called()

    def test_render_sidebar_no_longer_renders_latest_message_block(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")
        filtered_snapshot = {
            "A1": {"facility_code": "A1"},
            "A2": {"facility_code": "A2"},
        }

        with patch.dict(task4.st.session_state, {"display_mode": "power_value", "selected_fuel": "All", "selected_region": "All"}, clear=True), \
            patch.object(task4.st, "markdown"), \
            patch.object(task4.st, "header"), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "button", return_value=False), \
            patch.object(task4.st, "selectbox"), \
            patch.object(task4.st, "write") as write_mock, \
            patch.object(task4.st, "caption") as caption_mock, \
            patch.object(task4.st, "json") as json_mock, \
            patch.object(task4.st, "info"), \
            patch.object(task4.st, "success"), \
            patch.object(task4.st, "warning"), \
            patch.object(task4.st, "error"):
            task4._render_sidebar(runtime, {}, filtered_snapshot, "live", ["All", "Gas"])

        runtime.cache.get_latest_message.assert_not_called()
        json_mock.assert_not_called()
        self.assertFalse(any("No MQTT messages have arrived yet." in str(call.args[0]) for call in write_mock.call_args_list))
        caption_mock.assert_any_call("2 facilities selected")
        self.assertTrue(any(str(call.args[0]) == "2 facilities selected" for call in caption_mock.call_args_list))

    def test_render_sidebar_reset_button_triggers_soft_reset_and_shows_timestamp_after_button(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")
        updated_reset_at = datetime(2026, 7, 4, 1, 2, 3, tzinfo=timezone.utc)

        def soft_reset_side_effect(runtime_obj):
            runtime.last_soft_reset_at = updated_reset_at
            runtime_obj.last_soft_reset_at = updated_reset_at

        with patch.dict(task4.st.session_state, {"display_mode": "power_value", "selected_fuel": "All", "selected_region": "All"}, clear=True), \
            patch.object(task4.st, "markdown"), \
            patch.object(task4.st, "header"), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "button", return_value=True) as button_mock, \
            patch.object(task4.st, "selectbox"), \
            patch.object(task4.st, "write") as write_mock, \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "json"), \
            patch.object(task4.st, "info"), \
            patch.object(task4.st, "success"), \
            patch.object(task4.st, "warning"), \
            patch.object(task4.st, "error"), \
            patch.object(task4, "_soft_reset_runtime", side_effect=soft_reset_side_effect) as soft_reset_mock, \
            patch.object(task4.st, "rerun") as rerun_mock:
            task4._render_sidebar(runtime, {}, {}, "live", ["All", "Gas"])

        button_mock.assert_called_once_with("Reset Cache", key="reset_cache")
        soft_reset_mock.assert_called_once()
        rerun_mock.assert_not_called()
        self.assertIn(
            f"Last soft reset: {task4._format_ts(updated_reset_at.timestamp())}",
            [str(call.args[0]) for call in write_mock.call_args_list],
        )

    def test_render_sidebar_shows_ready_notice_once_after_fallback(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")

        class FakeSessionState(dict):
            def __getattr__(self, key: str):
                return self[key]

            def __setattr__(self, key: str, value):
                self[key] = value

        state = FakeSessionState(
            display_mode="power_value",
            selected_fuel="All",
            selected_region="All",
            **{task4.READY_NOTICE_SESSION_KEY: True},
        )

        with patch.object(task4.st, "session_state", state), \
            patch.object(task4.st, "markdown"), \
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
            task4._render_sidebar(runtime, {}, {}, "live", ["All", "Gas"])

        success_mock.assert_any_call("Real-time data ready")
        self.assertFalse(state[task4.READY_NOTICE_SESSION_KEY])
        info_mock.assert_not_called()
        warning_mock.assert_not_called()
        error_mock.assert_not_called()

        success_mock.reset_mock()
        info_mock.reset_mock()
        warning_mock.reset_mock()
        error_mock.reset_mock()

        with patch.object(task4.st, "session_state", state), \
            patch.object(task4.st, "markdown"), \
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
            task4._render_sidebar(runtime, {}, {}, "live", ["All", "Gas"])

        success_mock.assert_any_call("Connected")
        self.assertNotIn("Real-time data ready", [call.args[0] for call in success_mock.call_args_list])
        info_mock.assert_not_called()
        warning_mock.assert_not_called()
        error_mock.assert_not_called()

    def test_main_calls_render_dashboard_without_manual_rerun_loop(self) -> None:
        with patch.object(task4, "render_dashboard") as render_mock, \
            patch.object(task4.time, "sleep") as sleep_mock, \
            patch.object(task4.st, "rerun") as rerun_mock:
            task4.main()

        render_mock.assert_called_once()
        sleep_mock.assert_not_called()
        rerun_mock.assert_not_called()

    def test_render_sidebar_injects_compact_header_css(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")

        with patch.dict(task4.st.session_state, {"display_mode": "power_value", "selected_fuel": "All", "selected_region": "All"}, clear=True), \
            patch.object(task4.st, "markdown") as markdown_mock, \
            patch.object(task4.st, "header"), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "button", return_value=False), \
            patch.object(task4.st, "selectbox"), \
            patch.object(task4.st, "write"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info"), \
            patch.object(task4.st, "success"), \
            patch.object(task4.st, "warning"), \
            patch.object(task4.st, "error"):
            task4._render_sidebar(runtime, {}, {}, "live", ["All", "Gas"])

        self.assertTrue(markdown_mock.called)
        css = markdown_mock.call_args_list[0].args[0]
        self.assertIn('data-testid="stSidebarHeader"', css)
        self.assertIn('data-testid="stSidebarCollapseButton"', css)
        self.assertIn("Control Center", css)
        self.assertIn("font-size: 1.25rem", css)
        self.assertIn("margin-bottom: 0 !important", css)
        self.assertIn("overflow-y: hidden !important", css)
        self.assertIn("margin-top: 0 !important", css)

    def test_render_map_syncs_display_mode_from_component_value(self) -> None:
        filtered_snapshot = {
            "A1": {
                "facility_code": "A1",
                "facility_name": "Alpha",
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "power_value": 10.0,
                "emission_value": 2.0,
                "price_per_mwh": 30.0,
                "demand_mw": 40.0,
                "timestamp": "2026-07-03T00:00:00+10:00",
                "fuel_group": "Fossil / Non-renewable",
            }
        }

        class FakeSessionState(dict):
            def __getattr__(self, key: str):
                return self[key]

            def __setattr__(self, key: str, value):
                self[key] = value

        fake_state = FakeSessionState(
            display_mode="power_value",
            selected_fuel="All",
            selected_region="All",
        )

        with patch.object(task4.st, "session_state", fake_state), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info"), \
            patch.object(task4, "render_nem_facility_map", return_value={"display_mode": "emission_value"}) as render_mock:
            task4._render_map(filtered_snapshot, "power_value")

        self.assertEqual(fake_state["display_mode"], "emission_value")
        render_mock.assert_called_once()

    def test_render_map_ignores_view_state_only_component_value(self) -> None:
        filtered_snapshot = {
            "A1": {
                "facility_code": "A1",
                "facility_name": "Alpha",
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "Gas",
                "power_value": 10.0,
                "emission_value": 2.0,
                "price_per_mwh": 30.0,
                "demand_mw": 40.0,
                "timestamp": "2026-07-03T00:00:00+10:00",
                "fuel_group": "Fossil / Non-renewable",
            }
        }

        class FakeSessionState(dict):
            def __getattr__(self, key: str):
                return self[key]

            def __setattr__(self, key: str, value):
                self[key] = value

        fake_state = FakeSessionState(
            display_mode="power_value",
            selected_fuel="All",
            selected_region="All",
        )

        with patch.object(task4.st, "session_state", fake_state), \
            patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info"), \
            patch.object(task4, "render_nem_facility_map", return_value={"center": {"lat": -33.0, "lng": 151.0}, "zoom": 6}) as render_mock:
            task4._render_map(filtered_snapshot, "power_value")

        self.assertEqual(fake_state["display_mode"], "power_value")
        render_mock.assert_called_once()
