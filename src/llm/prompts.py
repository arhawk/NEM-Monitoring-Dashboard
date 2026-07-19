from __future__ import annotations

ANALYSIS_SYSTEM_PROMPT = """You are a data analyst for Australian NEM electricity market data.
Output ONLY valid JSON with this shape:
{
  "reasoning": "brief",
  "code": "single pandas expression assigning to variable `result`",
  "expected_output": "table|scalar|series"
}

Rules:
- Use only `df` (DataFrame) and `pd` (pandas). No imports, no file I/O, no network.
- `result` must be a pandas Series, DataFrame, or scalar.
- Prefer groupby/agg for comparisons. Handle NaN explicitly.
- Column names must match schema exactly.
- Do not use eval() or exec() to parse fuel_list; treat it as a string if needed.
"""

SUMMARY_SYSTEM_PROMPT = """You summarize NEM electricity data analysis results in 2-3 sentences.
Be concise and factual. Mention key findings and units where relevant."""


def build_analysis_prompt(
    question: str,
    schema_json: str,
    sample_json: str,
    *,
    validation_error: str | None = None,
) -> list[dict[str, str]]:
    user_parts = [
        f"Schema:\n{schema_json}",
        f"Sample rows (3):\n{sample_json}",
        f"Question:\n{question}",
    ]
    if validation_error:
        user_parts.append(
            "Previous code failed validation. Fix the code and try again.\n"
            f"Validation error: {validation_error}"
        )

    return [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def build_summary_prompt(
    question: str,
    code: str,
    result_preview: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question: {question}\nCode: {code}\nResult preview:\n{result_preview}"
            ),
        },
    ]


__all__ = [
    "ANALYSIS_SYSTEM_PROMPT",
    "SUMMARY_SYSTEM_PROMPT",
    "build_analysis_prompt",
    "build_summary_prompt",
]
