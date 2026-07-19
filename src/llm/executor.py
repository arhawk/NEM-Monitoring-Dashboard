from __future__ import annotations

import threading
from typing import Any

import pandas as pd


def _truncate_result(result: Any) -> Any:
    if isinstance(result, pd.DataFrame):
        return result.head(50)
    if isinstance(result, pd.Series):
        return result.head(50)
    return result


def execute_analysis_code(
    df: pd.DataFrame,
    code: str,
    *,
    timeout_seconds: float = 5.0,
) -> Any:
    namespace: dict[str, Any] = {"df": df.copy(), "pd": pd, "result": None}
    error_holder: list[BaseException] = []

    def _run() -> None:
        try:
            exec(compile(code, "<llm>", "exec"), namespace, namespace)
        except BaseException as exc:  # noqa: BLE001 - surface execution errors to caller
            error_holder.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(f"Analysis code exceeded the {timeout_seconds}s timeout.")

    if error_holder:
        raise error_holder[0]

    result = namespace.get("result")
    if result is None:
        raise ValueError("Analysis code did not assign a value to 'result'.")

    return _truncate_result(result)


def format_result_for_display(result: Any) -> str:
    if isinstance(result, pd.DataFrame):
        row_count = len(result)
        return f"({row_count} rows):\n{result.to_string()}"
    if isinstance(result, pd.Series):
        length = len(result)
        return f"({length} items):\n{result.to_string()}"
    return str(result)


def describe_result(result: Any) -> tuple[str, str | None, str]:
    if isinstance(result, pd.DataFrame):
        preview = result.head(10).to_string()
        shape = f"{len(result)} rows x {len(result.columns)} columns"
        return "dataframe", shape, preview
    if isinstance(result, pd.Series):
        preview = result.head(10).to_string()
        shape = f"{len(result)} items"
        return "series", shape, preview
    return "scalar", None, str(result)


__all__ = [
    "describe_result",
    "execute_analysis_code",
    "format_result_for_display",
]
