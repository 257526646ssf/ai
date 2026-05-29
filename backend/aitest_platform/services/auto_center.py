from __future__ import annotations

import base64
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from aitest_platform.models import ApiEndpoint, ApiTestCase, ApiTestLib, AutoCaseFile, AutoExecution, AutoProject, TestCase
from aitest_platform.services.auto_runner import sanitize_runner_payload

MAX_AUTO_FILE_CONTENT_CHARS = 1_000_000
MAX_AUTO_FILE_PATH_CHARS = 512
MAX_AUTO_FILE_NAME_CHARS = 255
MAX_ARTIFACT_TEXT_PREVIEW_BYTES = 256_000
MAX_ARTIFACT_IMAGE_PREVIEW_BYTES = 2_000_000
MAX_CANDIDATE_LIMIT = 200
DEFAULT_CANDIDATE_LIMIT = 20

TEXT_PREVIEW_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".log",
    ".md",
    ".py",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
IMAGE_PREVIEW_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
ARCHIVE_PREVIEW_SUFFIXES = {".har", ".trace", ".zip"}

_URL_LIKE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class AutoCenterValidationError(ValueError):
    pass


class AutoCenterNotFoundError(LookupError):
    pass


def screen_auto_candidates(
    session: Session,
    *,
    payload: dict[str, Any],
    auto_project: AutoProject | None = None,
) -> dict[str, Any]:
    limit = _candidate_limit(payload.get("limit") or payload.get("pageSize"))
    project_id = _optional_int(payload.get("project_id") or payload.get("projectId"))
    if auto_project is not None:
        project_id = auto_project.project_id

    source_case_ids = _unique_ints(payload.get("source_case_ids") or payload.get("sourceCaseIds") or payload.get("case_ids"))
    source_api_case_ids = _unique_ints(
        payload.get("source_api_case_ids") or payload.get("sourceApiCaseIds") or payload.get("api_case_ids") or payload.get("apiCaseIds")
    )
    recommendation_filter = _normalized_recommendation(payload.get("recommendation"))

    candidates: list[dict[str, Any]] = []
    candidates.extend(_test_case_candidates(session, project_id=project_id, source_case_ids=source_case_ids, limit=limit))
    remaining = max(0, limit - len(candidates))
    if remaining:
        candidates.extend(_api_case_candidates(session, project_id=project_id, source_api_case_ids=source_api_case_ids, limit=remaining))

    if recommendation_filter:
        candidates = [item for item in candidates if _normalized_recommendation(item.get("automation_recommendation")) == recommendation_filter]

    candidates = sorted(candidates, key=lambda item: (-int(item.get("score") or 0), str(item.get("candidate_id") or "")))[:limit]
    result = {
        "criteria": sanitize_runner_payload(
            {
                "project_id": project_id,
                "auto_project_id": auto_project.id if auto_project else _optional_int(payload.get("auto_project_id") or payload.get("autoProjectId")),
                "source_case_ids": source_case_ids,
                "source_api_case_ids": source_api_case_ids,
                "limit": limit,
                "recommendation": recommendation_filter or payload.get("recommendation"),
            }
        ),
        "candidates": sanitize_runner_payload(candidates),
        "total": len(candidates),
        "generated_at": _now_iso(),
    }
    if auto_project is not None:
        _store_auto_center_config(auto_project, candidates=candidates, criteria=result["criteria"])
    return result


def list_project_candidates(session: Session, project: AutoProject) -> dict[str, Any]:
    center = _auto_center_config(project)
    candidates = center.get("candidates")
    if not isinstance(candidates, list):
        fresh = screen_auto_candidates(session, payload={"auto_project_id": project.id, "project_id": project.project_id}, auto_project=project)
        candidates = fresh["candidates"]
        center = _auto_center_config(project)
    selection = center.get("selection") if isinstance(center.get("selection"), dict) else {}
    return sanitize_runner_payload(
        {
            "auto_project_id": project.id,
            "project_id": project.project_id,
            "candidates": candidates,
            "selection": selection,
            "total": len(candidates),
        }
    )


def update_candidate_selection(session: Session, project: AutoProject, payload: dict[str, Any]) -> dict[str, Any]:
    current = list_project_candidates(session, project)
    candidates = current.get("candidates") if isinstance(current.get("candidates"), list) else []
    candidate_ids = {str(item.get("candidate_id") or item.get("id")) for item in candidates if isinstance(item, dict)}

    selected = _candidate_key_set(
        payload.get("selected_candidate_ids")
        or payload.get("selectedCandidateIds")
        or payload.get("selected_ids")
        or payload.get("selectedIds")
        or payload.get("selected")
        or payload.get("candidates")
    )
    excluded = _candidate_key_set(
        payload.get("excluded_candidate_ids")
        or payload.get("excludedCandidateIds")
        or payload.get("excluded_ids")
        or payload.get("excludedIds")
        or payload.get("excluded")
    )

    selected.update(f"case:{item}" for item in _unique_ints(payload.get("selected_source_case_ids") or payload.get("selectedSourceCaseIds")))
    selected.update(f"api_case:{item}" for item in _unique_ints(payload.get("selected_source_api_case_ids") or payload.get("selectedSourceApiCaseIds")))
    excluded.update(f"case:{item}" for item in _unique_ints(payload.get("excluded_source_case_ids") or payload.get("excludedSourceCaseIds")))
    excluded.update(f"api_case:{item}" for item in _unique_ints(payload.get("excluded_source_api_case_ids") or payload.get("excludedSourceApiCaseIds")))
    for item in payload.get("selections") or []:
        if not isinstance(item, dict):
            continue
        key = _normalize_candidate_key(item.get("candidate_id") or item.get("id"))
        if key is None and item.get("source_case_id") is not None:
            key = f"case:{item.get('source_case_id')}"
        if key is None and item.get("source_api_case_id") is not None:
            key = f"api_case:{item.get('source_api_case_id')}"
        if key is None:
            continue
        if item.get("selected") is False:
            excluded.add(key)
            selected.discard(key)
        else:
            selected.add(key)

    if payload.get("select_all") or payload.get("selectAll"):
        selected = set(candidate_ids)
    selected -= excluded

    selection = {
        "selected_candidate_ids": sorted(selected),
        "excluded_candidate_ids": sorted(excluded),
        "selected_source_case_ids": sorted(_ids_from_candidate_keys(selected, "case")),
        "selected_source_api_case_ids": sorted(_ids_from_candidate_keys(selected, "api_case")),
        "excluded_source_case_ids": sorted(_ids_from_candidate_keys(excluded, "case")),
        "excluded_source_api_case_ids": sorted(_ids_from_candidate_keys(excluded, "api_case")),
        "updated_at": _now_iso(),
    }
    center = _auto_center_config(project)
    center["selection"] = sanitize_runner_payload(selection)
    project.extra_config = _with_auto_center_config(project, center)
    return sanitize_runner_payload({"auto_project_id": project.id, "selection": selection, "candidates": candidates, "total": len(candidates)})


def selected_generation_candidates(session: Session, project: AutoProject, payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    explicit_case_ids = _unique_ints(payload.get("source_case_ids") or payload.get("sourceCaseIds") or payload.get("case_ids") or payload.get("caseIds"))
    explicit_api_case_ids = _unique_ints(
        payload.get("source_api_case_ids") or payload.get("sourceApiCaseIds") or payload.get("api_case_ids") or payload.get("apiCaseIds")
    )
    if explicit_case_ids or explicit_api_case_ids:
        candidates = screen_auto_candidates(
            session,
            payload={"source_case_ids": explicit_case_ids, "source_api_case_ids": explicit_api_case_ids, "limit": MAX_CANDIDATE_LIMIT},
            auto_project=project,
        )["candidates"]
        return candidates

    center = _auto_center_config(project)
    selection = center.get("selection")
    if not isinstance(selection, dict):
        return None
    candidates = center.get("candidates")
    if not isinstance(candidates, list):
        candidates = list_project_candidates(session, project).get("candidates") or []

    selected = set(str(item) for item in (selection.get("selected_candidate_ids") or []))
    excluded = set(str(item) for item in (selection.get("excluded_candidate_ids") or []))
    if selected:
        filtered = [item for item in candidates if str(item.get("candidate_id") or item.get("id")) in selected and str(item.get("candidate_id") or item.get("id")) not in excluded]
    else:
        filtered = [item for item in candidates if str(item.get("candidate_id") or item.get("id")) not in excluded]
    return [item for item in filtered if isinstance(item, dict)]


def playwright_framework_files(project: AutoProject) -> dict[str, str]:
    extension = playwright_extension(project)
    config_name = "playwright.config.ts" if extension == "ts" else "playwright.config.js"
    config = _playwright_ts_config() if extension == "ts" else _playwright_js_config()
    fixture_name = f"fixtures/test-fixtures.{extension}"
    page_name = f"pages/BasePage.{extension}"
    smoke_name = f"tests/generated-smoke.spec.{extension}"
    return {
        "README.md": (
            f"# {project.name}\n\n"
            "Generated Playwright automation project.\n\n"
            "## Run\n\n"
            "```bash\nnpm install\nnpx playwright test\n```\n"
        ),
        "package.json": json.dumps(
            {
                "scripts": {
                    "test": "playwright test",
                    "test:headed": "playwright test --headed",
                    "report": "playwright show-report",
                },
                "devDependencies": {"@playwright/test": "^1.44.0"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        config_name: config,
        fixture_name: _playwright_fixture_content(extension),
        page_name: _playwright_page_content(extension),
        smoke_name: _playwright_smoke_content(extension),
        ".gitignore": "node_modules/\nplaywright-report/\ntest-results/\n.env\n",
    }


def build_case_file_payloads(session: Session, project: AutoProject, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("source_case_id") is not None:
            case = session.get(TestCase, int(candidate["source_case_id"]))
            if case is not None and not case.is_deleted and case.project_id == project.project_id:
                payloads.append(_case_file_payload_from_test_case(project, case, candidate))
        elif candidate.get("source_api_case_id") is not None:
            api_case = session.get(ApiTestCase, int(candidate["source_api_case_id"]))
            if api_case is not None and not api_case.is_deleted and _api_case_project_id(session, api_case) == project.project_id:
                payloads.append(_case_file_payload_from_api_case(session, project, api_case, candidate))
    return payloads


def fallback_case_file_payload(project: AutoProject) -> dict[str, Any]:
    if is_playwright_project(project):
        extension = playwright_extension(project)
        return {
            "file_name": f"generated-smoke.spec.{extension}",
            "file_path": f"tests/generated-smoke.spec.{extension}",
            "content": _playwright_smoke_content(extension),
            "case_count": 1,
            "automation_dsl": {"runner": "playwright", "steps": [{"action": "page.goto"}, {"action": "expect.visible"}]},
        }
    return {
        "file_name": "test_generated.py",
        "file_path": "tests/test_generated.py",
        "content": "def test_generated_placeholder():\n    assert True\n",
        "case_count": 1,
        "automation_dsl": {"runner": "pytest", "steps": [{"action": "placeholder_assert"}]},
    }


def is_playwright_project(project: AutoProject) -> bool:
    return "playwright" in str(project.framework or "").lower()


def playwright_extension(project: AutoProject) -> str:
    language = str(project.language or "").lower()
    return "ts" if language in {"ts", "typescript"} else "js"


def validate_auto_file_path(value: Any) -> str:
    if not isinstance(value, str):
        raise AutoCenterValidationError("file_path must be a string")
    raw = value.strip().replace("\\", "/")
    if not raw:
        raise AutoCenterValidationError("file_path must not be empty")
    if len(raw) > MAX_AUTO_FILE_PATH_CHARS:
        raise AutoCenterValidationError("file_path is too long")
    if "\x00" in raw or _URL_LIKE_RE.match(raw) or _WINDOWS_DRIVE_RE.match(raw) or raw.startswith(("/", "\\")):
        raise AutoCenterValidationError("file_path must be a safe relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.name in {"", ".", ".."}:
        raise AutoCenterValidationError("file_path must point to a file")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise AutoCenterValidationError("file_path must not contain empty, dot, or parent segments")
    return path.as_posix()


def validate_auto_file_name(value: Any) -> str:
    if not isinstance(value, str):
        raise AutoCenterValidationError("file_name must be a string")
    raw = value.strip()
    if not raw:
        raise AutoCenterValidationError("file_name must not be empty")
    if len(raw) > MAX_AUTO_FILE_NAME_CHARS:
        raise AutoCenterValidationError("file_name is too long")
    if "\x00" in raw or "/" in raw or "\\" in raw or raw in {".", ".."} or _URL_LIKE_RE.match(raw) or _WINDOWS_DRIVE_RE.match(raw):
        raise AutoCenterValidationError("file_name must be a safe file name")
    return raw


def validate_auto_file_content(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AutoCenterValidationError("content must be a string")
    if len(value) > MAX_AUTO_FILE_CONTENT_CHARS:
        raise AutoCenterValidationError("content is too large")
    return value


def build_case_file_create_fields(project: AutoProject, payload: dict[str, Any]) -> dict[str, Any]:
    file_path = validate_auto_file_path(payload.get("file_path") or payload.get("filePath") or payload.get("path") or payload.get("file_name") or payload.get("fileName"))
    file_name = validate_auto_file_name(payload.get("file_name") or payload.get("fileName") or PurePosixPath(file_path).name)
    content = validate_auto_file_content(payload.get("content", ""))
    return {
        "auto_project_id": project.id,
        "source_case_id": _optional_int(payload.get("source_case_id") or payload.get("sourceCaseId")),
        "source_api_case_id": _optional_int(payload.get("source_api_case_id") or payload.get("sourceApiCaseId")),
        "file_name": file_name,
        "file_path": file_path,
        "content": content,
        "case_count": _non_negative_int(payload.get("case_count") or payload.get("caseCount"), default=1),
        "automation_dsl": sanitize_runner_payload(payload.get("automation_dsl") if "automation_dsl" in payload else payload.get("automationDsl")),
        "last_result": sanitize_runner_payload(payload.get("last_result") if "last_result" in payload else payload.get("lastResult")),
    }


def build_case_file_patch_fields(case_file: AutoCaseFile, payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    new_path = payload.get("file_path") if "file_path" in payload else payload.get("filePath") if "filePath" in payload else None
    if new_path is not None:
        fields["file_path"] = validate_auto_file_path(new_path)
    if "file_name" in payload or "fileName" in payload:
        fields["file_name"] = validate_auto_file_name(payload.get("file_name") if "file_name" in payload else payload.get("fileName"))
    elif "file_path" in fields:
        fields["file_name"] = PurePosixPath(fields["file_path"]).name
    if "content" in payload:
        fields["content"] = validate_auto_file_content(payload.get("content"))
    if "case_count" in payload or "caseCount" in payload:
        fields["case_count"] = _non_negative_int(payload.get("case_count") if "case_count" in payload else payload.get("caseCount"), default=case_file.case_count or 0)
    if "automation_dsl" in payload or "automationDsl" in payload:
        fields["automation_dsl"] = sanitize_runner_payload(payload.get("automation_dsl") if "automation_dsl" in payload else payload.get("automationDsl"))
    if "last_result" in payload or "lastResult" in payload:
        fields["last_result"] = sanitize_runner_payload(payload.get("last_result") if "last_result" in payload else payload.get("lastResult"))
    if "source_case_id" in payload or "sourceCaseId" in payload:
        fields["source_case_id"] = _optional_int(payload.get("source_case_id") if "source_case_id" in payload else payload.get("sourceCaseId"))
    if "source_api_case_id" in payload or "sourceApiCaseId" in payload:
        fields["source_api_case_id"] = _optional_int(payload.get("source_api_case_id") if "source_api_case_id" in payload else payload.get("sourceApiCaseId"))
    return fields


def auto_file_public_dict(case_file: AutoCaseFile) -> dict[str, Any]:
    return sanitize_runner_payload(
        {
            "id": case_file.id,
            "auto_project_id": case_file.auto_project_id,
            "source_case_id": case_file.source_case_id,
            "source_api_case_id": case_file.source_api_case_id,
            "file_name": case_file.file_name,
            "file_path": case_file.file_path,
            "content": case_file.content,
            "case_count": case_file.case_count,
            "automation_dsl": case_file.automation_dsl,
            "last_result": case_file.last_result,
            "created_at": case_file.created_at.isoformat() if getattr(case_file, "created_at", None) else None,
            "updated_at": case_file.updated_at.isoformat() if getattr(case_file, "updated_at", None) else None,
        }
    )


def auto_execution_detail(execution: AutoExecution) -> dict[str, Any]:
    artifacts = sanitize_runner_payload(execution.artifacts or {})
    runner = artifacts.get("runner") if isinstance(artifacts, dict) and isinstance(artifacts.get("runner"), dict) else {}
    evidence = _execution_evidence(execution)
    return sanitize_runner_payload(
        {
            "id": execution.id,
            "execution_id": execution.id,
            "auto_project_id": execution.auto_project_id,
            "status": execution.status,
            "summary": execution.summary or {},
            "log_excerpt": execution.log_excerpt or "",
            "artifacts": artifacts,
            "evidence": evidence,
            "runner": runner,
            "duration_ms": execution.duration_ms,
            "duration": execution.duration_ms,
            "executed_at": execution.executed_at.isoformat() if getattr(execution, "executed_at", None) else None,
        }
    )


def auto_execution_artifacts_payload(execution: AutoExecution) -> dict[str, Any]:
    artifacts = sanitize_runner_payload(execution.artifacts or {})
    evidence = _execution_evidence(execution)
    return sanitize_runner_payload(
        {
            "execution_id": execution.id,
            "status": execution.status,
            "artifact_root": artifacts.get("artifact_dir") if isinstance(artifacts, dict) else None,
            "download": {
                "available": True,
                "url": f"/api/v2/auto-executions/{execution.id}/artifacts/download",
                "filename": f"auto-execution-{execution.id}-artifacts.zip",
                "mime_type": "application/zip",
            },
            "evidence": evidence,
            "artifacts": artifacts,
            "total": len(evidence),
        }
    )


def preview_auto_execution_artifact(execution: AutoExecution, relative_path: str) -> dict[str, Any]:
    root = _artifact_root(execution)
    if root is None:
        raise AutoCenterNotFoundError("Artifact root is not available")
    safe_relative = validate_auto_file_path(relative_path)
    target = (root / safe_relative).resolve()
    if not _is_relative_to(target, root):
        raise AutoCenterValidationError("relativePath escaped artifact root")
    if not target.exists() or not target.is_file():
        raise AutoCenterNotFoundError("Artifact file not found")

    suffix = target.suffix.lower()
    size = target.stat().st_size
    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if suffix in TEXT_PREVIEW_SUFFIXES and mime_type == "application/octet-stream":
        mime_type = "text/plain; charset=utf-8"
    download_url = f"/api/v2/auto-executions/{execution.id}/artifacts/download"
    base = {
        "execution_id": execution.id,
        "relative_path": safe_relative,
        "size_bytes": size,
        "mime_type": mime_type,
        "mime": mime_type,
        "download_url": download_url,
        "download": {
            "available": True,
            "url": download_url,
        },
    }
    if suffix in IMAGE_PREVIEW_SUFFIXES:
        if size > MAX_ARTIFACT_IMAGE_PREVIEW_BYTES:
            return {**base, "preview_type": "image", "preview_available": False, "previewable": False, "reason": "image is too large for inline preview"}
        return {
            **base,
            "preview_type": "image",
            "preview_available": True,
            "previewable": True,
            "content_base64": base64.b64encode(target.read_bytes()).decode("ascii"),
        }
    if suffix in TEXT_PREVIEW_SUFFIXES or mime_type.startswith("text/"):
        data = target.read_bytes()
        truncated = len(data) > MAX_ARTIFACT_TEXT_PREVIEW_BYTES
        text = data[:MAX_ARTIFACT_TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace")
        return {
            **base,
            "preview_type": "text",
            "preview_available": True,
            "previewable": True,
            "content": sanitize_runner_payload(text),
            "text": sanitize_runner_payload(text),
            "truncated": truncated,
        }
    if suffix in ARCHIVE_PREVIEW_SUFFIXES:
        return {**base, "preview_type": "archive", "preview_available": False, "previewable": False, "reason": "archive preview is metadata only"}
    return {**base, "preview_type": "binary", "preview_available": False, "previewable": False, "reason": "binary preview is metadata only"}


def _test_case_candidates(
    session: Session,
    *,
    project_id: int | None,
    source_case_ids: list[int],
    limit: int,
) -> list[dict[str, Any]]:
    stmt = select(TestCase).where(TestCase.is_deleted.is_(False))
    if project_id is not None:
        stmt = stmt.where(TestCase.project_id == project_id)
    if source_case_ids:
        stmt = stmt.where(TestCase.id.in_(source_case_ids))
    stmt = stmt.order_by(TestCase.id).limit(limit)
    return [_candidate_from_test_case(case) for case in session.scalars(stmt)]


def _api_case_candidates(
    session: Session,
    *,
    project_id: int | None,
    source_api_case_ids: list[int],
    limit: int,
) -> list[dict[str, Any]]:
    stmt = (
        select(ApiTestCase, ApiEndpoint, ApiTestLib)
        .join(ApiEndpoint, ApiEndpoint.id == ApiTestCase.endpoint_id)
        .join(ApiTestLib, ApiTestLib.id == ApiTestCase.lib_id)
        .where(ApiTestCase.is_deleted.is_(False), ApiEndpoint.is_deleted.is_(False), ApiTestLib.is_deleted.is_(False))
    )
    if project_id is not None:
        stmt = stmt.where(ApiTestLib.project_id == project_id)
    if source_api_case_ids:
        stmt = stmt.where(ApiTestCase.id.in_(source_api_case_ids))
    stmt = stmt.order_by(ApiTestCase.id).limit(limit)
    return [_candidate_from_api_case(api_case, endpoint) for api_case, endpoint, _lib in session.execute(stmt).all()]


def _candidate_from_test_case(case: TestCase) -> dict[str, Any]:
    score, reasons = _score_test_case(case)
    recommendation = _recommendation_from_score(score)
    automation_type = _automation_type_from_case_type(case.case_type)
    title = _safe_text(case.title or case.case_number or f"TestCase {case.id}")
    return {
        "id": f"case:{case.id}",
        "candidate_id": f"case:{case.id}",
        "source_case_id": case.id,
        "source_api_case_id": None,
        "title": title,
        "automation_recommendation": recommendation,
        "automation_type": automation_type,
        "reason": "; ".join(reasons),
        "reasons": reasons,
        "priority": case.priority or "P2",
        "score": score,
    }


def _candidate_from_api_case(api_case: ApiTestCase, endpoint: ApiEndpoint) -> dict[str, Any]:
    score, reasons = _score_api_case(api_case, endpoint)
    recommendation = _recommendation_from_score(score)
    title = _safe_text(api_case.name or endpoint.name or f"{endpoint.method} {endpoint.path}")
    return {
        "id": f"api_case:{api_case.id}",
        "candidate_id": f"api_case:{api_case.id}",
        "source_case_id": None,
        "source_api_case_id": api_case.id,
        "title": title,
        "automation_recommendation": recommendation,
        "automation_type": "api",
        "reason": "; ".join(reasons),
        "reasons": reasons,
        "priority": "P1" if 200 <= int(api_case.expected_status or 0) < 300 else "P2",
        "score": score,
    }


def _score_test_case(case: TestCase) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 35
    priority_bonus = {"P0": 30, "P1": 24, "P2": 16, "P3": 8}.get(str(case.priority or "").upper(), 12)
    score += priority_bonus
    reasons.append(f"priority {case.priority or 'P2'}")
    if str(case.status or "").lower() in {"confirmed", "ready"}:
        score += 12
        reasons.append("status is ready for automation")
    elif str(case.status or "").lower() == "draft":
        score += 4
        reasons.append("draft case can be automated after review")
    case_type = str(case.case_type or "").lower()
    if any(marker in case_type for marker in ("ui", "web", "e2e", "smoke", "regression", "functional")):
        score += 12
        reasons.append("case type has deterministic automation value")
    steps = case.steps
    if isinstance(steps, list) and steps:
        score += min(10, len(steps) * 2)
        reasons.append("structured steps are available")
    elif isinstance(steps, str) and steps.strip():
        score += 5
        reasons.append("text steps are available")
    return min(100, score), reasons


def _score_api_case(api_case: ApiTestCase, endpoint: ApiEndpoint) -> tuple[int, list[str]]:
    reasons = ["API case has structured request data"]
    score = 55
    if api_case.assertions:
        score += 15
        reasons.append("assertions are available")
    if endpoint.method and endpoint.path:
        score += 10
        reasons.append("endpoint method and path are available")
    if str(api_case.status or "").lower() in {"ready", "confirmed"}:
        score += 10
        reasons.append("status is ready for automation")
    if 200 <= int(api_case.expected_status or 0) < 300:
        score += 5
        reasons.append("success status is deterministic")
    return min(100, score), reasons


def _recommendation_from_score(score: int) -> str:
    if score >= 85:
        return "highly_recommended"
    if score >= 65:
        return "recommended"
    if score >= 45:
        return "optional"
    return "manual_review"


def _automation_type_from_case_type(case_type: str | None) -> str:
    lowered = str(case_type or "").lower()
    if "api" in lowered or "interface" in lowered:
        return "api"
    if any(marker in lowered for marker in ("ui", "web", "e2e")):
        return "ui"
    return "functional"


def _case_file_payload_from_test_case(project: AutoProject, case: TestCase, candidate: dict[str, Any]) -> dict[str, Any]:
    if is_playwright_project(project):
        extension = playwright_extension(project)
        file_path = f"tests/ui_case_{case.id}.spec.{extension}"
        content = _playwright_ui_case_content(extension, case)
    else:
        file_path = f"tests/test_case_{case.id}.py"
        content = _pytest_case_content(case)
    return {
        "source_case_id": case.id,
        "source_api_case_id": None,
        "file_name": PurePosixPath(file_path).name,
        "file_path": file_path,
        "content": content,
        "case_count": 1,
        "automation_dsl": sanitize_runner_payload(
            {
                "candidate_id": candidate.get("candidate_id"),
                "automation_type": candidate.get("automation_type"),
                "source_case_id": case.id,
                "title": case.title,
                "steps": case.steps,
                "expected_result": case.expected_result,
            }
        ),
    }


def _case_file_payload_from_api_case(session: Session, project: AutoProject, api_case: ApiTestCase, candidate: dict[str, Any]) -> dict[str, Any]:
    endpoint = session.get(ApiEndpoint, api_case.endpoint_id)
    if is_playwright_project(project):
        extension = playwright_extension(project)
        file_path = f"tests/api_case_{api_case.id}.spec.{extension}"
        content = _playwright_api_case_content(extension, api_case, endpoint)
    else:
        file_path = f"tests/test_api_case_{api_case.id}.py"
        content = _pytest_api_case_content(api_case, endpoint)
    return {
        "source_case_id": None,
        "source_api_case_id": api_case.id,
        "file_name": PurePosixPath(file_path).name,
        "file_path": file_path,
        "content": content,
        "case_count": 1,
        "automation_dsl": sanitize_runner_payload(
            {
                "candidate_id": candidate.get("candidate_id"),
                "automation_type": "api",
                "source_api_case_id": api_case.id,
                "endpoint": {"method": getattr(endpoint, "method", None), "path": getattr(endpoint, "path", None)},
                "expected_status": api_case.expected_status,
                "assertions": api_case.assertions,
            }
        ),
    }


def _pytest_case_content(case: TestCase) -> str:
    title = _safe_repr(case.title or f"test case {case.id}")
    expected = _safe_repr(case.expected_result or "expected result")
    return (
        f"def test_case_{case.id}_generated():\n"
        f"    title = {title}\n"
        f"    expected_result = {expected}\n"
        "    assert title\n"
        "    assert expected_result\n"
    )


def _pytest_api_case_content(api_case: ApiTestCase, endpoint: ApiEndpoint | None) -> str:
    method = _safe_repr(getattr(endpoint, "method", "GET") or "GET")
    path = _safe_repr(getattr(endpoint, "path", "/") or "/")
    expected = int(api_case.expected_status or 200)
    return (
        f"def test_api_case_{api_case.id}_contract():\n"
        f"    method = {method}\n"
        f"    path = {path}\n"
        f"    expected_status = {expected}\n"
        "    assert method\n"
        "    assert path.startswith('/')\n"
        "    assert 100 <= expected_status < 600\n"
    )


def _playwright_ui_case_content(extension: str, case: TestCase) -> str:
    title = _safe_js_string(case.title or f"case {case.id}")
    expected = _safe_js_string(case.expected_result or "expected result")
    if extension == "ts":
        return (
            "import { test, expect } from '../fixtures/test-fixtures';\n\n"
            f"test({title}, async ({{ basePage }}) => {{\n"
            "  await basePage.openBlank();\n"
            f"  test.info().annotations.push({{ type: 'expected', description: {expected} }});\n"
            "  await expect(basePage.body).toBeVisible();\n"
            "});\n"
        )
    return (
        "const { test, expect } = require('../fixtures/test-fixtures');\n\n"
        f"test({title}, async ({{ basePage }}) => {{\n"
        "  await basePage.openBlank();\n"
        f"  test.info().annotations.push({{ type: 'expected', description: {expected} }});\n"
        "  await expect(basePage.body).toBeVisible();\n"
        "});\n"
    )


def _playwright_api_case_content(extension: str, api_case: ApiTestCase, endpoint: ApiEndpoint | None) -> str:
    name = _safe_js_string(api_case.name or f"api case {api_case.id}")
    method = _safe_js_string(getattr(endpoint, "method", "GET") or "GET")
    path = _safe_js_string(getattr(endpoint, "path", "/") or "/")
    expected = int(api_case.expected_status or 200)
    if extension == "ts":
        return (
            "import { test, expect } from '@playwright/test';\n\n"
            f"test({name}, async () => {{\n"
            f"  const method = {method};\n"
            f"  const path = {path};\n"
            f"  const expectedStatus = {expected};\n"
            "  expect(method.length).toBeGreaterThan(0);\n"
            "  expect(path.startsWith('/')).toBeTruthy();\n"
            "  expect(expectedStatus).toBeGreaterThanOrEqual(100);\n"
            "});\n"
        )
    return (
        "const { test, expect } = require('@playwright/test');\n\n"
        f"test({name}, async () => {{\n"
        f"  const method = {method};\n"
        f"  const path = {path};\n"
        f"  const expectedStatus = {expected};\n"
        "  expect(method.length).toBeGreaterThan(0);\n"
        "  expect(path.startsWith('/')).toBeTruthy();\n"
        "  expect(expectedStatus).toBeGreaterThanOrEqual(100);\n"
        "});\n"
    )


def _playwright_js_config() -> str:
    return (
        "const { defineConfig } = require('@playwright/test');\n\n"
        "module.exports = defineConfig({\n"
        "  testDir: './tests',\n"
        "  timeout: 30000,\n"
        "  retries: 0,\n"
        "  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],\n"
        "  use: {\n"
        "    trace: 'retain-on-failure',\n"
        "    screenshot: 'only-on-failure',\n"
        "    video: 'retain-on-failure'\n"
        "  },\n"
        "  outputDir: 'test-results'\n"
        "});\n"
    )


def _playwright_ts_config() -> str:
    return (
        "import { defineConfig } from '@playwright/test';\n\n"
        "export default defineConfig({\n"
        "  testDir: './tests',\n"
        "  timeout: 30000,\n"
        "  retries: 0,\n"
        "  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],\n"
        "  use: {\n"
        "    trace: 'retain-on-failure',\n"
        "    screenshot: 'only-on-failure',\n"
        "    video: 'retain-on-failure'\n"
        "  },\n"
        "  outputDir: 'test-results'\n"
        "});\n"
    )


def _playwright_fixture_content(extension: str) -> str:
    if extension == "ts":
        return (
            "import { test as base, expect } from '@playwright/test';\n"
            "import { BasePage } from '../pages/BasePage';\n\n"
            "type Fixtures = { basePage: BasePage };\n\n"
            "const test = base.extend<Fixtures>({\n"
            "  basePage: async ({ page }, use) => {\n"
            "    await use(new BasePage(page));\n"
            "  }\n"
            "});\n\n"
            "export { test, expect };\n"
        )
    return (
        "const base = require('@playwright/test');\n"
        "const { BasePage } = require('../pages/BasePage');\n\n"
        "const test = base.test.extend({\n"
        "  basePage: async ({ page }, use) => {\n"
        "    await use(new BasePage(page));\n"
        "  }\n"
        "});\n\n"
        "module.exports = { test, expect: base.expect };\n"
    )


def _playwright_page_content(extension: str) -> str:
    if extension == "ts":
        return (
            "import type { Page, Locator } from '@playwright/test';\n\n"
            "export class BasePage {\n"
            "  readonly page: Page;\n"
            "  readonly body: Locator;\n\n"
            "  constructor(page: Page) {\n"
            "    this.page = page;\n"
            "    this.body = page.locator('body');\n"
            "  }\n\n"
            "  async openBlank() {\n"
            "    await this.page.goto('about:blank');\n"
            "  }\n"
            "}\n"
        )
    return (
        "class BasePage {\n"
        "  constructor(page) {\n"
        "    this.page = page;\n"
        "    this.body = page.locator('body');\n"
        "  }\n\n"
        "  async openBlank() {\n"
        "    await this.page.goto('about:blank');\n"
        "  }\n"
        "}\n\n"
        "module.exports = { BasePage };\n"
    )


def _playwright_smoke_content(extension: str) -> str:
    if extension == "ts":
        return (
            "import { test, expect } from '../fixtures/test-fixtures';\n\n"
            "test('generated smoke', async ({ basePage }) => {\n"
            "  await basePage.openBlank();\n"
            "  await expect(basePage.body).toBeVisible();\n"
            "});\n"
        )
    return (
        "const { test, expect } = require('../fixtures/test-fixtures');\n\n"
        "test('generated smoke', async ({ basePage }) => {\n"
        "  await basePage.openBlank();\n"
        "  await expect(basePage.body).toBeVisible();\n"
        "});\n"
    )


def _execution_evidence(execution: AutoExecution) -> list[dict[str, Any]]:
    artifacts = execution.artifacts or {}
    if not isinstance(artifacts, dict):
        return []
    root = _artifact_root(execution)
    entries: list[dict[str, Any]] = []
    raw_evidence = artifacts.get("evidence")
    if isinstance(raw_evidence, list):
        entries.extend(item for item in raw_evidence if isinstance(item, dict))
    raw_files = artifacts.get("files")
    if isinstance(raw_files, list):
        entries.extend(item for item in raw_files if isinstance(item, dict) and item.get("path"))
    runner_log = artifacts.get("runner_log")
    if runner_log:
        entries.append({"kind": "log", "path": runner_log, "relative_path": "runner.log", "source": "runner"})

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in entries:
        relative_path = item.get("relative_path") or item.get("relativePath")
        path_value = item.get("path")
        if not relative_path and path_value and root is not None:
            try:
                source = Path(str(path_value)).resolve()
                if _is_relative_to(source, root):
                    relative_path = source.relative_to(root).as_posix()
            except (OSError, ValueError):
                relative_path = None
        if not relative_path:
            continue
        relative_path = str(relative_path).replace("\\", "/")
        try:
            relative_path = validate_auto_file_path(relative_path)
        except AutoCenterValidationError:
            continue
        if relative_path in seen:
            continue
        seen.add(relative_path)
        size = item.get("size_bytes")
        if size is None and root is not None:
            target = (root / relative_path).resolve()
            if _is_relative_to(target, root) and target.exists() and target.is_file():
                size = target.stat().st_size
        kind = item.get("kind") or item.get("type") or item.get("artifact_type") or _kind_from_suffix(relative_path)
        normalized.append(
            sanitize_runner_payload(
                {
                    "kind": kind,
                    "type": kind,
                    "relative_path": relative_path,
                    "relativePath": relative_path,
                    "size_bytes": size,
                    "source": item.get("source"),
                    "preview": {
                        "available": True,
                        "url": f"/api/v2/auto-executions/{execution.id}/artifacts/preview?relativePath={relative_path}",
                    },
                    "download": {
                        "available": True,
                        "url": f"/api/v2/auto-executions/{execution.id}/artifacts/download",
                    },
                }
            )
        )
    return normalized


def _kind_from_suffix(relative_path: str) -> str:
    suffix = PurePosixPath(relative_path).suffix.lower()
    if suffix in IMAGE_PREVIEW_SUFFIXES:
        return "screenshot"
    if suffix in {".webm", ".mp4"}:
        return "video"
    if suffix in ARCHIVE_PREVIEW_SUFFIXES:
        return "trace"
    if suffix in {".html"}:
        return "report"
    if suffix in {".xml"}:
        return "junit"
    if suffix in {".log", ".txt"}:
        return "log"
    return "file"


def _artifact_root(execution: AutoExecution) -> Path | None:
    artifacts = execution.artifacts or {}
    if not isinstance(artifacts, dict):
        return None
    artifact_dir = artifacts.get("artifact_dir")
    if not artifact_dir:
        return None
    try:
        return Path(str(artifact_dir)).resolve()
    except OSError:
        return None


def _store_auto_center_config(project: AutoProject, *, candidates: list[dict[str, Any]], criteria: dict[str, Any]) -> None:
    center = _auto_center_config(project)
    center["candidates"] = sanitize_runner_payload(candidates)
    center["criteria"] = sanitize_runner_payload(criteria)
    center["updated_at"] = _now_iso()
    project.extra_config = _with_auto_center_config(project, center)


def _auto_center_config(project: AutoProject) -> dict[str, Any]:
    config = project.extra_config if isinstance(project.extra_config, dict) else {}
    center = config.get("automation_center")
    return dict(center) if isinstance(center, dict) else {}


def _with_auto_center_config(project: AutoProject, center: dict[str, Any]) -> dict[str, Any]:
    config = dict(project.extra_config or {}) if isinstance(project.extra_config, dict) else {}
    config["automation_center"] = sanitize_runner_payload(center)
    return config


def _api_case_project_id(session: Session, api_case: ApiTestCase) -> int | None:
    lib = session.get(ApiTestLib, api_case.lib_id)
    return lib.project_id if lib is not None and not lib.is_deleted else None


def _candidate_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = DEFAULT_CANDIDATE_LIMIT
    return max(1, min(MAX_CANDIDATE_LIMIT, limit))


def _unique_ints(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else str(value).split(",")
    result: list[int] = []
    seen: set[int] = set()
    for item in raw_items:
        try:
            parsed = int(item.get("id") if isinstance(item, dict) else item)
        except (TypeError, ValueError):
            continue
        if parsed not in seen:
            seen.add(parsed)
            result.append(parsed)
    return result


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _non_negative_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AutoCenterValidationError("case_count must be an integer") from exc
    if parsed < 0:
        raise AutoCenterValidationError("case_count must be non-negative")
    return parsed


def _candidate_key_set(value: Any) -> set[str]:
    if value in (None, ""):
        return set()
    raw_items = value if isinstance(value, list) else [value]
    keys: set[str] = set()
    for item in raw_items:
        if isinstance(item, dict):
            key = item.get("candidate_id") or item.get("id")
            if key is None and item.get("source_case_id") is not None:
                key = f"case:{item.get('source_case_id')}"
            if key is None and item.get("source_api_case_id") is not None:
                key = f"api_case:{item.get('source_api_case_id')}"
        else:
            key = item
        normalized = _normalize_candidate_key(key)
        if normalized:
            keys.add(normalized)
    return keys


def _normalize_candidate_key(value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if raw.startswith("case:") or raw.startswith("api_case:"):
        return raw
    if raw.startswith("api:"):
        return "api_case:" + raw.split(":", 1)[1]
    if raw.isdigit():
        return f"case:{raw}"
    return raw


def _ids_from_candidate_keys(keys: Iterable[str], prefix: str) -> list[int]:
    values: list[int] = []
    marker = f"{prefix}:"
    for key in keys:
        if str(key).startswith(marker):
            try:
                values.append(int(str(key).split(":", 1)[1]))
            except (TypeError, ValueError):
                continue
    return values


def _normalized_recommendation(value: Any) -> str | None:
    if value in (None, "", False):
        return None
    if value is True:
        return "recommended"
    lowered = str(value).strip().lower()
    aliases = {
        "high": "highly_recommended",
        "highly": "highly_recommended",
        "yes": "recommended",
        "true": "recommended",
        "manual": "manual_review",
    }
    return aliases.get(lowered, lowered)


def _safe_text(value: str) -> str:
    return str(sanitize_runner_payload(value or ""))[:255]


def _safe_repr(value: Any) -> str:
    return repr(str(sanitize_runner_payload(value or "")))


def _safe_js_string(value: Any) -> str:
    return json.dumps(str(sanitize_runner_payload(value or "")), ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
