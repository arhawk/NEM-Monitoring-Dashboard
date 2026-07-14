from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd

from src.llm.client import GeminiClient, _extract_text_from_response, parse_llm_json
from src.llm.executor import execute_analysis_code, format_result_for_display
from src.llm.pipeline import run_llm_query
from src.llm.validators import validate_analysis_code


def _mini_mart_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": "2025-10-25 00:00:00+11:00",
                "Price ($/MWh)": 100.0,
                "Demand (MW)": 20000.0,
                "facility_code": "A1",
                "Power (MW)": 10.0,
                "Emissions (tonnes)": 5.0,
                "facility_name": "Alpha",
                "lat": -33.0,
                "lng": 151.0,
                "state": "NSW",
                "fuel_list": "['Wind']",
            },
            {
                "timestamp": "2025-10-25 00:05:00+11:00",
                "Price ($/MWh)": 110.0,
                "Demand (MW)": 20100.0,
                "facility_code": "A2",
                "Power (MW)": 20.0,
                "Emissions (tonnes)": 8.0,
                "facility_name": "Beta",
                "lat": -27.0,
                "lng": 153.0,
                "state": "QLD",
                "fuel_list": "['Gas']",
            },
            {
                "timestamp": "2025-10-25 00:10:00+11:00",
                "Price ($/MWh)": 120.0,
                "Demand (MW)": 20200.0,
                "facility_code": "A3",
                "Power (MW)": 30.0,
                "Emissions (tonnes)": 3.0,
                "facility_name": "Gamma",
                "lat": -34.0,
                "lng": 150.0,
                "state": "NSW",
                "fuel_list": "['Solar']",
            },
        ]
    )


class LlmPipelineTests(TestCase):
    def test_validator_rejects_import_os(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_analysis_code("import os\nresult = df.head()")
        self.assertIn("import", str(ctx.exception).lower())

    def test_validator_accepts_groupby_code(self) -> None:
        code = 'result = df.groupby("state")["Emissions (tonnes)"].mean().sort_values(ascending=False)'
        validate_analysis_code(code)

    def test_executor_groupby_emissions(self) -> None:
        df = _mini_mart_dataframe()
        code = 'result = df.groupby("state")["Emissions (tonnes)"].mean().sort_values(ascending=False)'
        result = execute_analysis_code(df, code)
        self.assertEqual(result.index[0], "QLD")
        self.assertAlmostEqual(float(result.loc["QLD"]), 8.0)

    def test_parse_llm_json_handles_markdown_fence(self) -> None:
        raw = """```json
        {"reasoning": "test", "code": "result = df.head()", "expected_output": "table"}
        ```"""
        payload = parse_llm_json(raw)
        self.assertEqual(payload["code"], "result = df.head()")

    def test_pipeline_fail_closed_no_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "mart.csv"
            _mini_mart_dataframe().to_csv(csv_path, index=False)
            with (
                patch.dict(
                    os.environ,
                    {
                        "ENABLE_LLM_ANALYTICS": "true",
                        "GOOGLE_AI_API_KEY": "",
                    },
                    clear=False,
                ),
                self.assertRaises(RuntimeError),
            ):
                run_llm_query(
                    "Which state has the highest average emissions?", data_path=csv_path
                )

    def test_pipeline_fail_closed_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "mart.csv"
            _mini_mart_dataframe().to_csv(csv_path, index=False)
            with (
                patch.dict(
                    os.environ,
                    {
                        "ENABLE_LLM_ANALYTICS": "false",
                        "GOOGLE_AI_API_KEY": "test-key",
                    },
                    clear=False,
                ),
                self.assertRaises(RuntimeError) as ctx,
            ):
                run_llm_query(
                    "Which state has the highest average emissions?", data_path=csv_path
                )
            self.assertIn("disabled", str(ctx.exception).lower())

    def test_pipeline_end_to_end_with_mock_client(self) -> None:
        df = _mini_mart_dataframe()
        code = 'result = df.groupby("state")["Emissions (tonnes)"].mean().sort_values(ascending=False)'
        mock_client = Mock(spec=GeminiClient)
        mock_client.complete.side_effect = [
            json.dumps(
                {
                    "reasoning": "Group by state and average emissions.",
                    "code": code,
                    "expected_output": "series",
                }
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "mart.csv"
            audit_dir = Path(tmpdir) / "llm_runs"
            df.to_csv(csv_path, index=False)
            with patch.dict(
                os.environ,
                {
                    "ENABLE_LLM_ANALYTICS": "true",
                    "GOOGLE_AI_API_KEY": "test-key",
                    "LLM_AUDIT_DIR": str(audit_dir),
                },
                clear=False,
            ):
                query_result = run_llm_query(
                    "Which state has the highest average emissions?",
                    data_path=csv_path,
                    client=mock_client,
                )

            self.assertEqual(query_result.code, code)
            self.assertEqual(query_result.expected_output, "series")
            self.assertIn("QLD", query_result.summary)
            self.assertTrue(query_result.audit_path.exists())
            audit_payload = json.loads(
                query_result.audit_path.read_text(encoding="utf-8")
            )
            self.assertEqual(audit_payload["status"], "success")
            self.assertEqual(audit_payload["retry_count"], 0)
            self.assertEqual(mock_client.complete.call_count, 1)

    def test_pipeline_retries_on_validation_error(self) -> None:
        df = _mini_mart_dataframe()
        valid_code = 'result = df.groupby("state")["Power (MW)"].mean().sort_values(ascending=False)'
        mock_client = Mock(spec=GeminiClient)
        mock_client.complete.side_effect = [
            json.dumps(
                {
                    "reasoning": "bad",
                    "code": "import os\nresult = df.head()",
                    "expected_output": "table",
                }
            ),
            json.dumps(
                {
                    "reasoning": "good",
                    "code": valid_code,
                    "expected_output": "series",
                }
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "mart.csv"
            audit_dir = Path(tmpdir) / "llm_runs"
            df.to_csv(csv_path, index=False)
            with patch.dict(
                os.environ,
                {
                    "ENABLE_LLM_ANALYTICS": "true",
                    "GOOGLE_AI_API_KEY": "test-key",
                    "LLM_AUDIT_DIR": str(audit_dir),
                },
                clear=False,
            ):
                query_result = run_llm_query(
                    "Top states by average power output",
                    data_path=csv_path,
                    client=mock_client,
                )

            self.assertEqual(query_result.code, valid_code)
            audit_payload = json.loads(
                query_result.audit_path.read_text(encoding="utf-8")
            )
            self.assertEqual(audit_payload["retry_count"], 1)
            self.assertEqual(mock_client.complete.call_count, 2)

    def test_format_result_for_display_truncates_dataframe(self) -> None:
        df = pd.DataFrame({"value": range(60)})
        rendered = format_result_for_display(df)
        self.assertIn("(60 rows)", rendered)

    def test_extract_text_from_response_reads_gemini_payload(self) -> None:
        text = _extract_text_from_response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"reasoning":"ok","code":"result = df.head()","expected_output":"table"}'
                                }
                            ]
                        }
                    }
                ]
            }
        )
        self.assertIn("result = df.head()", text)

    def test_gemini_client_uses_rest_api(self) -> None:
        mock_response = Mock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "summary text"}]}}]
        }
        mock_response.raise_for_status = Mock()

        client = GeminiClient(
            api_key="test-key",
            model="gemini-2.0-flash",
            post=Mock(return_value=mock_response),
        )
        result = client.complete(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
            ]
        )

        self.assertEqual(result, "summary text")
        call_kwargs = client._post.call_args.kwargs
        self.assertIn("systemInstruction", call_kwargs["json"])
        self.assertEqual(call_kwargs["json"]["generationConfig"]["temperature"], 0)
