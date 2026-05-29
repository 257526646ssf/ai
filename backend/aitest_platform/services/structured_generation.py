from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from aitest_platform.services.llm_client import (
    LlmClientError,
    OpenAICompatibleClient,
    extract_chat_reply,
    extract_usage_tokens,
    sanitize_llm_payload,
)


MAX_REQUIREMENT_ITEMS = 8
MAX_TEST_POINTS = 10
MAX_TEST_CASES = 20
MAX_PROMPT_TEXT_CHARS = 12000

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_PRIORITIES = {"P0", "P1", "P2", "P3"}
_POINT_TYPES = {"functional", "happy_path", "negative", "boundary", "permission", "integration", "performance", "security", "compatibility"}
_CASE_TYPES = {"functional", "happy_path", "negative", "boundary", "permission", "integration", "performance", "security", "compatibility"}


@dataclass(frozen=True)
class StructuredGenerationResult:
    records: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    duration_ms: int


def _as_text(value: Any, *, default: str = "", limit: int = 1000) -> str:
    text = str(value).strip() if value is not None else default
    return text[:limit]


def _as_list(value: Any, *, limit: int = 12) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value[:limit]
    if isinstance(value, tuple):
        return list(value[:limit])
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [value]


def _priority(value: Any, default: str = "P2") -> str:
    text = str(value or default).strip().upper()
    return text if text in _PRIORITIES else default


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.7
    return min(1.0, max(0.0, number))


def _extract_json_text(content: str) -> str:
    text = content.strip()
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        return fence_match.group(1).strip()

    first_obj = text.find("{")
    first_arr = text.find("[")
    starts = [idx for idx in (first_obj, first_arr) if idx >= 0]
    if not starts:
        raise ValueError("LLM response does not contain JSON")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    if end < start:
        raise ValueError("LLM response JSON is incomplete")
    return text[start : end + 1]


def parse_json_response(content: str) -> Any:
    try:
        return json.loads(_extract_json_text(content))
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response JSON could not be parsed") from exc


def _records_from_payload(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = []
        for key in keys:
            if isinstance(payload.get(key), list):
                values = payload[key]
                break
    else:
        values = []
    return [item for item in values if isinstance(item, dict)]


def normalize_requirement_items(payload: Any) -> list[dict[str, Any]]:
    records = _records_from_payload(payload, ("items", "requirement_items", "requirements"))
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(records[:MAX_REQUIREMENT_ITEMS], start=1):
        title = _as_text(item.get("title") or item.get("name"), default=f"Requirement Item {index}", limit=255)
        normalized.append(
            {
                "title": title,
                "summary": _as_text(item.get("summary") or item.get("description") or title, limit=2000),
                "module": _as_text(item.get("module"), limit=128) or None,
                "actor": _as_text(item.get("actor"), limit=128) or None,
                "goal": _as_text(item.get("goal"), limit=1000) or None,
                "preconditions": _as_list(item.get("preconditions"), limit=12),
                "business_rules": _as_list(item.get("business_rules"), limit=12),
                "state_transitions": _as_list(item.get("state_transitions"), limit=12),
                "exceptions": _as_list(item.get("exceptions"), limit=12),
                "permissions": _as_list(item.get("permissions"), limit=12),
                "non_functional": _as_list(item.get("non_functional"), limit=12),
                "priority": _priority(item.get("priority")),
                "status": "draft",
                "confidence": _confidence(item.get("confidence")),
                "granularity_flag": _as_text(item.get("granularity_flag"), default="normal", limit=32) or "normal",
                "source_anchor_ids": _as_list(item.get("source_anchor_ids"), limit=8),
            }
        )
    return normalized


def normalize_test_points(payload: Any) -> list[dict[str, Any]]:
    records = _records_from_payload(payload, ("points", "test_points"))
    normalized: list[dict[str, Any]] = []
    for index, point in enumerate(records[:MAX_TEST_POINTS], start=1):
        point_type = _as_text(point.get("point_type") or point.get("type"), default="functional", limit=48)
        normalized.append(
            {
                "title": _as_text(point.get("title") or point.get("name"), default=f"Test Point {index}", limit=255),
                "point_type": point_type if point_type in _POINT_TYPES else "functional",
                "target": _as_text(point.get("target") or point.get("objective"), limit=2000) or None,
                "priority": _priority(point.get("priority")),
                "suggested_method": _as_text(point.get("suggested_method") or point.get("method"), default="manual", limit=48) or "manual",
                "coverage_status": "todo",
                "source_anchor_ids": _as_list(point.get("source_anchor_ids"), limit=8),
                "note": _as_text(point.get("note"), limit=1000) or None,
            }
        )
    return normalized


def normalize_test_cases(payload: Any, *, valid_point_ids: set[int], generation_mode: str) -> list[dict[str, Any]]:
    records = _records_from_payload(payload, ("cases", "test_cases"))
    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(records[:MAX_TEST_CASES], start=1):
        point_id = case.get("test_point_id")
        try:
            point_id = int(point_id)
        except (TypeError, ValueError):
            point_id = None
        if point_id not in valid_point_ids:
            point_id = None
        case_type = _as_text(case.get("case_type") or case.get("type"), default="functional", limit=48)
        steps = _as_list(case.get("steps"), limit=20)
        if not steps:
            steps = [{"step": 1, "action": "Execute the described user flow."}]
        normalized.append(
            {
                "test_point_id": point_id,
                "title": _as_text(case.get("title") or case.get("name"), default=f"Test Case {index}", limit=255),
                "case_type": case_type if case_type in _CASE_TYPES else "functional",
                "precondition": _as_text(case.get("precondition"), limit=2000) or None,
                "steps": steps,
                "expected_result": _as_text(case.get("expected_result") or case.get("expected"), default="The actual result matches the requirement.", limit=3000),
                "priority": _priority(case.get("priority")),
                "tags": [str(tag)[:48] for tag in _as_list(case.get("tags"), limit=8)] or [generation_mode],
                "source_anchor_ids": _as_list(case.get("source_anchor_ids"), limit=8),
                "evidence_type": _as_text(case.get("evidence_type"), default="original", limit=32) or "original",
                "generation_reason": _as_text(case.get("generation_reason"), default=f"{generation_mode} LLM generation", limit=1000),
                "status": "draft",
            }
        )
    return normalized


class StructuredGenerationService:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        client_cls: Callable[..., OpenAICompatibleClient] = OpenAICompatibleClient,
    ):
        self.client = client_cls(base_url=base_url, api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def generate_requirement_items(self, *, document: dict[str, Any], blocks: list[dict[str, Any]]) -> StructuredGenerationResult:
        content = "\n\n".join(_as_text(block.get("normalized_text") or block.get("raw_text"), limit=3000) for block in blocks)
        if not content:
            content = _as_text(document.get("raw_content") or document.get("name"), limit=MAX_PROMPT_TEXT_CHARS)
        prompt = (
            "Extract structured requirement items from the requirement document. "
            "Return JSON only with key \"items\". Each item may contain title, summary, module, actor, goal, "
            "preconditions, business_rules, state_transitions, exceptions, permissions, non_functional, priority, confidence.\n"
            f"Document name: {_as_text(document.get('name'), limit=255)}\n"
            f"Document content:\n{content[:MAX_PROMPT_TEXT_CHARS]}"
        )
        return self._generate(prompt, normalize_requirement_items, empty_message="LLM returned no requirement items")

    def generate_test_points(self, *, item: dict[str, Any]) -> StructuredGenerationResult:
        prompt = (
            "Generate concise test points for this requirement item. Return JSON only with key \"points\". "
            "Each point may contain title, point_type, target, priority, suggested_method, note.\n"
            f"Requirement item JSON:\n{json.dumps(sanitize_llm_payload(item), ensure_ascii=False)[:MAX_PROMPT_TEXT_CHARS]}"
        )
        return self._generate(prompt, normalize_test_points, empty_message="LLM returned no test points")

    def generate_test_cases(
        self,
        *,
        item: dict[str, Any],
        points: list[dict[str, Any]],
        generation_mode: str,
    ) -> StructuredGenerationResult:
        valid_point_ids = {int(point["id"]) for point in points if str(point.get("id", "")).isdigit()}

        def normalize(payload: Any) -> list[dict[str, Any]]:
            return normalize_test_cases(payload, valid_point_ids=valid_point_ids, generation_mode=generation_mode)

        prompt = (
            "Generate executable manual test cases for this requirement item and its test points. "
            "Return JSON only with key \"cases\". Each case may contain test_point_id, title, case_type, "
            "precondition, steps, expected_result, priority, tags.\n"
            f"Generation mode: {generation_mode}\n"
            f"Requirement item JSON:\n{json.dumps(sanitize_llm_payload(item), ensure_ascii=False)[:6000]}\n"
            f"Test points JSON:\n{json.dumps(sanitize_llm_payload(points), ensure_ascii=False)[:6000]}"
        )
        return self._generate(prompt, normalize, empty_message="LLM returned no test cases")

    def _generate(
        self,
        prompt: str,
        normalize: Callable[[Any], list[dict[str, Any]]],
        *,
        empty_message: str,
    ) -> StructuredGenerationResult:
        response, duration_ms = self.client.chat_completions(
            model=self.model,
            messages=[
                {"role": "system", "content": "You generate compact valid JSON only. Do not include Markdown unless asked."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        content = extract_chat_reply(response)
        records = normalize(parse_json_response(content))
        if not records:
            raise LlmClientError(empty_message)
        input_tokens, output_tokens = extract_usage_tokens(response)
        return StructuredGenerationResult(records=records, input_tokens=input_tokens, output_tokens=output_tokens, duration_ms=duration_ms)
