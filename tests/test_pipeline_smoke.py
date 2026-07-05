from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from src.dashboard import render as dashboard_render
from src.dashboard import render_context as dashboard_render_context
from src.dashboard.runtime import state as dashboard_runtime_state
from src.dashboard.runtime import mqtt as dashboard_mqtt
from src.dashboard.components import nem_map_component as dashboard_nem_map_component
from src.dashboard.views import header as dashboard_header_view
from src.dashboard.views import map as dashboard_map_view
from src.dashboard.views import table as dashboard_table_view
from src.publisher.publish import mqtt_publish as publisher_mqtt
from src.shared.stream_cache import StreamCache


class PipelineSmokeTests(TestCase):
    class FakeSessionState(dict):
        def __getattr__(self, key: str):
            return self[key]

        def __setattr__(self, key: str, value):
            self[key] = value

    def _write_measure_csv(self, directory: Path) -> Path:
        path = directory / "data_for_publish.csv"
        path.write_text(
            "\n".join(
                [
                    "timestamp,facility_code,facility_name,state,fuel_list,Power (MW),Emissions (tonnes),Price ($/MWh),Demand (MW),lat,lng",
                    "2026-07-03 00:00:00+10:00,A1,Alpha,NSW,Gas,42.5,3.1,77.2,11.4,-33.0,151.0",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _prepare_live_context(
        self,
    ) -> tuple[dict[str, object], object, object, dict[str, str]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._write_measure_csv(Path(tmpdir))
            rows = publisher_mqtt.load_measure_rows(csv_path)
            published: dict[str, object] = {}

            def capture_publish(client, topic, payload, qos=1, retain=False):
                published["topic"] = topic
                published["payload"] = payload
                return True

            state = {"seq": 0, "last_ts": None, "last_fac": ""}
            with (
                patch.object(
                    publisher_mqtt, "safe_publish_stream", side_effect=capture_publish
                ),
                patch.object(publisher_mqtt, "sleep_until_ns", return_value=None),
                patch.object(publisher_mqtt, "perf_counter_ns", return_value=0),
            ):
                keep_running = publisher_mqtt.publish_new_since(Mock(), rows, state)

            self.assertTrue(keep_running)
            self.assertEqual(state["seq"], 1)
            self.assertEqual(published["topic"], "comp5339/task123/measurements/A1")

            runtime = SimpleNamespace(
                cache=StreamCache(maxlen=10),
                status="Connected",
                last_error=None,
                last_soft_reset_at=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
            )
            with patch.object(dashboard_mqtt.mqtt, "Client", return_value=Mock()):
                manager = dashboard_mqtt.MqttConnectionManager(runtime)

            message = SimpleNamespace(
                payload=json.dumps(published["payload"]).encode("utf-8"),
                topic=published["topic"],
            )
            manager._on_message(Mock(), None, message)

            session_state = self.FakeSessionState(
                display_mode="power_value",
                selected_fuel="All",
                selected_region="All",
            )
            with (
                patch.object(
                    dashboard_render_context.compat_st, "session_state", session_state
                ),
                patch.object(dashboard_runtime_state, "_ACTIVE_RUNTIME", runtime),
            ):
                context = dashboard_render_context._build_dashboard_context()

            return published, runtime, context, session_state

    def test_publish_message_reaches_dashboard_context(self) -> None:
        published, runtime, context, _ = self._prepare_live_context()

        self.assertEqual(published["payload"]["facility_code"], "A1")
        self.assertEqual(runtime.cache.size(), 1)
        self.assertEqual(context.data_source, "live")
        self.assertEqual(list(context.snapshot.keys()), ["A1"])
        self.assertEqual(context.stats["total_power"], 42.5)
        self.assertEqual(context.filtered_snapshot["A1"]["facility_name"], "Alpha")

    def test_dashboard_render_uses_live_context(self) -> None:
        _, runtime, context, session_state = self._prepare_live_context()

        column_mocks = [Mock(), Mock(), Mock(), Mock()]
        for column in column_mocks:
            column.__enter__ = Mock(return_value=column)
            column.__exit__ = Mock(return_value=None)

        with (
            patch.object(dashboard_header_view.st, "title"),
            patch.object(dashboard_header_view.st, "badge"),
            patch.object(dashboard_header_view.st, "caption"),
            patch.object(
                dashboard_header_view.st, "columns", return_value=column_mocks
            ),
            patch.object(dashboard_header_view.st, "metric"),
            patch.object(dashboard_map_view.st, "session_state", session_state),
            patch.object(dashboard_map_view.st, "subheader"),
            patch.object(dashboard_map_view.st, "caption"),
            patch.object(dashboard_map_view.st, "info"),
            patch.object(
                dashboard_nem_map_component, "render_nem_facility_map", return_value={}
            ) as render_map_mock,
            patch.object(dashboard_table_view.st, "subheader"),
            patch.object(dashboard_table_view.st, "dataframe") as dataframe_mock,
        ):
            dashboard_render._render_header(runtime, context.stats, context.snapshot)
            dashboard_render._render_map(context.filtered_snapshot, "power_value")
            dashboard_render._render_table(context.filtered_snapshot)

        self.assertEqual(
            render_map_mock.call_args.args[0]["markers"][0]["facility_code"], "A1"
        )
        self.assertEqual(
            dataframe_mock.call_args.args[0].iloc[0]["facility_code"], "A1"
        )
