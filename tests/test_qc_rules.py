from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.publisher.publish import mqtt_publish as publisher_mqtt
from src.publisher.qc.rules import (
    check_mart_002_primary_key_unique,
    check_mart_geo_001_state_bounds,
    check_pub_001_power_zero_publishable,
    load_qc_context,
    run_all_checks,
    should_fail_exit,
    summarize_checks,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "qc"
THRESHOLDS = Path(__file__).resolve().parents[1] / "config" / "qc_thresholds.yaml"


class MqttPublishZeroTests(TestCase):
    def test_load_measure_rows_preserves_zero_power(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rows.csv"
            path.write_text(
                "\n".join(
                    [
                        "timestamp,facility_code,facility_name,state,fuel_list,Power (MW),Emissions (tonnes),Price ($/MWh),Demand (MW),lat,lng",
                        "2025-10-25 00:00:00+11:00,ADP,Alpha,NSW,Gas,0.0,0.0,77.2,11.4,-33.0,151.0",
                    ]
                ),
                encoding="utf-8",
            )
            rows = publisher_mqtt.load_measure_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["power_value"], 0.0)
            self.assertEqual(rows[0]["emission_value"], 0.0)
            self.assertEqual(rows[0]["price_per_mwh"], 77.2)


class QcRulesFixtureTests(TestCase):
    def _ctx(self, mart_name: str, staging_name: str):
        return load_qc_context(
            mart_path=FIXTURES / mart_name,
            staging_path=FIXTURES / staging_name,
            thresholds_path=THRESHOLDS,
            baseline_path=FIXTURES / "qc_baseline_fixture.yaml",
        )

    def test_fixture_passes_all_checks(self) -> None:
        ctx = self._ctx("mart_pass.csv", "staging_pass.csv")
        checks = run_all_checks(ctx)
        summary = summarize_checks(checks)
        self.assertFalse(should_fail_exit(checks))
        self.assertEqual(summary["overall_status"], "pass")
        self.assertEqual(summary["warnings"], 0)

    def test_duplicate_primary_key_fails(self) -> None:
        ctx = self._ctx("mart_dup_fail.csv", "staging_pass.csv")
        result = check_mart_002_primary_key_unique(ctx)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.id, "MART-002")

    def test_geo_state_bounds_fail(self) -> None:
        ctx = self._ctx("mart_geo_fail.csv", "staging_geo_fail.csv")
        result = check_mart_geo_001_state_bounds(ctx)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.id, "MART-GEO-001")

    def test_power_zero_publish_mapping_passes(self) -> None:
        ctx = self._ctx("mart_pass.csv", "staging_pass.csv")
        result = check_pub_001_power_zero_publishable(ctx)
        self.assertEqual(result.status, "pass")
