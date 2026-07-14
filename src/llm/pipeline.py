from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.llm.audit import write_audit_log
from src.llm.client import OpenAIClient, parse_llm_json
from src.llm.executor import (
    describe_result,
    execute_analysis_code,
    format_result_for_display,
)
from src.llm.prompts import build_analysis_prompt, build_summary_prompt
from src.llm.schema import load_mart_dataframe, sample_rows_json, schema_json
from src.llm.validators import validate_analysis_code
from src.shared.config import (
    get_enable_llm_analytics,
    get_llm_audit_dir,
    get_llm_max_rows,
    get_openai_model,
)


@dataclass
class QueryResult:
    question: str
    code: str
    result: Any
    summary: str
    audit_path: Path
    expected_output: str


def _ensure_enabled() -> None:
    if not get_enable_llm_analytics():
        raise RuntimeError("LLM analytics is disabled. Set ENABLE_LLM_ANALYTICS=true.")


def _generate_analysis(
    client: OpenAIClient,
    question: str,
    df,
    *,
    validation_error: str | None = None,
) -> dict:
    messages = build_analysis_prompt(
        question,
        schema_json(),
        sample_rows_json(df),
        validation_error=validation_error,
    )
    raw = client.complete(messages)
    payload = parse_llm_json(raw)
    for key in ("reasoning", "code", "expected_output"):
        if key not in payload:
            raise ValueError(f"LLM response is missing required field '{key}'.")
    return payload


def _summarize_result(
    client: OpenAIClient,
    question: str,
    code: str,
    result: Any,
) -> str:
    _, shape, preview = describe_result(result)
    try:
        messages = build_summary_prompt(question, code, preview)
        return client.complete(messages).strip()
    except Exception:
        if shape:
            return f"Analysis completed with {shape}."
        return "Analysis completed successfully."


def run_llm_query(
    question: str,
    *,
    data_path: Path | None = None,
    client: OpenAIClient | None = None,
) -> QueryResult:
    _ensure_enabled()
    active_client = client or OpenAIClient()
    model = get_openai_model()
    started_at = datetime.now(timezone.utc).isoformat()

    df = load_mart_dataframe(get_llm_max_rows(), data_path)
    retry_count = 0
    validation_error: str | None = None
    payload: dict | None = None
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            payload = _generate_analysis(
                active_client,
                question,
                df,
                validation_error=validation_error,
            )
            validate_analysis_code(str(payload["code"]))
            break
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                validation_error = str(exc)
                retry_count = 1
                continue
            raise

    if payload is None:
        raise RuntimeError("Failed to generate analysis code.") from last_error

    code = str(payload["code"]).strip()
    reasoning = str(payload.get("reasoning", ""))
    expected_output = str(payload.get("expected_output", ""))

    result = execute_analysis_code(df, code)
    summary = _summarize_result(active_client, question, code, result)
    result_type, result_shape, result_preview = describe_result(result)

    audit_path = write_audit_log(
        {
            "question": question,
            "code": code,
            "reasoning": reasoning,
            "expected_output": expected_output,
            "result_type": result_type,
            "result_shape": result_shape,
            "result_preview": result_preview,
            "model": model,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": retry_count,
            "status": "success",
        },
        get_llm_audit_dir(),
    )

    return QueryResult(
        question=question,
        code=code,
        result=result,
        summary=summary,
        audit_path=audit_path,
        expected_output=expected_output,
    )


def format_query_output(query_result: QueryResult) -> str:
    result_display = format_result_for_display(query_result.result)
    return "\n".join(
        [
            f"Question: {query_result.question}",
            f"Generated code: {query_result.code}",
            f"Result {result_display}",
            f"Summary: {query_result.summary}",
            f"Audit log: {query_result.audit_path}",
        ]
    )


__all__ = ["QueryResult", "format_query_output", "run_llm_query"]
