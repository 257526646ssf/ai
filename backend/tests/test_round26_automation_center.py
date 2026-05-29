from __future__ import annotations

import base64
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import (
    ApiEndpoint,
    ApiTestCase,
    ApiTestLib,
    AutoCaseFile,
    AutoExecution,
    RequirementDocument,
    RequirementItem,
    RequirementLib,
    TestCase as DbTestCase,
)
from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

FAKE_SECRET = "round26-fake-secret-value"
AUTH_SECRET = f"Bearer {FAKE_SECRET}"
API_KEY_SECRET = f"round26-api-key-{FAKE_SECRET}"
COOKIE_SECRET = f"round26-cookie-{FAKE_SECRET}"
SECRET_MARKERS = (FAKE_SECRET, AUTH_SECRET, API_KEY_SECRET, COOKIE_SECRET)


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_fake_secrets(payload: Any) -> None:
    dumped = payload_text(payload)
    for secret in SECRET_MARKERS:
        assert secret not in dumped, dumped


def list_items(value: Any, *, keys: tuple[str, ...] = ("list", "items", "records", "results", "data")) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if isinstance(nested, list):
                assert all(isinstance(item, dict) for item in nested), nested
                return nested
        if "id" in value:
            return [value]
    if isinstance(value, list):
        assert all(isinstance(item, dict) for item in value), value
        return value
    pytest.fail(f"Expected list-like payload, got: {value!r}", pytrace=False)


def candidate_items(value: Any) -> list[dict[str, Any]]:
    return list_items(value, keys=("candidates", "items", "records", "results", "data", "list"))


def case_file_items(value: Any) -> list[dict[str, Any]]:
    return list_items(value, keys=("files", "case_files", "cases", "items", "records", "results", "data", "list"))


def artifact_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("evidence"), list):
        assert all(isinstance(item, dict) for item in value["evidence"]), value
        return value["evidence"]
    return list_items(value, keys=("evidence", "artifacts", "items", "records", "results", "data", "list"))


def create_auto_project(client, *, marker: str, framework: str = "pytest", language: str = "python") -> dict[str, Any]:
    project_id = create_project(client)
    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {
            "name": f"round26-auto-{marker}",
            "type": "web",
            "language": language,
            "framework": framework,
            "config": {
                "base_url": "https://round26.example.test",
                "token": FAKE_SECRET,
                "headers": {"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET},
            },
        },
    )
    return {"project_id": project_id, "auto_project_id": object_id(auto_project, "id", "auto_project_id")}


def seed_source_cases(project_id: int | str, *, marker: str) -> dict[str, Any]:
    with session_scope() as session:
        lib = RequirementLib(project_id=int(project_id), name=f"Round26 requirement lib {marker}")
        session.add(lib)
        session.flush()
        document = RequirementDocument(
            project_id=int(project_id),
            lib_id=lib.id,
            document_number=f"R26-DOC-{project_id}-{marker}",
            name=f"Round26 requirement document {marker}",
            source_type="text",
            raw_content="Automation center should screen, select, generate and execute stable automation cases.",
            parser_status="parsed",
        )
        session.add(document)
        session.flush()
        item = RequirementItem(
            project_id=int(project_id),
            lib_id=lib.id,
            document_id=document.id,
            item_number=f"R26-REQ-{project_id}-{marker}",
            title=f"Round26 automation requirement {marker}",
            summary="Candidate screening and automation generation workflow.",
            module="automation-center",
            priority="P1",
            status="confirmed",
            confidence=0.95,
        )
        session.add(item)
        session.flush()

        selected_case = DbTestCase(
            project_id=int(project_id),
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=item.id,
            case_number=f"R26-TC-{project_id}-{marker}-selected",
            title="Selected web smoke case",
            case_type="functional",
            steps=[{"action": "open", "target": "/login"}, {"action": "expect_visible", "target": "Login"}],
            expected_result="Login screen is visible.",
            priority="P1",
            status="confirmed",
            tags=["automation", "web"],
        )
        excluded_case = DbTestCase(
            project_id=int(project_id),
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=item.id,
            case_number=f"R26-TC-{project_id}-{marker}-excluded",
            title="Excluded exploratory-only case",
            case_type="exploratory",
            steps=[{"action": "explore", "target": "visual polish"}],
            expected_result="Reviewer records subjective findings.",
            priority="P3",
            status="draft",
            tags=["manual-only"],
        )
        session.add_all([selected_case, excluded_case])

        api_lib = ApiTestLib(project_id=int(project_id), name=f"Round26 API lib {marker}")
        session.add(api_lib)
        session.flush()
        endpoint = ApiEndpoint(
            lib_id=api_lib.id,
            requirement_item_id=item.id,
            name=f"Round26 candidate endpoint {marker}",
            method="POST",
            path=f"/round26/{marker}/candidates",
            headers_schema={"Authorization": AUTH_SECRET},
            response_schema={"status": 200},
        )
        session.add(endpoint)
        session.flush()
        api_case = ApiTestCase(
            endpoint_id=endpoint.id,
            lib_id=api_lib.id,
            requirement_item_id=item.id,
            name=f"Selected API contract case {marker}",
            category="contract",
            request_headers={"Authorization": AUTH_SECRET},
            request_query={"api_key": API_KEY_SECRET},
            request_body={"cookie": COOKIE_SECRET, "marker": marker},
            expected_status=200,
            assertions=[{"type": "status_code", "expected": 200}],
            status="confirmed",
        )
        session.add(api_case)
        session.flush()

        return {
            "lib_id": lib.id,
            "document_id": document.id,
            "requirement_item_id": item.id,
            "selected_case_id": selected_case.id,
            "excluded_case_id": excluded_case.id,
            "api_lib_id": api_lib.id,
            "api_endpoint_id": endpoint.id,
            "api_case_id": api_case.id,
        }


def seed_auto_case_file(
    *,
    auto_project_id: int | str,
    file_path: str,
    content: str,
    source_case_id: int | str | None = None,
    source_api_case_id: int | str | None = None,
) -> int:
    with session_scope() as session:
        case_file = AutoCaseFile(
            auto_project_id=int(auto_project_id),
            source_case_id=int(source_case_id) if source_case_id is not None else None,
            source_api_case_id=int(source_api_case_id) if source_api_case_id is not None else None,
            file_name=Path(file_path).name,
            file_path=file_path,
            content=content,
            case_count=1,
            automation_dsl={"steps": [{"action": "contract"}]},
        )
        session.add(case_file)
        session.flush()
        return case_file.id


def get_case_file_snapshot(case_file_id: int | str) -> dict[str, Any]:
    with session_scope() as session:
        case_file = session.get(AutoCaseFile, int(case_file_id))
        assert case_file is not None
        return {
            "id": case_file.id,
            "file_path": case_file.file_path,
            "content": case_file.content,
            "last_result": case_file.last_result,
        }


def extract_file_map(payload: Any) -> dict[str, str]:
    if isinstance(payload, dict):
        raw_files = payload.get("files") or payload.get("framework_files")
        if isinstance(raw_files, dict):
            return {str(path): str(content) for path, content in raw_files.items()}
        if isinstance(raw_files, list):
            mapped: dict[str, str] = {}
            for item in raw_files:
                if isinstance(item, dict):
                    path = item.get("path") or item.get("file_path") or item.get("name")
                    if path:
                        mapped[str(path)] = str(item.get("content") or "")
            if mapped:
                return mapped
        auto_project = payload.get("auto_project")
        if isinstance(auto_project, dict):
            return extract_file_map(auto_project)
    return {}


def decode_zip_payload(payload: dict[str, Any]) -> zipfile.ZipFile:
    raw_zip = base64.b64decode(payload["content_base64"])
    return zipfile.ZipFile(io.BytesIO(raw_zip))


def assert_zip_names_safe(names: set[str]) -> None:
    assert names, "zip archive must contain files"
    for name in names:
        normalized = name.replace("\\", "/")
        assert not normalized.startswith("/"), names
        assert ":" not in normalized.split("/", 1)[0], names
        assert ".." not in normalized.split("/"), names


def install_subprocess_mock(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_run(cmd: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd_list = [str(item) for item in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        cwd = Path(kwargs["cwd"])
        calls.append({"cmd": cmd_list, "cwd": str(cwd), "kwargs": kwargs})
        (cwd / "screenshots").mkdir(exist_ok=True)
        (cwd / "screenshots" / "selected.png").write_bytes(base64.b64decode(SMALL_PNG_BASE64))
        (cwd / "traces").mkdir(exist_ok=True)
        (cwd / "traces" / "trace.zip").write_bytes(b"PK\x03\x04round26-trace")
        return subprocess.CompletedProcess(cmd_list, 0, stdout=f"1 passed\ntoken={FAKE_SECRET}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


SMALL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def seed_execution_with_artifacts(auto_project_id: int | str, artifact_root: Path) -> int:
    run_dir = artifact_root / "run-26"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    (run_dir / "traces").mkdir(parents=True, exist_ok=True)
    runner_log = run_dir / "runner.log"
    screenshot = run_dir / "screenshots" / "home.png"
    trace_zip = run_dir / "traces" / "trace.zip"
    runner_log.write_text(f"started\nAuthorization: {AUTH_SECRET}\ntoken={FAKE_SECRET}\n", encoding="utf-8")
    screenshot.write_bytes(base64.b64decode(SMALL_PNG_BASE64))
    with zipfile.ZipFile(trace_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("trace.trace", "round26 trace content")

    evidence = [
        {"kind": "log", "type": "log", "path": str(runner_log), "relative_path": "runner.log", "size_bytes": runner_log.stat().st_size},
        {"kind": "screenshot", "type": "screenshot", "path": str(screenshot), "relative_path": "screenshots/home.png", "size_bytes": screenshot.stat().st_size},
        {"kind": "trace", "type": "trace", "path": str(trace_zip), "relative_path": "traces/trace.zip", "size_bytes": trace_zip.stat().st_size},
        {"kind": "log", "type": "log", "path": str(runner_log), "relative_path": "../escape.log", "size_bytes": runner_log.stat().st_size},
    ]
    with session_scope() as session:
        execution = AutoExecution(
            auto_project_id=int(auto_project_id),
            status="completed",
            summary={"total": 1, "passed": 1, "failed": 0, "errors": 0},
            artifacts={
                "artifact_dir": str(run_dir),
                "runner_log": str(runner_log),
                "evidence": evidence,
                "return_code": 0,
                "runner": {"mode": "pytest"},
            },
            log_excerpt=f"token={FAKE_SECRET}",
            duration_ms=42,
        )
        session.add(execution)
        session.flush()
        return execution.id


def test_candidate_screening_lists_filterable_recommendations_and_redacts_secrets(client):
    context = create_auto_project(client, marker="candidates")
    sources = seed_source_cases(context["project_id"], marker=f"candidates-{context['auto_project_id']}")

    screened = data_of(
        client.post(
            f"{API_PREFIX}/auto-candidates/screen",
            json={
                "project_id": context["project_id"],
                "auto_project_id": context["auto_project_id"],
                "source_case_ids": [sources["selected_case_id"], sources["excluded_case_id"]],
                "source_api_case_ids": [sources["api_case_id"]],
                "criteria": {"recommendation": "recommended", "token": FAKE_SECRET},
            },
        )
    )
    candidates = candidate_items(screened)

    assert candidates, "screening must return non-empty automation candidates"
    assert any(item.get("source_case_id") is not None for item in candidates), candidates
    assert any(item.get("source_api_case_id") is not None for item in candidates), candidates
    for item in candidates:
        assert item.get("source_case_id") is not None or item.get("source_api_case_id") is not None, item
        assert item.get("automation_recommendation"), item
        assert item.get("automation_type"), item
        assert item.get("reason"), item
        assert item.get("priority") is not None or item.get("score") is not None, item
    assert_no_fake_secrets(screened)

    target_recommendation = str(candidates[0]["automation_recommendation"])
    listed = data_of(
        client.get(
            f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/candidates",
            params={"recommendation": target_recommendation},
        )
    )
    filtered = candidate_items(listed)

    assert filtered, "candidate list must support recommendation filtering"
    assert all(str(item.get("automation_recommendation")) == target_recommendation for item in filtered), filtered
    assert_no_fake_secrets(listed)


def test_candidate_selection_limits_generate_cases_to_selected_sources(client):
    context = create_auto_project(client, marker="selection")
    sources = seed_source_cases(context["project_id"], marker=f"selection-{context['auto_project_id']}")

    data_of(
        client.post(
            f"{API_PREFIX}/auto-candidates/screen",
            json={
                "project_id": context["project_id"],
                "auto_project_id": context["auto_project_id"],
                "source_case_ids": [sources["selected_case_id"], sources["excluded_case_id"]],
                "source_api_case_ids": [sources["api_case_id"]],
            },
        )
    )
    selection_response = client.post(
        f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/candidates/selection",
        json={
            "selected_source_case_ids": [sources["selected_case_id"]],
            "selected_source_api_case_ids": [sources["api_case_id"]],
            "excluded_source_case_ids": [sources["excluded_case_id"]],
            "selections": [
                {"candidate_id": f"case:{sources['selected_case_id']}", "source_case_id": sources["selected_case_id"], "selected": True},
                {"candidate_id": f"api:{sources['api_case_id']}", "source_api_case_id": sources["api_case_id"], "selected": True},
                {"candidate_id": f"case:{sources['excluded_case_id']}", "source_case_id": sources["excluded_case_id"], "selected": False},
            ],
            "token": FAKE_SECRET,
        },
    )
    assert selection_response.status_code in {200, 201}, selection_response.text
    assert_no_fake_secrets(data_of(selection_response))

    generated = data_of(client.post(f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/generate-cases", json={"use_selection": True}))
    files = case_file_items(generated)
    generated_case_ids = {int(item["source_case_id"]) for item in files if item.get("source_case_id") is not None}
    generated_api_case_ids = {int(item["source_api_case_id"]) for item in files if item.get("source_api_case_id") is not None}

    assert int(sources["selected_case_id"]) in generated_case_ids, files
    assert int(sources["api_case_id"]) in generated_api_case_ids, files
    assert int(sources["excluded_case_id"]) not in generated_case_ids, files
    assert len(files) == 2, files
    assert_no_fake_secrets(generated)


def test_playwright_framework_generation_persists_trace_screenshot_video_reporter_templates(client):
    context = create_auto_project(client, marker="playwright", framework="playwright", language="typescript")

    generated = data_of(client.post(f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/generate-framework"))
    file_map = extract_file_map(generated)
    lower_paths = {path.lower() for path in file_map}

    assert any(path.endswith("readme.md") for path in lower_paths), file_map
    assert any(path.endswith("package.json") or path.endswith("requirements.txt") for path in lower_paths), file_map
    assert any("playwright.config" in path for path in lower_paths), file_map
    assert any(path.startswith("tests/") and (".spec." in path or ".test." in path) for path in lower_paths), file_map
    assert any(path.startswith("pages/") or path.startswith("fixtures/") or "/pages/" in path or "/fixtures/" in path for path in lower_paths), file_map

    combined = "\n".join(file_map.values()).lower()
    for keyword in ("trace", "screenshot", "video", "reporter"):
        assert keyword in combined, file_map
    assert_no_fake_secrets(generated)

    download = data_of(client.get(f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/download"))
    with decode_zip_payload(download) as archive:
        names = set(archive.namelist())
    assert any(name.lower().endswith("readme.md") for name in names), names
    assert any("playwright.config" in name.lower() for name in names), names
    assert_zip_names_safe(names)
    assert_no_fake_secrets(download)


def test_online_case_file_view_patch_download_and_path_validation(client):
    context = create_auto_project(client, marker="files")
    original_content = "def test_round26_original():\n    assert True\n"
    case_file_id = seed_auto_case_file(
        auto_project_id=context["auto_project_id"],
        file_path="tests/test_round26_original.py",
        content=original_content,
    )

    files_payload = data_of(client.get(f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/files"))
    listed_files = case_file_items(files_payload)
    assert any(str(object_id(item, "id", "case_file_id")) == str(case_file_id) for item in listed_files), listed_files

    detail = data_of(client.get(f"{API_PREFIX}/auto-case-files/{case_file_id}"))
    assert detail["file_path"] == "tests/test_round26_original.py", detail
    assert detail["content"] == original_content, detail

    updated_content = "def test_round26_saved_from_editor():\n    assert 'editor' == 'editor'\n"
    updated_path = "tests/round26/test_saved_from_editor.py"
    patched = data_of(
        client.patch(
            f"{API_PREFIX}/auto-case-files/{case_file_id}",
            json={"file_path": updated_path, "content": updated_content},
        )
    )
    assert patched["file_path"] == updated_path, patched
    assert patched["content"] == updated_content, patched

    reread = data_of(client.get(f"{API_PREFIX}/auto-case-files/{case_file_id}"))
    assert reread["file_path"] == updated_path, reread
    assert reread["content"] == updated_content, reread

    download = data_of(client.get(f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/download"))
    with decode_zip_payload(download) as archive:
        names = set(archive.namelist())
        assert updated_path in names, names
        assert archive.read(updated_path).decode("utf-8") == updated_content
        assert_zip_names_safe(names)

    for illegal_path in ("../x.py", str(Path.cwd() / "x.py"), "tests/../../x.py"):
        response = client.patch(
            f"{API_PREFIX}/auto-case-files/{case_file_id}",
            json={"file_path": illegal_path, "content": "def test_overwrite():\n    assert False\n"},
        )
        assert response.status_code == 400, response.text
        snapshot = get_case_file_snapshot(case_file_id)
        assert snapshot["file_path"] == updated_path, snapshot
        assert snapshot["content"] == updated_content, snapshot
    assert_no_fake_secrets(download)


def test_execute_selected_case_files_returns_detail_and_updates_last_result(monkeypatch, tmp_path, client):
    calls = install_subprocess_mock(monkeypatch)
    context = create_auto_project(client, marker="execute")
    selected_file_id = seed_auto_case_file(
        auto_project_id=context["auto_project_id"],
        file_path="tests/test_round26_selected.py",
        content="def test_selected():\n    assert True\n",
    )
    excluded_file_id = seed_auto_case_file(
        auto_project_id=context["auto_project_id"],
        file_path="tests/test_round26_excluded.py",
        content="def test_excluded():\n    assert False\n",
    )

    execution = data_of(
        client.post(
            f"{API_PREFIX}/auto-projects/{context['auto_project_id']}/execute",
            json={"case_file_ids": [selected_file_id], "artifact_root": str(tmp_path / "auto-artifacts"), "env": {"ROUND26_TOKEN": FAKE_SECRET}},
        )
    )
    execution_id = object_id(execution, "id", "execution_id")

    assert calls, "execute must invoke the automation runner through subprocess.run"
    assert execution["status"] == "completed", execution
    assert isinstance(execution.get("summary"), dict), execution
    assert execution.get("log_excerpt") or execution.get("log"), execution
    assert isinstance(execution.get("artifacts"), dict), execution
    executed_files = execution["artifacts"].get("files") or []
    executed_paths = {str(item.get("path")) for item in executed_files if item.get("source") == "case_file"}
    assert executed_paths == {"tests/test_round26_selected.py"}, execution
    assert "test_round26_excluded.py" not in payload_text(execution), execution
    assert_no_fake_secrets(execution)

    selected_snapshot = get_case_file_snapshot(selected_file_id)
    excluded_snapshot = get_case_file_snapshot(excluded_file_id)
    assert selected_snapshot["last_result"], selected_snapshot
    assert str(selected_snapshot["last_result"].get("execution_id")) == str(execution_id), selected_snapshot
    assert excluded_snapshot["last_result"] in (None, {}), excluded_snapshot

    detail = data_of(client.get(f"{API_PREFIX}/auto-executions/{execution_id}"))
    assert str(object_id(detail, "id", "execution_id")) == str(execution_id), detail
    assert detail.get("summary") == execution.get("summary"), detail
    assert detail.get("artifacts"), detail
    assert detail.get("log_excerpt") or detail.get("log"), detail
    assert_no_fake_secrets(detail)


def test_execution_artifacts_list_and_preview_are_safe(tmp_path, client):
    context = create_auto_project(client, marker="artifacts")
    execution_id = seed_execution_with_artifacts(context["auto_project_id"], tmp_path / "round26-artifacts")

    listed = data_of(client.get(f"{API_PREFIX}/auto-executions/{execution_id}/artifacts"))
    evidence = artifact_items(listed)
    kinds = {str(item.get("kind") or item.get("type")) for item in evidence}
    assert {"log", "screenshot", "trace"} <= kinds, evidence
    assert_no_fake_secrets(listed)

    log_preview = data_of(client.get(f"{API_PREFIX}/auto-executions/{execution_id}/artifacts/preview", params={"relativePath": "runner.log"}))
    assert log_preview.get("previewable") is True, log_preview
    assert str(log_preview.get("mime_type") or log_preview.get("mime") or "").startswith("text/"), log_preview
    assert "started" in str(log_preview.get("content") or log_preview.get("text") or ""), log_preview
    assert_no_fake_secrets(log_preview)

    image_preview = data_of(
        client.get(
            f"{API_PREFIX}/auto-executions/{execution_id}/artifacts/preview",
            params={"relativePath": "screenshots/home.png"},
        )
    )
    assert str(image_preview.get("mime_type") or image_preview.get("mime") or "").startswith("image/"), image_preview
    assert base64.b64decode(image_preview["content_base64"]), image_preview
    assert_no_fake_secrets(image_preview)

    trace_preview = data_of(
        client.get(
            f"{API_PREFIX}/auto-executions/{execution_id}/artifacts/preview",
            params={"relativePath": "traces/trace.zip"},
        )
    )
    assert trace_preview.get("previewable") is False, trace_preview
    assert trace_preview.get("download_url") or trace_preview.get("download_path") or trace_preview.get("relative_path"), trace_preview
    assert_no_fake_secrets(trace_preview)

    for escape_path in ("../runner.log", "/runner.log", "screenshots/../../runner.log"):
        response = client.get(
            f"{API_PREFIX}/auto-executions/{execution_id}/artifacts/preview",
            params={"relativePath": escape_path},
        )
        assert response.status_code in {400, 404}, response.text


def test_artifacts_download_zip_regression_is_decodable_manifested_and_redacted(tmp_path, client):
    context = create_auto_project(client, marker="artifact-download")
    execution_id = seed_execution_with_artifacts(context["auto_project_id"], tmp_path / "round26-artifact-download")

    download = data_of(client.get(f"{API_PREFIX}/auto-executions/{execution_id}/artifacts/download"))
    with decode_zip_payload(download) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names, names
        assert any(name.startswith("artifacts/") for name in names), names
        assert_zip_names_safe(names)
        raw_contents = b"\n".join(archive.read(name) for name in names)
    assert FAKE_SECRET.encode("utf-8") not in raw_contents
    assert_no_fake_secrets(download)
