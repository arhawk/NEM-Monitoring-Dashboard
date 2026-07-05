from __future__ import annotations

import importlib
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
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


from src.dashboard import app as dashboard_app
from src.dashboard import actions as dashboard_actions
from src.dashboard import data as dashboard_data
from src.dashboard.components import nem_map_component as dashboard_nem_map_component
from src.dashboard.views import header as dashboard_header_view
from src.dashboard import render as dashboard_render
from src.dashboard import render_context as dashboard_render_context
from src.dashboard import settings as dashboard_settings
from src.dashboard.views import map as dashboard_map_payload
from src.dashboard.views import sidebar as dashboard_sidebar_view
from src.dashboard.views import table as dashboard_table_view
from src.dashboard import runtime as dashboard_runtime
from src.publisher import cli as publisher_cli
from src.publisher.data import assignment1 as task_a1_cleaning
from src.publisher.data import cleaning as task13_cleaning
from src.publisher.publish import mqtt_publish as task13_mqtt
from src.shared import stream_cache

task4 = SimpleNamespace()
for module in (
    dashboard_render,
    dashboard_data,
    dashboard_header_view,
    dashboard_sidebar_view,
    dashboard_map_payload,
    dashboard_runtime,
    dashboard_render_context,
    dashboard_table_view,
):
    for name in getattr(module, "__all__", []):
        setattr(task4, name, getattr(module, name))
task4.st = dashboard_render_context.compat_st
task4.pd = pd
task4.components = dashboard_header_view.components
task4.render_nem_facility_map = dashboard_nem_map_component.render_nem_facility_map
task4.get_runtime = dashboard_runtime.get_runtime
task4.set_active_runtime = dashboard_runtime.set_active_runtime
task4.render_dashboard = dashboard_render.render_dashboard
task4.main = dashboard_app.main


class FakeSessionState(dict):
    def __getattr__(self, key: str):
        return self[key]

    def __setattr__(self, key: str, value):
        self[key] = value


class PublishLogicTests(TestCase):
    def test_legacy_publisher_wrapper_import_is_side_effect_free(self) -> None:
        module_path = ROOT / "scripts" / "run_publisher.py"
        with patch("src.publisher.cli.main") as main_mock:
            spec = importlib.util.spec_from_file_location("publisher_wrapper", module_path)
            if spec is None or spec.loader is None:
                self.fail(f"Unable to load module from {module_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules["publisher_wrapper"] = module
            spec.loader.exec_module(module)

        main_mock.assert_not_called()

    def test_dashboard_wrapper_import_is_side_effect_free(self) -> None:
        module_path = ROOT / "app" / "streamlit_app.py"
        with patch("src.dashboard.app.main") as main_mock:
            spec = importlib.util.spec_from_file_location("dashboard_wrapper", module_path)
            if spec is None or spec.loader is None:
                self.fail(f"Unable to load module from {module_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules["dashboard_wrapper"] = module
            spec.loader.exec_module(module)

        main_mock.assert_not_called()

    def test_normalize_non_negative_replaces_negative_values_only(self) -> None:
        series = pd.Series([5.0, -3.0, None, 0.0, -1.5], name="Power (MW)")
        cleaned = task13_cleaning.normalize_non_negative(series)
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
        result = task13_cleaning.handle_missing_values_fast(group)
        self.assertTrue(result.empty)

    def test_fill_missing_half_ffill_bfill_keeps_partial_gap_semantics(self) -> None:
        series = pd.Series([1.0, None, None, 4.0], name="Power (MW)")
        cleaned = task13_cleaning.fill_missing_half_ffill_bfill(series)
        self.assertEqual(cleaned.iloc[1], 1.0)
        self.assertEqual(cleaned.iloc[2], 4.0)

    def test_clean_nger_data_applies_assignment1_filters(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "reportingEntity": "Alpha",
                    "facilityName": "Good Facility",
                    "type": "F",
                    "state": "NSW",
                    "electricityProductionGJ": 1.0,
                    "electricityProductionMwh": 2.0,
                    "scope1tCO2e": 3.0,
                    "scope2tCO2e": 4.0,
                    "totalEmissionstCO2e": 5.0,
                    "emissionIntensitytMwh": 6.0,
                    "gridConnected": "On",
                    "grid": "NEM",
                    "primaryFuel": "Wind",
                    "importantNotes": None,
                    "year": 2025,
                },
                {
                    "reportingEntity": "Beta",
                    "facilityName": "Drop Notes",
                    "type": "F",
                    "state": "NSW",
                    "electricityProductionGJ": 1.0,
                    "electricityProductionMwh": 2.0,
                    "scope1tCO2e": 3.0,
                    "scope2tCO2e": 4.0,
                    "totalEmissionstCO2e": 5.0,
                    "emissionIntensitytMwh": 6.0,
                    "gridConnected": "On",
                    "grid": "NEM",
                    "primaryFuel": "Solar",
                    "importantNotes": "note",
                    "year": 2025,
                },
                {
                    "reportingEntity": "Gamma",
                    "facilityName": "Drop Total",
                    "type": "C",
                    "state": "NSW",
                    "electricityProductionGJ": 1.0,
                    "electricityProductionMwh": 2.0,
                    "scope1tCO2e": 3.0,
                    "scope2tCO2e": 4.0,
                    "totalEmissionstCO2e": 5.0,
                    "emissionIntensitytMwh": 6.0,
                    "gridConnected": "On",
                    "grid": "NEM",
                    "primaryFuel": "Coal",
                    "importantNotes": None,
                    "year": 2025,
                },
            ]
        )

        cleaned = task_a1_cleaning.clean_nger_data(df)

        self.assertEqual(cleaned.shape[0], 1)
        self.assertListEqual(
            cleaned.columns.tolist(),
            [
                "facilityName",
                "type",
                "state",
                "electricityProductionMwh",
                "scope1tCO2e",
                "scope2tCO2e",
                "totalEmissionstCO2e",
                "emissionIntensitytMwh",
                "primaryFuel",
                "year",
            ],
        )
        self.assertEqual(cleaned.iloc[0]["facilityName"], "Good Facility")

    def test_clean_cer_data_normalizes_station_name_and_year(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "powerStation": "Laura Johnson Home, Townview - Solar w SGU - QLD",
                    "state": "QLD",
                    "postcode": 4825,
                    "MWCapacity": 0.2265,
                    "fuelSource": "Solar",
                    "Accreditation start date": "2024-10-15",
                    "Approval date": "2025-01-13",
                    "inSheet": "Approved",
                    "Committed Date (Month/Year)": None,
                },
                {
                    "powerStation": "Leppington - Solar - NSW",
                    "state": "NSW",
                    "postcode": 2179,
                    "MWCapacity": 0.732,
                    "fuelSource": "Solar",
                    "Accreditation start date": "2024-11-22",
                    "Approval date": "2025-01-13",
                    "inSheet": "Approved",
                    "Committed Date (Month/Year)": None,
                },
            ]
        )

        cleaned = task_a1_cleaning.clean_cer_data(df)

        self.assertListEqual(
            cleaned.columns.tolist(),
            ["powerStation", "state", "postcode", "MWCapacity", "fuelSource", "year"],
        )
        self.assertEqual(cleaned.iloc[0]["powerStation"], "Laura Johnson Home, Townview")
        self.assertEqual(cleaned.iloc[0]["year"], 2025)
        self.assertEqual(cleaned.iloc[1]["year"], 2025)

    def test_load_assignment1_csv_falls_back_to_staged_data(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            staged_root = Path(temp_dir)
            staged_path = staged_root / "assignment1" / "NGER_data_clean.csv"
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {"facilityName": "Alpha", "lat": -33.0, "lng": 151.0},
                ]
            ).to_csv(staged_path, index=False)

            missing_clean_path = Path("/tmp/nonexistent-assignment1/NGER_data_clean.csv")
            with patch.object(
                task_a1_cleaning,
                "staging_data_path",
                side_effect=lambda *parts: staged_root.joinpath(*parts),
            ):
                loaded = task_a1_cleaning.load_assignment1_csv(missing_clean_path)

        self.assertIn("lat", loaded.columns)
        self.assertIn("lng", loaded.columns)
        self.assertEqual(len(loaded), 1)

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
        client.publish.return_value = DummyInfo(task13_mqtt.mqtt.MQTT_ERR_SUCCESS, True)
        self.assertTrue(task13_mqtt.safe_publish_stream(client, "topic", {"x": 1}))
        client.publish.return_value = DummyInfo(task13_mqtt.mqtt.MQTT_ERR_SUCCESS, False)
        self.assertFalse(task13_mqtt.safe_publish_stream(client, "topic", {"x": 1}))

    def test_publisher_client_uses_tls_when_enabled(self) -> None:
        client = Mock()
        with patch.object(task13_mqtt, "MQTT_TLS", True), \
            patch.object(task13_mqtt.mqtt, "Client", return_value=client):
            task13_mqtt.make_client()

        client.tls_set.assert_called_once()
        client.connect.assert_called_once_with(task13_mqtt.BROKER, task13_mqtt.PORT, keepalive=60)

    def test_publisher_client_uses_online_mqtt_env_with_tls(self) -> None:
        client = Mock()
        with patch.dict(
            os.environ,
            {
                "MQTT_BROKER": "s1.eu.hivemq.cloud",
                "MQTT_PORT": "8883",
                "MQTT_TLS": "true",
                "MQTT_BROKER_HOST": "",
                "MQTT_BROKER_PORT": "",
            },
            clear=False,
        ):
            online_mqtt = load_module("task13_mqtt_online", "src/publisher/publish/mqtt_publish.py")

        with patch.object(online_mqtt.mqtt, "Client", return_value=client):
            online_mqtt.make_client()

        client.tls_set.assert_called_once()
        client.connect.assert_called_once_with("s1.eu.hivemq.cloud", 8883, keepalive=60)

    def test_publish_topic_template_defaults_to_measurements_path(self) -> None:
        self.assertEqual(
            task13_mqtt.PUBLISH_TOPIC_TEMPLATE,
            "comp5339/task123/measurements/{facility_code}",
        )

    def test_publisher_main_skips_data_prep_when_publish_csv_exists(self) -> None:
        publish_path = Mock()
        publish_path.exists.return_value = True

        with patch.object(publisher_cli, "PUBLISH_PATH", publish_path), \
            patch.object(publisher_cli, "prepare_data_artifacts") as prepare_mock, \
            patch.object(publisher_cli, "run_publisher_loop") as run_mock:
            publisher_cli.main()

        prepare_mock.assert_not_called()
        run_mock.assert_called_once_with(publish_path)

    def test_publisher_main_prepares_data_when_publish_csv_missing(self) -> None:
        publish_path = Mock()
        publish_path.exists.return_value = False

        with patch.object(publisher_cli, "PUBLISH_PATH", publish_path), \
            patch.object(publisher_cli, "prepare_data_artifacts") as prepare_mock, \
            patch.object(publisher_cli, "run_publisher_loop") as run_mock:
            publisher_cli.main()

        prepare_mock.assert_called_once()
        run_mock.assert_called_once_with(publish_path)

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

        with patch.object(task13_mqtt, "safe_publish_stream", return_value=False) as publish_mock, \
            patch.object(task13_mqtt, "sleep_until_ns", return_value=None), \
            patch.object(task13_mqtt, "perf_counter_ns", return_value=0):
            task13_mqtt.publish_new_since(Mock(), rows, state)

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

        with patch.object(task13_mqtt, "safe_publish_stream", return_value=True), \
            patch.object(task13_mqtt, "sleep_until_ns", return_value=None), \
            patch.object(task13_mqtt, "perf_counter_ns", return_value=0):
            task13_mqtt.publish_new_since(Mock(), rows, state)

        self.assertEqual(state["seq"], 1)
        self.assertEqual(state["last_fac"], "A1")
        self.assertEqual(state["last_ts"], rows[0]["_ts_dt"])

    def test_publish_new_since_stops_when_deadline_hits_mid_batch(self) -> None:
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

        with patch.object(task13_mqtt, "safe_publish_stream", return_value=True) as publish_mock, \
            patch.object(task13_mqtt, "sleep_until_ns", return_value=None), \
            patch.object(task13_mqtt, "perf_counter_ns", side_effect=[
                0, 0, 0, 0, 10, 120_000_000, 120_000_000,
            ]):
            keep_running = task13_mqtt.publish_new_since(Mock(), rows, state, deadline_ns=150_000_000)

        self.assertFalse(keep_running)
        self.assertEqual(state["seq"], 1)
        self.assertEqual(state["last_fac"], "A1")
        self.assertEqual(state["last_ts"], rows[0]["_ts_dt"])
        self.assertEqual(publish_mock.call_count, 1)

    def test_publish_new_since_formats_concrete_topic_from_template(self) -> None:
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

        with patch.object(task13_mqtt, "safe_publish_stream", return_value=True) as publish_mock, \
            patch.object(task13_mqtt, "sleep_until_ns", return_value=None), \
            patch.object(task13_mqtt, "perf_counter_ns", return_value=0):
            task13_mqtt.publish_new_since(Mock(), rows, state)

        self.assertEqual(publish_mock.call_args[0][1], "comp5339/task123/measurements/A1")

    def test_run_publisher_loop_exits_cleanly_in_timed_mode(self) -> None:
        client = Mock()

        with patch.object(task13_mqtt, "make_client", return_value=client), \
            patch.object(task13_mqtt, "wait_for_connection", return_value=True), \
            patch.object(task13_mqtt, "load_measure_rows", return_value=[]), \
            patch.object(task13_mqtt, "publish_new_since") as publish_mock, \
            patch.object(task13_mqtt.time, "sleep", return_value=None), \
            patch.object(task13_mqtt, "perf_counter_ns", side_effect=[0, 0, 2_000_000_000]):
            task13_mqtt.run_publisher_loop(Mock(), poll_seconds=5, duration_seconds=1)

        self.assertGreaterEqual(publish_mock.call_count, 1)
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_run_publisher_loop_breaks_when_helper_reports_timeout(self) -> None:
        client = Mock()

        with patch.object(task13_mqtt, "make_client", return_value=client), \
            patch.object(task13_mqtt, "wait_for_connection", return_value=True), \
            patch.object(task13_mqtt, "load_measure_rows", return_value=[]), \
            patch.object(task13_mqtt, "publish_new_since", return_value=False) as publish_mock, \
            patch.object(task13_mqtt.time, "sleep", return_value=None) as sleep_mock, \
            patch.object(task13_mqtt, "perf_counter_ns", side_effect=[0, 0]):
            task13_mqtt.run_publisher_loop(Mock(), poll_seconds=5, duration_seconds=1)

        publish_mock.assert_called_once()
        sleep_mock.assert_not_called()
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_run_publisher_loop_keeps_infinite_mode_when_duration_unset(self) -> None:
        client = Mock()

        with patch.object(task13_mqtt, "make_client", return_value=client), \
            patch.object(task13_mqtt, "wait_for_connection", return_value=True), \
            patch.object(task13_mqtt, "load_measure_rows", return_value=[]), \
            patch.object(task13_mqtt, "publish_new_since") as publish_mock, \
            patch.object(task13_mqtt.time, "sleep", side_effect=SystemExit) as sleep_mock, \
            patch.object(task13_mqtt, "perf_counter_ns", return_value=0):
            with self.assertRaises(SystemExit):
                task13_mqtt.run_publisher_loop(Mock(), poll_seconds=7, duration_seconds=0)

        publish_mock.assert_called_once()
        sleep_mock.assert_called_once_with(7)
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_run_publisher_loop_reports_broker_refusal_without_traceback(self) -> None:
        with patch.object(task13_mqtt, "BROKER", "127.0.0.1"), \
            patch.object(task13_mqtt, "PORT", 1883), \
            patch.object(task13_mqtt, "make_client", side_effect=ConnectionRefusedError("refused")), \
            patch.object(task13_mqtt, "wait_for_connection") as wait_mock, \
            patch.object(task13_mqtt, "print") as print_mock:
            with self.assertRaises(SystemExit) as ctx:
                task13_mqtt.run_publisher_loop(Mock(), poll_seconds=5, duration_seconds=1)

        self.assertEqual(ctx.exception.code, 1)
        wait_mock.assert_not_called()
        print_mock.assert_any_call("[Main] MQTT connect failed for 127.0.0.1:1883: refused")


class GitHubActionsControlTests(TestCase):
    def _response(self, status_code: int, payload: dict | None = None, text: str = "") -> Mock:
        response = Mock()
        response.status_code = status_code
        response.text = text
        response.json.return_value = payload or {}
        return response

    def test_auto_start_does_not_call_github_when_control_disabled(self) -> None:
        session_state = FakeSessionState()
        with patch.object(dashboard_actions, "ENABLE_GITHUB_ACTIONS_CONTROL", False), \
            patch.object(dashboard_actions.st, "session_state", session_state), \
            patch.object(dashboard_actions.requests, "request") as request_mock:
            result = dashboard_actions.maybe_auto_start_publisher()

        self.assertFalse(result["triggered"])
        self.assertEqual(result["message"], "GitHub Actions control is disabled.")
        request_mock.assert_not_called()

    def test_trigger_publisher_workflow_skips_when_run_is_active(self) -> None:
        session_state = FakeSessionState()
        active_run = {
            "id": 101,
            "status": "in_progress",
            "conclusion": None,
            "created_at": datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc),
            "html_url": "https://example.com/run/101",
            "run_number": 7,
        }
        responses = [self._response(200, {"workflow_runs": [active_run]})]

        with patch.object(dashboard_actions, "ENABLE_GITHUB_ACTIONS_CONTROL", True), \
            patch.object(dashboard_actions, "GITHUB_TOKEN", "token"), \
            patch.object(dashboard_actions.st, "session_state", session_state), \
            patch.object(dashboard_actions.requests, "request", side_effect=responses) as request_mock:
            result = dashboard_actions.trigger_publisher_workflow(duration_seconds=600)

        self.assertFalse(result["triggered"])
        self.assertIn("already in_progress", result["message"])
        self.assertEqual(request_mock.call_count, 1)

    def test_trigger_publisher_workflow_dispatches_when_no_runs_block(self) -> None:
        session_state = FakeSessionState()
        responses = [
            self._response(200, {"workflow_runs": []}),
            self._response(204, None),
        ]

        with patch.object(dashboard_actions, "ENABLE_GITHUB_ACTIONS_CONTROL", True), \
            patch.object(dashboard_actions, "GITHUB_TOKEN", "token"), \
            patch.object(dashboard_actions.st, "session_state", session_state), \
            patch.object(dashboard_actions.requests, "request", side_effect=responses) as request_mock:
            result = dashboard_actions.trigger_publisher_workflow(duration_seconds=600)

        self.assertTrue(result["triggered"])
        self.assertIn("Triggered GitHub Actions publisher", result["message"])
        self.assertEqual(request_mock.call_count, 2)

    def test_auto_start_only_triggers_once_per_session(self) -> None:
        session_state = FakeSessionState()
        responses = [
            self._response(200, {"workflow_runs": []}),
            self._response(204, None),
        ]

        with patch.object(dashboard_actions, "ENABLE_GITHUB_ACTIONS_CONTROL", True), \
            patch.object(dashboard_actions, "AUTO_START_PUBLISHER", True), \
            patch.object(dashboard_actions, "GITHUB_TOKEN", "token"), \
            patch.object(dashboard_actions.st, "session_state", session_state), \
            patch.object(dashboard_actions.requests, "request", side_effect=responses) as request_mock:
            first = dashboard_actions.maybe_auto_start_publisher()
            second = dashboard_actions.maybe_auto_start_publisher()

        self.assertTrue(first["triggered"])
        self.assertTrue(second["triggered"])
        self.assertEqual(second["message"], first["message"])
        self.assertEqual(request_mock.call_count, 2)

    def test_trigger_publisher_workflow_blocks_when_within_cooldown(self) -> None:
        session_state = FakeSessionState()
        now = datetime.now(timezone.utc)
        recent_run = {
            "id": 103,
            "status": "completed",
            "conclusion": "success",
            "created_at": now - timedelta(seconds=30),
            "html_url": "https://example.com/run/103",
            "run_number": 9,
        }
        responses = [self._response(200, {"workflow_runs": [recent_run]})]

        with patch.object(dashboard_actions, "ENABLE_GITHUB_ACTIONS_CONTROL", True), \
            patch.object(dashboard_actions, "AUTO_START_COOLDOWN_SECONDS", 600), \
            patch.object(dashboard_actions, "GITHUB_TOKEN", "token"), \
            patch.object(dashboard_actions.st, "session_state", session_state), \
            patch.object(dashboard_actions.requests, "request", side_effect=responses) as request_mock:
            result = dashboard_actions.trigger_publisher_workflow(duration_seconds=600)

        self.assertFalse(result["triggered"])
        self.assertIn("cooldown window", result["message"])
        self.assertEqual(request_mock.call_count, 1)


class DashboardLogicTests(TestCase):
    def _build_sidebar_runtime(self, status: str = "Connected") -> Mock:
        runtime = Mock()
        runtime.status = status
        runtime.last_error = None
        runtime.last_soft_reset_at = datetime(2026, 7, 3, 23, 56, 37, tzinfo=timezone.utc)
        runtime.cache.messages_since_reset.return_value = 3
        runtime.cache.get_recent_messages.return_value = []
        runtime.cache.size.return_value = 2
        runtime.cache.max_size.return_value = 100
        runtime.cache.last_updated_at.return_value = None
        runtime.cache.last_reset_at.return_value = None
        return runtime

    def test_build_dashboard_context_does_not_touch_connection_state(self) -> None:
        runtime = self._build_sidebar_runtime(status="Disconnected")

        class FakeSessionState(dict):
            def __getattr__(self, key: str):
                return self[key]

            def __setattr__(self, key: str, value):
                self[key] = value

        with patch.object(dashboard_runtime, "get_active_runtime", return_value=runtime), \
            patch.object(dashboard_render_context.compat_st, "session_state", FakeSessionState()):
            context = dashboard_render_context._build_dashboard_context()

        runtime.maybe_soft_reset.assert_not_called()
        runtime.ensure_connection.assert_not_called()
        self.assertEqual(context["data_source"], "empty")

    def test_build_dashboard_context_signature_ignores_messages_since_reset(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")
        runtime.cache.size.return_value = 2
        runtime.cache.last_updated_at.return_value = 100.0
        runtime.cache.last_reset_at.return_value = 456.0

        class FakeSessionState(dict):
            def __getattr__(self, key: str):
                return self[key]

            def __setattr__(self, key: str, value):
                self[key] = value

        with patch.object(dashboard_render_context.compat_st, "session_state", FakeSessionState(display_mode="power_value", selected_fuel="All", selected_region="All")), \
            patch.object(runtime.cache, "last_updated_at", return_value=120.0):
            runtime.cache.messages_since_reset.return_value = 3
            baseline = dashboard_render_context._build_dashboard_context_signature(runtime)
            runtime.cache.messages_since_reset.return_value = 99
            updated = dashboard_render_context._build_dashboard_context_signature(runtime)

        self.assertEqual(baseline, updated)

    def test_build_dashboard_context_uses_live_messages_when_present(self) -> None:
        runtime = self._build_sidebar_runtime(status="Connected")
        runtime.cache.get_recent_messages.return_value = [
            {
                "facility_code": "LIVE1",
                "facility_name": "Live Facility",
                "lat": -33.0,
                "lng": 151.0,
                "timestamp": "2026-07-03T00:00:00+10:00",
                "power_value": 11.0,
                "state": "NSW",
                "fuel_list": "Gas",
            }
        ]
        runtime.cache.last_updated_at.return_value = 100.0

        class FakeSessionState(dict):
            def __getattr__(self, key: str):
                return self[key]

            def __setattr__(self, key: str, value):
                self[key] = value

        with patch.object(dashboard_runtime, "get_active_runtime", return_value=runtime), \
            patch.object(dashboard_render_context.compat_st, "session_state", FakeSessionState()):
            context = dashboard_render_context._build_dashboard_context()

        self.assertEqual(context["data_source"], "live")
        self.assertEqual(list(context["snapshot"].keys()), ["LIVE1"])
        self.assertEqual(context["messages"], runtime.cache.get_recent_messages.return_value)

    def test_mqtt_manager_subscribes_with_explicit_topic_filter(self) -> None:
        runtime = self._build_sidebar_runtime(status="Disconnected")
        client = Mock()
        with patch.object(dashboard_runtime.mqtt.mqtt, "Client", return_value=client):
            manager = dashboard_runtime.MqttConnectionManager(runtime)

        manager._on_connect(client, None, None, 0)

        client.subscribe.assert_called_once_with(dashboard_settings.SUBSCRIBE_TOPIC_FILTER, qos=0)

    def test_dashboard_client_uses_tls_when_enabled(self) -> None:
        runtime = self._build_sidebar_runtime(status="Disconnected")
        client = Mock()
        with patch.object(dashboard_runtime.mqtt, "MQTT_TLS", True), \
            patch.object(dashboard_runtime.mqtt.mqtt, "Client", return_value=client):
            manager = dashboard_runtime.MqttConnectionManager(runtime)
            manager.schedule_connect()

        client.tls_set.assert_called_once()
        client.connect_async.assert_called_once_with(dashboard_settings.BROKER, dashboard_settings.PORT, keepalive=60)

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
            patch.object(dashboard_map_payload, "_build_marker_payload", wraps=dashboard_map_payload._build_marker_payload) as build_mock:
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
            patch.object(dashboard_map_payload, "_build_marker_payload", wraps=dashboard_map_payload._build_marker_payload) as build_mock:
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

    def test_resolve_data_source_uses_live_only_when_live_messages_exist(self) -> None:
        live_messages = [{"facility_code": "A1"}]
        self.assertEqual(task4._resolve_data_source(live_messages), "live")

    def test_resolve_data_source_distinguishes_empty_and_live_states(self) -> None:
        self.assertEqual(task4._resolve_data_source([]), "empty")
        self.assertEqual(task4._resolve_data_source([{"facility_code": "A1"}]), "live")

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

    def test_render_current_trend_shows_empty_state_when_cache_is_stale(self) -> None:
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = 100.0

        with patch.object(dashboard_header_view, "time", return_value=104.5), \
            patch.object(task4.st, "subheader") as subheader_mock, \
            patch.object(task4.st, "info") as info_mock:
            task4._render_current_trend(runtime, [
                {
                    "facility_code": "WOOLGSF",
                    "facility_name": "Woolooga",
                    "timestamp": "2025-10-25T08:50:00",
                    "power_value": 0.0,
                    "emission_value": 0.0,
                    "price_per_mwh": 102.16,
                    "demand_mw": 23448.02,
                }
            ])

        subheader_mock.assert_called_once_with("Current Facility")
        info_mock.assert_called_once_with("No MQTT messages available for current trend yet.")

    def test_render_current_trend_uses_html_component_for_latest_record(self) -> None:
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = 100.0
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

        with patch.object(dashboard_header_view, "time", return_value=102.5), \
            patch.object(task4.components, "html") as html_mock:
            task4._render_current_trend(runtime, messages)

        html_mock.assert_called_once()
        self.assertIn("Current Facility: Woolooga", html_mock.call_args.args[0])
        self.assertEqual(html_mock.call_args.kwargs["height"], 220)
        self.assertFalse(html_mock.call_args.kwargs["scrolling"])

    def test_main_refresh_interval_defaults_to_one_second(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stream_cache.get_main_refresh_interval_seconds(), 1)

    def test_main_refresh_interval_prefers_environment_override(self) -> None:
        with patch.dict(os.environ, {"MAIN_REFRESH_INTERVAL_SECONDS": "5"}, clear=True):
            self.assertEqual(stream_cache.get_main_refresh_interval_seconds(), 5)

    def test_sidebar_refresh_interval_defaults_to_one_second(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stream_cache.get_sidebar_refresh_interval_seconds(), 1)

    def test_sidebar_refresh_interval_prefers_environment_override(self) -> None:
        with patch.dict(os.environ, {"SIDEBAR_REFRESH_INTERVAL_SECONDS": "4"}, clear=True):
            self.assertEqual(stream_cache.get_sidebar_refresh_interval_seconds(), 4)

    def test_max_stream_rows_defaults_to_five_thousand_five_hundred_twenty(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stream_cache.get_max_stream_rows(), 5520)

    def test_main_refresh_interval_ignores_legacy_generic_override(self) -> None:
        with patch.dict(os.environ, {"REFRESH_INTERVAL_SECONDS": "3"}, clear=True):
            self.assertEqual(stream_cache.get_main_refresh_interval_seconds(), 1)

    def test_sidebar_refresh_interval_ignores_legacy_generic_override(self) -> None:
        with patch.dict(os.environ, {"REFRESH_INTERVAL_SECONDS": "3"}, clear=True):
            self.assertEqual(stream_cache.get_sidebar_refresh_interval_seconds(), 1)

    def test_dashboard_subscribe_topic_filter_ignores_legacy_topic_alias(self) -> None:
        with patch.dict(
            os.environ,
            {"MQTT_TOPIC": "legacy/topic/#"},
            clear=True,
        ):
            module = load_module("dashboard_settings_legacy_alias_test", "src/dashboard/settings.py")
            self.assertEqual(module.SUBSCRIBE_TOPIC_FILTER, "comp5339/task123/measurements/#")

    def test_publisher_topic_template_ignores_legacy_topic_alias(self) -> None:
        with patch.dict(
            os.environ,
            {"MQTT_TOPIC_TEMPLATE": "legacy/topic/{facility_code}"},
            clear=True,
        ):
            module = load_module("publisher_mqtt_legacy_alias_test", "src/publisher/publish/mqtt_publish.py")
            self.assertEqual(module.PUBLISH_TOPIC_TEMPLATE, "comp5339/task123/measurements/{facility_code}")

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

    def test_snapshot_stats_return_none_for_empty_snapshot(self) -> None:
        stats = task4._calculate_snapshot_stats({})

        self.assertIsNone(stats["total_power"])
        self.assertIsNone(stats["total_emission"])
        self.assertIsNone(stats["median_price"])
        self.assertIsNone(stats["median_demand"])

    def test_resolve_data_source_defaults_to_empty_without_live_messages(self) -> None:
        self.assertEqual(task4._resolve_data_source([]), "empty")

    def test_render_header_uses_freshness_badge_for_empty_cache(self) -> None:
        stats = {
            "total_power": None,
            "total_emission": 8.0,
            "median_price": 30.0,
            "median_demand": 5.0,
        }
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = None
        column_mocks = [Mock(), Mock(), Mock(), Mock()]
        for column in column_mocks:
            column.__enter__ = Mock(return_value=column)
            column.__exit__ = Mock(return_value=None)

        with patch.object(task4.st, "title"), \
            patch.object(task4.st, "badge") as badge_mock, \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "info") as info_mock, \
            patch.object(task4.st, "success") as success_mock, \
            patch.object(task4.st, "columns", return_value=column_mocks), \
            patch.object(task4.st, "metric"):
            task4._render_header(runtime, stats, {})

        info_mock.assert_not_called()
        success_mock.assert_not_called()
        badge_mock.assert_called_once_with("Waiting for publish Message...", icon=":material/hourglass_empty:", color="blue")

    def test_render_header_uses_freshness_badge_for_fresh_cache(self) -> None:
        stats = {
            "total_power": 30.0,
            "total_emission": 8.0,
            "median_price": 30.0,
            "median_demand": 5.0,
        }
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = 100.0
        column_mocks = [Mock(), Mock(), Mock(), Mock()]
        for column in column_mocks:
            column.__enter__ = Mock(return_value=column)
            column.__exit__ = Mock(return_value=None)

        with patch.object(task4.st, "title"), \
            patch.object(dashboard_header_view, "time", return_value=102.5), \
            patch.object(task4.st, "badge") as badge_mock, \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "columns", return_value=column_mocks), \
            patch.object(task4.st, "metric"):
            task4._render_header(runtime, stats, {})

        badge_mock.assert_called_once_with("Real-time Update", icon=":material/schedule:", color="green")

    def test_render_header_uses_freshness_badge_for_stale_cache(self) -> None:
        stats = {
            "total_power": 30.0,
            "total_emission": 8.0,
            "median_price": 30.0,
            "median_demand": 5.0,
        }
        runtime = Mock()
        runtime.cache.last_updated_at.return_value = 100.0
        column_mocks = [Mock(), Mock(), Mock(), Mock()]
        for column in column_mocks:
            column.__enter__ = Mock(return_value=column)
            column.__exit__ = Mock(return_value=None)

        with patch.object(task4.st, "title"), \
            patch.object(dashboard_header_view, "time", return_value=104.1), \
            patch.object(task4.st, "badge") as badge_mock, \
            patch.object(task4.st, "caption"), \
            patch.object(task4.st, "columns", return_value=column_mocks), \
            patch.object(task4.st, "metric"):
            task4._render_header(runtime, stats, {})

        badge_mock.assert_called_once_with("Waiting for publish Message...", icon=":material/hourglass_empty:", color="blue")

    def test_render_sidebar_keeps_transport_status_without_transient_notices(self) -> None:
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
            task4._render_sidebar(runtime, {}, {}, "empty", ["All", "Gas"])

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
        info_mock.assert_called_once_with("Connecting")
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
            patch.object(dashboard_sidebar_view, "_soft_reset_runtime", side_effect=soft_reset_side_effect) as soft_reset_mock, \
            patch.object(task4.st, "rerun") as rerun_mock:
            task4._render_sidebar(runtime, {}, {}, "live", ["All", "Gas"])

        button_mock.assert_called_once_with("Reset Cache", key="reset_cache", type="primary")
        soft_reset_mock.assert_called_once()
        rerun_mock.assert_not_called()
        self.assertIn(
            f"Last soft reset: {task4._format_ts(updated_reset_at.timestamp())}",
            [str(call.args[0]) for call in write_mock.call_args_list],
        )

    def test_main_calls_render_dashboard_without_manual_rerun_loop(self) -> None:
        with patch.object(dashboard_app, "get_runtime") as runtime_mock, \
            patch.object(dashboard_app, "set_active_runtime") as set_runtime_mock, \
            patch.object(dashboard_app, "render_dashboard") as render_mock, \
            patch.object(task4.st, "rerun") as rerun_mock:
            runtime_mock.return_value = Mock()
            task4.main()

        set_runtime_mock.assert_called_once_with(runtime_mock.return_value)
        render_mock.assert_called_once()
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
            patch.object(dashboard_nem_map_component, "render_nem_facility_map", return_value={"display_mode": "emission_value"}) as render_mock:
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
            patch.object(dashboard_nem_map_component, "render_nem_facility_map", return_value={"center": {"lat": -33.0, "lng": 151.0}, "zoom": 6}) as render_mock:
            task4._render_map(filtered_snapshot, "power_value")

        self.assertEqual(fake_state["display_mode"], "power_value")
        render_mock.assert_called_once()

    def test_render_map_renders_empty_state_without_info_banner(self) -> None:
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
            patch.object(task4.st, "info") as info_mock, \
            patch.object(dashboard_nem_map_component, "render_nem_facility_map", return_value={}) as render_mock:
            task4._render_map({}, "power_value")

        info_mock.assert_not_called()
        render_mock.assert_called_once()
        marker_payload = render_mock.call_args.args[0]
        self.assertEqual(marker_payload["markers"], [])

    def test_render_table_renders_empty_state_without_info_banner(self) -> None:
        with patch.object(task4.st, "subheader"), \
            patch.object(task4.st, "info") as info_mock, \
            patch.object(task4.st, "dataframe") as dataframe_mock:
            task4._render_table({})

        info_mock.assert_not_called()
        dataframe_mock.assert_called_once()
        rendered = dataframe_mock.call_args.args[0]
        self.assertEqual(list(rendered.columns), [
            "facility_code",
            "facility_name",
            "state",
            "fuel_group",
            "fuel_list",
            "power_value",
            "emission_value",
            "price_per_mwh",
            "demand_mw",
            "timestamp",
        ])
