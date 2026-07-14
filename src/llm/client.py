from __future__ import annotations

import json
import re
import time
from typing import Callable

import requests

from src.shared.config import (
    get_google_ai_api_key,
    get_google_ai_model,
    get_llm_request_timeout_seconds,
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
RATE_LIMIT_BACKOFF_SECONDS = (2, 4, 8)


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


def _extract_text_from_response(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("LLM returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts") or []
    texts = [part.get("text", "") for part in parts if part.get("text")]
    content = "\n".join(text for text in texts if text).strip()
    if not content:
        raise RuntimeError("LLM returned an empty response.")
    return content


def _redact_api_key(message: str, api_key: str) -> str:
    return message.replace(api_key, "***")


def _quota_exhausted_message(response: requests.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") or {}
    message = str(error.get("message", ""))
    if "quota" not in message.lower() and error.get("status") != "RESOURCE_EXHAUSTED":
        return None
    return message


def _raise_api_error(response: requests.Response, api_key: str) -> None:
    if response.status_code == 429:
        quota_message = _quota_exhausted_message(response)
        if quota_message:
            raise RuntimeError(
                "Gemini API quota exceeded (429). "
                "Try a different GOOGLE_AI_MODEL such as gemini-3.1-flash-lite, "
                "wait for quota reset, or check usage at https://ai.dev/rate-limit. "
                f"Details: {quota_message}"
            )
        raise RuntimeError(
            "Gemini API rate limit exceeded (429). Wait 30-60 seconds and retry, "
            "or check your Google AI Studio quota."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = _redact_api_key(str(exc), api_key)
        raise RuntimeError(detail) from exc


class GeminiClient:
    """Google AI Studio client using the Gemini REST API and requests."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        session: requests.Session | None = None,
        post: Callable[..., requests.Response] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.api_key = api_key or get_google_ai_api_key()
        self.model = model or get_google_ai_model()
        self.timeout_seconds = timeout_seconds or get_llm_request_timeout_seconds()
        self._session = session or requests.Session()
        self._post = post or self._session.post
        self._sleep = sleep or time.sleep

    def complete(self, messages: list[dict[str, str]]) -> str:
        system_instruction, contents = _messages_to_gemini_request(messages)
        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"temperature": 0},
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = (
            f"{GEMINI_API_BASE}/models/{self.model}:generateContent?key={self.api_key}"
        )
        timeout = (5, self.timeout_seconds)

        last_response: requests.Response | None = None
        for attempt, delay in enumerate((*RATE_LIMIT_BACKOFF_SECONDS, None)):
            response = self._post(url, json=payload, timeout=timeout)
            last_response = response
            if response.status_code != 429:
                break
            if delay is not None:
                self._sleep(delay)

        assert last_response is not None
        _raise_api_error(last_response, self.api_key)
        return _extract_text_from_response(last_response.json())


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
