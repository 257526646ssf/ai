from __future__ import annotations

from typing import Any


def assess_requirement_quality(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    goal = str(item.get("goal") or "").strip()
    text = " ".join(part for part in (title, summary, goal) if part)
    anchors = item.get("source_anchor_ids") or []

    score = 100
    issues: list[dict[str, str]] = []
    actions: list[str] = []

    if len(text) < 30:
        score -= 25
        issues.append({"code": "too_short", "level": "medium", "message": "Requirement text is too short to verify reliably."})
        actions.append("Add user role, trigger, expected outcome, and acceptance criteria.")
    if len(text) > 900:
        score -= 20
        issues.append({"code": "too_broad", "level": "medium", "message": "Requirement text is broad and may contain multiple testable intents."})
        actions.append("Split the requirement into smaller independently verifiable items.")
    if not anchors:
        score -= 20
        issues.append({"code": "missing_source_anchor", "level": "high", "message": "Requirement has no source anchor."})
        actions.append("Bind the item to one or more parsed document blocks.")
    if not item.get("module"):
        score -= 8
        issues.append({"code": "missing_module", "level": "low", "message": "Module is not specified."})
        actions.append("Fill module to improve filtering and ownership.")
    if not item.get("actor") and not _contains_any(text.lower(), ("user", "admin", "operator", "客户", "用户", "管理员")):
        score -= 10
        issues.append({"code": "missing_actor", "level": "low", "message": "User role or actor is unclear."})
        actions.append("Clarify the actor affected by this requirement.")
    if not _contains_any(text.lower(), ("must", "should", "can", "reject", "allow", "when", "if", "需要", "必须", "应", "可以", "校验", "拒绝")):
        score -= 10
        issues.append({"code": "weak_acceptance_signal", "level": "low", "message": "Expected behavior is not explicit enough."})
        actions.append("Use clear expected behavior and acceptance wording.")

    score = max(0, min(100, score))
    if any(issue["code"] == "too_broad" for issue in issues):
        flag = "too_coarse"
    elif any(issue["code"] == "too_short" for issue in issues):
        flag = "too_small"
    elif score < 70:
        flag = "needs_review"
    else:
        flag = "normal"

    return {
        "granularity_score": score,
        "granularity_flag": flag,
        "issues": issues,
        "suggested_actions": actions,
        "source_anchors": anchors,
        "provider_call_performed": False,
        "llm_provider_called": False,
    }


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)
