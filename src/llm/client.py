from __future__ import annotations

import json
import re

from src.shared.config import get_openai_api_key, get_openai_model

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised in dependency-light test envs

    class OpenAI:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ModuleNotFoundError("openai is required for LLM analytics")


class OpenAIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: object | None = None,
    ) -> None:
        self.api_key = api_key or get_openai_api_key()
        self.model = model or get_openai_model()
        self._client = client or OpenAI(api_key=self.api_key)

    def complete(self, messages: list[dict[str, str]]) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty response.")
        return content


def parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object.")
    return payload


__all__ = ["OpenAIClient", "parse_llm_json"]
