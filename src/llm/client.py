from __future__ import annotations

import json
import re

from src.shared.config import get_google_ai_api_key, get_google_ai_model

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised in dependency-light test envs

    class genai:  # type: ignore[no-redef]
        class Client:
            def __init__(self, *args, **kwargs):
                raise ModuleNotFoundError("google-genai is required for LLM analytics")

    class types:  # type: ignore[no-redef]
        class GenerateContentConfig:
            def __init__(self, *args, **kwargs):
                raise ModuleNotFoundError("google-genai is required for LLM analytics")


def _messages_to_gemini_request(
    messages: list[dict[str, str]],
) -> tuple[str | None, list[dict[str, object]]]:
    system_instruction: str | None = None
    contents: list[dict[str, object]] = []

    for message in messages:
        role = message["role"]
        text = message["content"]
        if role == "system":
            system_instruction = text
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})

    return system_instruction, contents


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: object | None = None,
    ) -> None:
        self.api_key = api_key or get_google_ai_api_key()
        self.model = model or get_google_ai_model()
        self._client = client or genai.Client(api_key=self.api_key)

    def complete(self, messages: list[dict[str, str]]) -> str:
        system_instruction, contents = _messages_to_gemini_request(messages)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0,
        )
        response = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        content = response.text
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


__all__ = ["GeminiClient", "parse_llm_json"]
