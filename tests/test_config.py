from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from src.shared import config


class ConfigTests(TestCase):
    def test_parse_bool_handles_common_truthy_falsey_values(self) -> None:
        self.assertTrue(config.parse_bool("true"))
        self.assertTrue(config.parse_bool("1"))
        self.assertTrue(config.parse_bool("on"))
        self.assertFalse(config.parse_bool("false"))
        self.assertFalse(config.parse_bool("0"))
        self.assertFalse(config.parse_bool("off"))
        self.assertTrue(config.parse_bool("maybe", default=True))
        self.assertFalse(config.parse_bool("maybe", default=False))

    def test_mqtt_broker_prefers_primary_name_then_legacy_alias_then_default(self) -> None:
        with patch.dict(
            os.environ,
            {"MQTT_BROKER": "broker-a", "MQTT_BROKER_HOST": "broker-b"},
            clear=True,
        ):
            self.assertEqual(config.get_mqtt_broker(), "broker-a")

        with patch.dict(os.environ, {"MQTT_BROKER_HOST": "broker-b"}, clear=True):
            self.assertEqual(config.get_mqtt_broker(), "broker-b")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.get_mqtt_broker(), config.DEFAULT_MQTT_BROKER)

    def test_mqtt_port_falls_back_on_invalid_values(self) -> None:
        with patch.dict(
            os.environ,
            {"MQTT_PORT": "not-a-number", "MQTT_BROKER_PORT": "also-bad"},
            clear=True,
        ):
            self.assertEqual(config.get_mqtt_port(), config.DEFAULT_MQTT_PORT)

    def test_numeric_defaults_do_not_crash_on_invalid_input(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MAX_STREAM_ROWS": "bad",
                "RESET_INTERVAL_HOURS": "bad",
                "MAIN_REFRESH_INTERVAL_SECONDS": "bad",
                "SIDEBAR_REFRESH_INTERVAL_SECONDS": "bad",
                "MQTT_MONITOR_INTERVAL_SECONDS": "bad",
                "AUTO_START_COOLDOWN_SECONDS": "bad",
                "PUBLISH_DURATION_SECONDS": "bad",
            },
            clear=True,
        ):
            self.assertEqual(config.get_max_stream_rows(), config.DEFAULT_MAX_STREAM_ROWS)
            self.assertEqual(
                config.get_reset_interval_hours(), config.DEFAULT_RESET_INTERVAL_HOURS
            )
            self.assertEqual(
                config.get_main_refresh_interval_seconds(),
                config.DEFAULT_MAIN_REFRESH_INTERVAL_SECONDS,
            )
            self.assertEqual(
                config.get_sidebar_refresh_interval_seconds(),
                config.DEFAULT_SIDEBAR_REFRESH_INTERVAL_SECONDS,
            )
            self.assertEqual(
                config.get_mqtt_monitor_interval_seconds(),
                config.DEFAULT_MQTT_MONITOR_INTERVAL_SECONDS,
            )
            self.assertEqual(
                config.get_auto_start_cooldown_seconds(),
                config.DEFAULT_AUTO_START_COOLDOWN_SECONDS,
            )
            self.assertEqual(
                config.get_publish_duration_seconds(),
                config.DEFAULT_PUBLISH_DURATION_SECONDS,
            )

    def test_open_electricity_api_key_is_required_for_fetches(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                config.get_open_electricity_api_key()

