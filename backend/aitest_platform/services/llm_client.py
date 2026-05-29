from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


ENABLE_REAL_LLM_ENV = "AITEST_ENABLE_REAL_LLM"
LLM_BASE_URL_ENV = "AITEST_LLM_BASE_URL"
LLM_API_KEY_ENV = "AITEST_LLM_API_KEY"
LLM_MODEL_ENV = "AITEST_LLM_MODEL"

DEFAULT_TIMEOUT_SECONDS = 20.0
SECRET_PATTERNS = (
    re.compile(r"(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"agt_codex_[A-Za-z0-9_\-]{6,}"),
)


@dataclass(frozen=True)
class LlmRuntimeSettings:
    enabled: bool
    base_url: str | None
    api_key: str | None
    model: str | None


class LlmClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(redact_secret_text(message))
        self.status_code = status_code


def real_llm_enabled() -> bool:
    return os.getenv(ENABLE_REAL_LLM_ENV, "false").strip().lower() == "true"


def resolve_llm_settings(*, config_base_url: str | None = None, config_model: str | None = None) -> LlmRuntimeSettings:
    base_url = (config_base_url or os.getenv(LLM_BASE_URL_ENV) or "").strip() or None
    model = (config_model or os.getenv(LLM_MODEL_ENV) or "").strip() or None
    api_key = (os.getenv(LLM_API_KEY_ENV) or "").strip() or None
    return LlmRuntimeSettings(
        enabled=real_llm_enabled(),
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


def redact_secret_text(value: Any) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1) if match.groups() else ''}***", text)
    return text


def sanitize_llm_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(marker in lowered for marker in ("authorization", "api_key", "apikey", "token", "secret", "password", "cookie")):
                continue
            else:
                clean[key] = sanitize_llm_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_llm_payload(item) for item in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


class OpenAICompatibleClient:
    def __init__(self, *, base_url: str, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_models(self) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        data = self._request("GET", "/models")
        return data, self._duration_ms(started)

    def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        data = self._request("POST", "/chat/completions", json=payload)
        return data, self._duration_ms(started)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = redact_secret_text(exc.response.text[:500])
            raise LlmClientError(
                f"LLM provider returned HTTP {exc.response.status_code}: {detail}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise LlmClientError("LLM provider request timed out") from exc
        except httpx.RequestError as exc:
            raise LlmClientError(f"LLM provider request failed: {exc.__class__.__name__}") from exc
        except ValueError as exc:
            raise LlmClientError("LLM provider returned non-JSON response") from exc

        if not isinstance(data, dict):
            raise LlmClientError("LLM provider returned unexpected response shape")
        return sanitize_llm_payload(data)

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(1, int((time.perf_counter() - started) * 1000))


def extract_chat_reply(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmClientError("LLM provider response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise LlmClientError("LLM provider response choice has unexpected shape")
    message = first.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(first.get("text"), str):
        return first["text"]
    raise LlmClientError("LLM provider response has no text content")


def extract_usage_tokens(response: dict[str, Any]) -> tuple[int, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
