from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any


PASS_THRESHOLD = 80
ACTION_MARKERS = (
    "click",
    "tap",
    "open",
    "enter",
    "input",
    "select",
    "submit",
    "save",
    "delete",
    "update",
    "create",
    "upload",
    "download",
    "login",
    "logout",
    "verify",
    "check",
    "assert",
    "request",
    "send",
    "choose",
    "confirm",
    "\u70b9\u51fb",
    "\u8f93\u5165",
    "\u9009\u62e9",
    "\u63d0\u4ea4",
    "\u4fdd\u5b58",
    "\u5220\u9664",
    "\u65b0\u589e",
    "\u521b\u5efa",
    "\u4e0a\u4f20",
    "\u4e0b\u8f7d",
    "\u767b\u5f55",
    "\u67e5\u770b",
    "\u6821\u9a8c",
    "\u9a8c\u8bc1",
    "\u786e\u8ba4",
)
ASSERTION_MARKERS = (
    "should",
    "must",
    "display",
    "show",
    "return",
    "reject",
    "allow",
    "equal",
    "contain",
    "status",
    "message",
    "error",
    "created",
    "updated",
    "saved",
    "\u5e94",
    "\u5fc5\u987b",
    "\u663e\u793a",
    "\u8fd4\u56de",
    "\u63d0\u793a",
    "\u62d2\u7edd",
    "\u6210\u529f",
    "\u5931\u8d25",
    "\u72b6\u6001",
)
GENERIC_EXPECTATIONS = (
    "success",
    "successful",
    "ok",
    "pass",
    "passed",
    "normal",
    "works",
    "as expected",
    "meet requirement",
    "\u6210\u529f",
    "\u6b63\u5e38",
    "\u901a\u8fc7",
    "\u7b26\u5408\u9700\u6c42",
    "\u65e0\u5f02\u5e38",
)
NON_HAPPY_MARKERS = (
    "negative",
    "exception",
    "error",
    "fail",
    "failure",
    "invalid",
    "empty",
    "boundary",
    "permission",
    "timeout",
    "retry",
    "edge",
    "\u5f02\u5e38",
    "\u5931\u8d25",
    "\u9519\u8bef",
    "\u65e0\u6548",
    "\u4e3a\u7a7a",
    "\u8fb9\u754c",
    "\u6743\u9650",
    "\u8d85\u65f6",
    "\u91cd\u8bd5",
)
HAPPY_MARKERS = ("happy", "normal", "positive", "success", "functional", "\u6b63\u5e38", "\u6210\u529f")


def assess_test_case_quality(
    case: dict[str, Any],
    *,
    requirement: dict[str, Any] | None = None,
    peer_cases: list[dict[str, Any]] | None = None,
    requirement_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    peers = peer_cases or []
    cases_for_requirement = requirement_cases or [case]
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    actions: list[str] = []
    score = 100

    def add_issue(code: str, level: str, message: str, penalty: int, *, field: str | None = None) -> None:
        nonlocal score
        score -= penalty
        issue = {"code": code, "level": level, "message": message, "penalty": penalty}
        if field:
            issue["field"] = field
        issues.append(issue)

    title = _clean_text(case.get("title"))
    steps = _step_texts(case.get("steps"))
    expected = _clean_text(case.get("expected_result"))
    anchors = _as_list(case.get("source_anchor_ids"))
    tags = [_clean_text(item).lower() for item in _as_list(case.get("tags"))]
    case_type = _clean_text(case.get("case_type")).lower()

    title_ok = len(title) >= 6
    checks.append(_check("title_specific", title_ok))
    if not title_ok:
        add_issue("title_too_short", "medium", "Title is too short to identify the verification intent.", 10, field="title")
        actions.append("Rewrite the title with the object, condition, and expected behavior.")

    has_steps = bool(steps)
    checks.append(_check("has_steps", has_steps))
    if not has_steps:
        add_issue("missing_steps", "high", "Steps are missing.", 24, field="steps")
        actions.append("Add executable steps in user action order.")

    has_action = any(_contains_any(step.lower(), ACTION_MARKERS) for step in steps)
    executable = has_steps and has_action
    checks.append(_check("executable_steps", executable))
    if has_steps and not has_action:
        add_issue("unexecutable_steps", "high", "Steps do not contain a clear executable action.", 18, field="steps")
        actions.append("Use concrete actions such as open, input, select, submit, or verify.")
    elif not has_steps:
        add_issue("unexecutable_steps", "high", "The case is not executable without steps.", 10, field="steps")

    has_expected = bool(expected)
    checks.append(_check("has_expected_result", has_expected))
    if not has_expected:
        add_issue("missing_expected_result", "high", "Expected result is missing.", 24, field="expected_result")
        actions.append("Add an observable expected result for the final state or response.")
    else:
        expected_specific = len(expected) >= 12 and not _is_generic_expected(expected)
        expected_assertable = expected_specific and _contains_any(expected.lower(), ASSERTION_MARKERS)
        checks.append(_check("expected_result_specific", expected_specific))
        checks.append(_check("expected_result_assertable", expected_assertable))
        if not expected_specific:
            add_issue("expected_result_too_short", "medium", "Expected result is too short or generic.", 14, field="expected_result")
            actions.append("Describe the exact UI text, state, data, status code, or validation message.")
        elif not expected_assertable:
            add_issue("expected_result_not_assertable", "medium", "Expected result lacks an observable assertion target.", 10, field="expected_result")
            actions.append("Make the expected result measurable with visible state, persisted data, or returned value.")

    anchors_ok = bool(anchors)
    checks.append(_check("has_source_anchors", anchors_ok))
    if not anchors_ok:
        add_issue("missing_source_anchors", "medium", "No source anchors are linked to this case.", 12, field="source_anchor_ids")
        actions.append("Link the case to source requirement anchors for traceability.")

    req_priority = _clean_text((requirement or {}).get("priority")).upper()
    case_priority = _clean_text(case.get("priority")).upper()
    priority_aligned = not req_priority or not case_priority or req_priority == case_priority
    checks.append(_check("priority_aligned_with_requirement", priority_aligned))
    if not priority_aligned:
        add_issue(
            "priority_mismatch",
            "medium",
            f"Case priority {case_priority or 'unknown'} does not match requirement priority {req_priority}.",
            10,
            field="priority",
        )
        actions.append("Align the case priority with the requirement or record a review reason.")

    duplicate_candidates = _duplicate_candidates(case, peers)
    duplicate_ok = not duplicate_candidates
    checks.append(_check("no_duplicate_candidates", duplicate_ok))
    if duplicate_candidates:
        add_issue("duplicate_candidate", "medium", "Similar or duplicate test cases were found.", 16, field="title")
        actions.append("Merge duplicate cases or clarify the unique coverage intent.")

    weak_coverage = _is_happy_case(case_type, title, tags) and not _has_non_happy_case(cases_for_requirement)
    checks.append(_check("requirement_has_non_happy_coverage", not weak_coverage))
    if weak_coverage:
        add_issue("weak_coverage_happy_path_only", "low", "This requirement appears to have only happy-path coverage.", 8)
        actions.append("Add negative, boundary, permission, or exception-path cases for the same requirement.")

    score = max(0, min(100, score))
    review_status = "review_passed" if score >= PASS_THRESHOLD and not any(issue["level"] == "high" for issue in issues) else "needs_review"
    return {
        "case_id": case.get("id"),
        "score": score,
        "quality_score": score,
        "issues": issues,
        "suggested_actions": _unique(actions),
        "duplicate_candidates": duplicate_candidates,
        "checks": checks,
        "review_status": review_status,
        "provider_call_performed": False,
        "llm_provider_called": False,
    }


def assess_lightweight_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        assess_test_case_quality(
            item,
            peer_cases=[peer for peer in items if _identity(peer) != _identity(item)],
            requirement_cases=[peer for peer in items if peer.get("requirement_item_id") == item.get("requirement_item_id")],
        )
        for item in items
    ]


def summarize_reviews(items: list[dict[str, Any]]) -> dict[str, Any]:
    issue_counts: Counter[str] = Counter()
    for item in items:
        issue_counts.update(issue.get("code", "unknown") for issue in item.get("issues", []))
    total = len(items)
    passed = sum(1 for item in items if item.get("review_status") == "review_passed")
    avg_score = round(sum(float(item.get("quality_score", item.get("score", 0)) or 0) for item in items) / total, 2) if total else 0
    return {
        "total": total,
        "pass": passed,
        "needs_review": total - passed,
        "avg_score": avg_score,
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def duplicate_groups_from_reviews(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[int, set[int]] = defaultdict(set)
    scores: dict[tuple[int, int], float] = {}
    for item in items:
        source_id = item.get("case_id")
        if source_id is None:
            continue
        for candidate in item.get("duplicate_candidates", []):
            candidate_id = candidate.get("case_id")
            if candidate_id is None:
                continue
            key = tuple(sorted((int(source_id), int(candidate_id))))
            groups[key[0]].update(key)
            scores[key] = max(float(candidate.get("similarity", 0)), scores.get(key, 0))
    result = []
    seen: set[tuple[int, ...]] = set()
    for members in groups.values():
        frozen = tuple(sorted(members))
        if frozen in seen:
            continue
        seen.add(frozen)
        pair_scores = [score for pair, score in scores.items() if set(pair).issubset(members)]
        result.append({"case_ids": list(frozen), "max_similarity": round(max(pair_scores or [0]), 4)})
    return result


def _check(code: str, passed: bool) -> dict[str, Any]:
    return {"code": code, "passed": bool(passed)}


def _identity(item: dict[str, Any]) -> Any:
    return item.get("id") if item.get("id") is not None else id(item)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _step_texts(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if isinstance(value, dict):
        text = _clean_text(value.get("action") or value.get("step") or value.get("description") or value.get("text") or value)
        return [text] if text else []
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_step_texts(item))
        return [text for text in texts if text]
    text = _clean_text(value)
    return [text] if text else []


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _is_generic_expected(value: str) -> bool:
    normalized = value.strip().lower().strip(".!;: ")
    if len(normalized) < 8:
        return True
    return any(normalized == marker or normalized.startswith(marker + " ") for marker in GENERIC_EXPECTATIONS)


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", value.lower()) if token}


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens and right_tokens else 0
    sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    return max(jaccard, sequence)


def _duplicate_candidates(case: dict[str, Any], peers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    case_text = " ".join(
        part
        for part in (
            _clean_text(case.get("title")),
            _clean_text(case.get("expected_result")),
            " ".join(_step_texts(case.get("steps"))),
        )
        if part
    )
    candidates: list[dict[str, Any]] = []
    for peer in peers:
        peer_text = " ".join(
            part
            for part in (
                _clean_text(peer.get("title")),
                _clean_text(peer.get("expected_result")),
                " ".join(_step_texts(peer.get("steps"))),
            )
            if part
        )
        similarity = _similarity(case_text, peer_text)
        same_requirement = case.get("requirement_item_id") is not None and case.get("requirement_item_id") == peer.get("requirement_item_id")
        threshold = 0.82 if same_requirement else 0.9
        if similarity >= threshold:
            candidates.append(
                {
                    "case_id": peer.get("id"),
                    "title": peer.get("title"),
                    "similarity": round(similarity, 4),
                    "requirement_item_id": peer.get("requirement_item_id"),
                }
            )
    return sorted(candidates, key=lambda item: item["similarity"], reverse=True)[:5]


def _is_happy_case(case_type: str, title: str, tags: list[str]) -> bool:
    text = " ".join([case_type, title.lower(), *tags])
    if _contains_any(text, NON_HAPPY_MARKERS):
        return False
    return case_type in {"", "functional", "positive", "happy_path", "normal"} or _contains_any(text, HAPPY_MARKERS)


def _has_non_happy_case(cases: list[dict[str, Any]]) -> bool:
    for case in cases:
        case_type = _clean_text(case.get("case_type")).lower()
        title = _clean_text(case.get("title")).lower()
        tags = [_clean_text(item).lower() for item in _as_list(case.get("tags"))]
        text = " ".join([case_type, title, *tags])
        if _contains_any(text, NON_HAPPY_MARKERS):
            return True
    return False


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
