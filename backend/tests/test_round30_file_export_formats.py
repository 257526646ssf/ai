from __future__ import annotations

import base64
import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import (
    ApiTestLib,
    AutoExecution,
    AutoProject,
    Defect,
    Execution,
    PerfPlan,
    PerfResult,
    Project,
    Report,
    RequirementDocument,
    RequirementItem,
    RequirementLib,
    TestCase as CaseModel,
)
from conftest import API_PREFIX, data_of, object_id


pytestmark = pytest.mark.contract

FAKE_SECRET = "round30-fake-secret-value"
AUTH_SECRET = f"Bearer {FAKE_SECRET}"
API_KEY_SECRET = f"round30-api-key-{FAKE_SECRET}"
COOKIE_SECRET = f"round30-cookie-{FAKE_SECRET}"
SECRET_MARKERS = (FAKE_SECRET, AUTH_SECRET, API_KEY_SECRET, COOKIE_SECRET)
FORMULA_VALUES = ("=cmd", "+SUM", "-1+2", "@foo")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FAKE_FILE_FIELDS = {"filename", "content", "content_base64", "mime_type"}
UNSUPPORTED_FILE_TYPES = ("pdf", "word", "docx", "xmind")


def payload_text(payload: Any) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def response_payload(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        pytest.fail(f"Expected JSON response, got: {response.text!r}", pytrace=False)
    assert isinstance(payload, dict), payload
    return payload


def assert_no_fake_secrets(payload: Any) -> None:
    dumped = payload_text(payload)
    for secret in SECRET_MARKERS:
        assert secret not in dumped, dumped


def assert_no_fake_file_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        forbidden = FAKE_FILE_FIELDS & set(payload)
        assert not forbidden, {"forbidden_file_fields": sorted(forbidden), "payload": payload}
        for value in payload.values():
            assert_no_fake_file_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_fake_file_fields(item)


def assert_no_fake_collection_fields(payload: Any) -> None:
    forbidden_keys = {"blocks", "items", "apis"}
    if isinstance(payload, dict):
        forbidden = forbidden_keys & set(payload)
        assert not forbidden, {"forbidden_collection_fields": sorted(forbidden), "payload": payload}
        for value in payload.values():
            assert_no_fake_collection_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_fake_collection_fields(item)


def assert_structured_unsupported(response, *, expected_statuses: set[int] | None = None) -> dict[str, Any]:
    statuses = expected_statuses or {400, 415, 422}
    assert response.status_code in statuses, response.text
    payload = response_payload(response)
    assert {"code", "message", "data"} <= payload.keys(), payload
    assert payload["code"] not in {0, 200, 201}, payload
    assert isinstance(payload["message"], str) and payload["message"], payload
    assert isinstance(payload["data"], dict), payload
    dumped = payload_text(payload).lower()
    assert "unsupported" in dumped or "not supported" in dumped, payload
    assert_no_fake_file_fields(payload)
    assert_no_fake_secrets(payload)
    return payload


def api_request(client, method: str, path: str, **kwargs: Any):
    try:
        return getattr(client, method)(path, **kwargs)
    except Exception as exc:
        pytest.fail(
            f"{method.upper()} {path} must return a structured API response instead of raising "
            f"{exc.__class__.__name__}: {exc}",
            pytrace=False,
        )


def list_items(
    value: Any,
    *,
    keys: tuple[str, ...] = ("list", "items", "records", "results", "data", "apis", "test_cases"),
) -> list[dict[str, Any]]:
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


def seed_export_context(marker: str | None = None) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = _create_project(session, marker, "export")
        lib, document, item = _create_requirement_chain(session, project, marker, "export")
        selected_case = _create_case(
            session,
            project=project,
            lib=lib,
            document=document,
            item=item,
            marker=marker,
            suffix="selected",
            title=f"Round30 selected XLSX case {marker}",
            expected_result=f"Selected export data should redact api_key={API_KEY_SECRET}",
        )
        unselected_case = _create_case(
            session,
            project=project,
            lib=lib,
            document=document,
            item=item,
            marker=marker,
            suffix="unselected",
            title=f"Round30 unselected case {marker}",
        )
        execution = Execution(
            project_id=project.id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=item.id,
            case_id=selected_case.id,
            executor_type="manual",
            status="failed",
            actual_result=f"Round30 execution actual Authorization: {AUTH_SECRET}",
            response_snapshot={"headers": {"Set-Cookie": COOKIE_SECRET}},
            artifact_summary_json={"api_key": API_KEY_SECRET},
        )
        session.add(execution)
        session.flush()
        selected_defect = Defect(
            defect_number=f"BUG-R30-{marker}-selected",
            project_id=project.id,
            execution_id=execution.id,
            case_id=selected_case.id,
            requirement_item_id=item.id,
            title=f"Round30 selected XLSX defect {marker}",
            actual_result=f"Defect actual result cookie={COOKIE_SECRET}",
            severity="critical",
            status="open",
            remark=f"Authorization: {AUTH_SECRET}",
        )
        unselected_defect = Defect(
            defect_number=f"BUG-R30-{marker}-closed",
            project_id=project.id,
            execution_id=execution.id,
            case_id=unselected_case.id,
            requirement_item_id=item.id,
            title=f"Round30 closed defect {marker}",
            actual_result="Closed defect must not appear in open export.",
            severity="normal",
            status="closed",
            remark="closed",
        )
        session.add_all([selected_defect, unselected_defect])

        foreign_project = _create_project(session, marker, "foreign")
        foreign_lib, foreign_document, foreign_item = _create_requirement_chain(session, foreign_project, marker, "foreign")
        foreign_case = _create_case(
            session,
            project=foreign_project,
            lib=foreign_lib,
            document=foreign_document,
            item=foreign_item,
            marker=marker,
            suffix="foreign",
            title=f"Round30 foreign case {marker}",
        )
        foreign_defect = Defect(
            defect_number=f"BUG-R30-{marker}-foreign",
            project_id=foreign_project.id,
            case_id=foreign_case.id,
            requirement_item_id=foreign_item.id,
            title=f"Round30 foreign defect {marker}",
            actual_result="Foreign project defect must not appear.",
            severity="major",
            status="open",
            remark="foreign",
        )
        session.add(foreign_defect)
        session.flush()
        return {
            "marker": marker,
            "project_id": project.id,
            "case_id": selected_case.id,
            "case_title": selected_case.title,
            "unselected_case_title": unselected_case.title,
            "foreign_case_title": foreign_case.title,
            "defect_id": selected_defect.id,
            "defect_title": selected_defect.title,
            "closed_defect_title": unselected_defect.title,
            "foreign_defect_title": foreign_defect.title,
        }


def seed_formula_context(marker: str | None = None) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = _create_project(session, marker, "formula")
        lib, document, item = _create_requirement_chain(session, project, marker, "formula")
        case_ids: list[int] = []
        defect_ids: list[int] = []
        for index, formula in enumerate(FORMULA_VALUES, start=1):
            case = _create_case(
                session,
                project=project,
                lib=lib,
                document=document,
                item=item,
                marker=marker,
                suffix=f"formula-{index}",
                title=formula,
                precondition=f"Authorization: {AUTH_SECRET}",
                expected_result=f"api_key={API_KEY_SECRET}",
            )
            session.flush()
            case_ids.append(case.id)
            defect = Defect(
                defect_number=f"BUG-R30-{marker}-formula-{index}",
                project_id=project.id,
                case_id=case.id,
                requirement_item_id=item.id,
                title=formula,
                actual_result=f"token={FAKE_SECRET}",
                severity="normal",
                status="open",
                remark=f"cookie={COOKIE_SECRET}",
            )
            session.add(defect)
            session.flush()
            defect_ids.append(defect.id)
        return {"project_id": project.id, "case_ids": case_ids, "defect_ids": defect_ids, "marker": marker}


def seed_report(marker: str | None = None) -> int:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = _create_project(session, marker, "report")
        report = Report(
            project_id=project.id,
            name=f"round30-report-{marker}",
            type="comprehensive",
            status="generated",
            related_module="project",
            related_scope_json={"project_id": project.id},
            requirement_item_ids_json=[],
            source_document_ids_json=[],
            scope_snapshot={"project_id": project.id},
            data_snapshot={"marker": marker},
            source_refs_json={},
            content=f"# Round30 report {marker}\n",
            template_version="r30",
            ai_summary_version="rules",
            generated_at=datetime.now(timezone.utc),
        )
        session.add(report)
        session.flush()
        return report.id


def seed_import_context(marker: str | None = None) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = _create_project(session, marker, "import")
        lib, _, _ = _create_requirement_chain(session, project, marker, "import")
        api_lib = ApiTestLib(
            project_id=project.id,
            name=f"Round30 API import lib {marker}",
            description="Round30 import regression library.",
            import_source="round30",
        )
        session.add(api_lib)
        session.flush()
        return {"project_id": project.id, "lib_id": lib.id, "api_lib_id": api_lib.id, "marker": marker}


def seed_auto_artifact_execution(tmp_path: Path, marker: str | None = None) -> int:
    marker = marker or uuid4().hex[:10]
    artifact_dir = tmp_path / f"round30-auto-{marker}" / "run"
    artifact_dir.mkdir(parents=True)
    safe_log = artifact_dir / "runner.log"
    escaped_source = artifact_dir / "escape-source.log"
    outside_log = tmp_path / f"round30-outside-{marker}.log"
    safe_log.write_text(f"started\nAuthorization: {AUTH_SECRET}\ntoken={FAKE_SECRET}\n", encoding="utf-8")
    escaped_source.write_text("this relative path should be skipped\n", encoding="utf-8")
    outside_log.write_text(f"outside api_key={API_KEY_SECRET}\n", encoding="utf-8")

    with session_scope() as session:
        project = _create_project(session, marker, "auto-artifacts")
        auto_project = AutoProject(
            project_id=project.id,
            name=f"Round30 automation artifacts {marker}",
            type="web",
            language="python",
            framework="pytest",
            extra_config={},
        )
        session.add(auto_project)
        session.flush()
        execution = AutoExecution(
            auto_project_id=auto_project.id,
            status="completed",
            summary={"total": 1, "passed": 1, "failed": 0},
            artifacts={
                "artifact_dir": str(artifact_dir),
                "evidence": [
                    {"kind": "log", "path": str(safe_log), "relative_path": "runner.log"},
                    {"kind": "log", "path": str(escaped_source), "relative_path": "../escape.log"},
                    {"kind": "log", "path": str(outside_log), "relative_path": "outside.log"},
                ],
                "runner_log": str(safe_log),
            },
            log_excerpt=f"token={FAKE_SECRET}",
            duration_ms=30,
        )
        session.add(execution)
        session.flush()
        return execution.id


def seed_perf_artifact_result(tmp_path: Path, marker: str | None = None) -> int:
    marker = marker or uuid4().hex[:10]
    artifact_dir = tmp_path / f"round30-perf-{marker}" / "run"
    artifact_dir.mkdir(parents=True)
    safe_log = artifact_dir / "runner.log"
    escaped_source = artifact_dir / "escape-source.log"
    outside_log = tmp_path / f"round30-perf-outside-{marker}.log"
    safe_log.write_text(f"p95=120\nCookie: {COOKIE_SECRET}\nsecret={FAKE_SECRET}\n", encoding="utf-8")
    escaped_source.write_text("this relative path should be skipped\n", encoding="utf-8")
    outside_log.write_text(f"outside Authorization: {AUTH_SECRET}\n", encoding="utf-8")

    with session_scope() as session:
        project = _create_project(session, marker, "perf-artifacts")
        plan = PerfPlan(
            project_id=project.id,
            name=f"Round30 perf plan {marker}",
            target_doc="p95 <= 300ms",
            plan_schema={"thresholds": {"p95_ms": 300}},
            status="scripted",
        )
        session.add(plan)
        session.flush()
        result = PerfResult(
            plan_id=plan.id,
            project_id=project.id,
            status="completed",
            summary_data={"total": 1, "passed": 1, "failed": 0, "p95_ms": 120},
            timeline_data=[{"second": 1, "p95_ms": 120}],
            error_details=[],
            artifacts={
                "artifact_dir": str(artifact_dir),
                "evidence": [
                    {"kind": "log", "path": str(safe_log), "relative_path": "runner.log"},
                    {"kind": "log", "path": str(escaped_source), "relative_path": "../escape.log"},
                    {"kind": "log", "path": str(outside_log), "relative_path": "outside.log"},
                ],
            },
            duration=5,
        )
        session.add(result)
        session.flush()
        return result.id


def _create_project(session: Any, marker: str, suffix: str) -> Project:
    project = Project(
        code=f"r30-{marker}-{suffix}",
        name=f"Round30 {suffix} project {marker}",
        description=f"Round30 project description secret={FAKE_SECRET}",
        owner_name="round30_qa",
    )
    session.add(project)
    session.flush()
    return project


def _create_requirement_chain(session: Any, project: Project, marker: str, suffix: str) -> tuple[RequirementLib, RequirementDocument, RequirementItem]:
    lib = RequirementLib(
        project_id=project.id,
        name=f"Round30 requirement lib {suffix} {marker}",
        description=f"Authorization: {AUTH_SECRET}",
    )
    session.add(lib)
    session.flush()
    document = RequirementDocument(
        project_id=project.id,
        lib_id=lib.id,
        document_number=f"DOC-R30-{marker}-{suffix}",
        name=f"Round30 requirement document {suffix} {marker}",
        source_type="markdown",
        source_file_name=f"round30-{marker}-{suffix}.md",
        raw_content=f"# Round30\n\nDo not leak token={FAKE_SECRET}.",
        parser_status="parsed",
        parser_metadata={"source": "round30", "cookie": COOKIE_SECRET},
    )
    session.add(document)
    session.flush()
    item = RequirementItem(
        project_id=project.id,
        lib_id=lib.id,
        document_id=document.id,
        item_number=f"REQ-R30-{marker}-{suffix}",
        title=f"Round30 requirement item {suffix} {marker}",
        summary=f"Requirement summary api_key={API_KEY_SECRET}",
        module="round30",
        priority="P0",
        status="confirmed",
        confidence=0.9,
        case_status="generated",
    )
    session.add(item)
    session.flush()
    return lib, document, item


def _create_case(
    session: Any,
    *,
    project: Project,
    lib: RequirementLib,
    document: RequirementDocument,
    item: RequirementItem,
    marker: str,
    suffix: str,
    title: str,
    precondition: str | None = None,
    expected_result: str | None = None,
) -> CaseModel:
    case = CaseModel(
        project_id=project.id,
        lib_id=lib.id,
        document_id=document.id,
        requirement_item_id=item.id,
        case_number=f"TC-R30-{marker}-{suffix}",
        title=title,
        case_type="functional",
        precondition=precondition or f"Round30 precondition token={FAKE_SECRET}",
        steps=[{"step": 1, "action": f"Execute Round30 path {suffix}"}],
        expected_result=expected_result or "Round30 expected result is visible.",
        priority="P0",
        tags=["round30", suffix],
        status="active",
    )
    session.add(case)
    session.flush()
    return case


def export_xlsx_bytes(response) -> tuple[dict[str, Any], bytes]:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        assert response.status_code == 200, response.text
        mime = content_type.split(";", 1)[0]
        assert mime == XLSX_MIME, response.headers
        return {"mime_type": mime}, response.content

    payload = response_payload(response)
    assert response.status_code in {200, 201}, response.text
    assert payload.get("code") in {0, 200}, payload
    data = payload["data"]
    assert isinstance(data, dict), payload
    assert data.get("format") == "xlsx", data
    mime = str(data.get("mime_type") or "").split(";", 1)[0]
    assert mime == XLSX_MIME, data
    if isinstance(data.get("content_base64"), str):
        return data, base64.b64decode(data["content_base64"])
    if isinstance(data.get("content"), str):
        content = data["content"]
        try:
            return data, base64.b64decode(content, validate=True)
        except Exception:
            return data, content.encode("latin-1")
    pytest.fail(f"XLSX export must provide raw bytes or content_base64: {data!r}", pytrace=False)


def assert_real_xlsx(raw_xlsx: bytes) -> tuple[set[str], list[str], dict[str, str]]:
    assert raw_xlsx.startswith(b"PK"), raw_xlsx[:8]
    with zipfile.ZipFile(io.BytesIO(raw_xlsx)) as archive:
        names = set(archive.namelist())
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"}
        assert required <= names, names
        xml_by_name: dict[str, str] = {}
        text_values: list[str] = []
        for name in names:
            if not name.endswith(".xml"):
                continue
            raw_xml = archive.read(name)
            xml_text = raw_xml.decode("utf-8", errors="replace")
            xml_by_name[name] = xml_text
            try:
                root = ElementTree.fromstring(raw_xml)
            except ElementTree.ParseError:
                continue
            for element in root.iter():
                if element.text and element.text.strip():
                    text_values.append(element.text.strip())
        return names, text_values, xml_by_name


def assert_xlsx_has_no_formula_nodes(xml_by_name: dict[str, str]) -> None:
    sheet_xml = "\n".join(xml for name, xml in xml_by_name.items() if name.startswith("xl/worksheets/"))
    assert re.search(r"<(?:\w+:)?f(?:\s|>)", sheet_xml) is None, sheet_xml


def assert_xlsx_contains_only_expected(combined_text: str, *, present: str, absent: tuple[str, ...]) -> None:
    assert present in combined_text, combined_text
    for value in absent:
        assert value not in combined_text, combined_text


def assert_csv_formula_values_are_neutralized(content: str) -> None:
    rows = list(csv.reader(io.StringIO(content)))
    cells = [cell for row in rows for cell in row]
    for formula in FORMULA_VALUES:
        assert formula not in cells, {"formula": formula, "cells": cells}
        assert any(is_neutralized_cell(cell, formula) for cell in cells), {"formula": formula, "cells": cells}


def assert_xlsx_formula_values_are_neutralized(values: list[str], xml_by_name: dict[str, str]) -> None:
    assert_xlsx_has_no_formula_nodes(xml_by_name)
    for formula in FORMULA_VALUES:
        assert formula not in values, {"formula": formula, "values": values}
        assert any(is_neutralized_cell(value, formula) for value in values), {"formula": formula, "values": values}


def is_neutralized_cell(value: str, formula: str) -> bool:
    return value != formula and any(value.startswith(prefix + formula) for prefix in ("'", "\t", " ", "\u200b", "\ufeff"))


def decode_zip_payload(payload: dict[str, Any]) -> tuple[bytes, dict[str, Any], set[str], dict[str, bytes]]:
    raw_zip = base64.b64decode(payload["content_base64"])
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names, names
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    assert isinstance(manifest, dict), manifest
    return raw_zip, manifest, names, files


def assert_zip_names_safe(names: set[str]) -> None:
    assert names, "zip archive must contain files"
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        assert not str(path).startswith("/"), names
        assert ":" not in path.parts[0], names
        assert ".." not in path.parts, names


def skipped_metadata_items(payload: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if "skipped" in str(key).lower():
                if isinstance(value, list):
                    found.extend(value)
                else:
                    found.append(value)
            found.extend(skipped_metadata_items(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(skipped_metadata_items(item))
    return found


def assert_artifact_zip_contract(download: dict[str, Any]) -> None:
    assert download["mime_type"] == "application/zip", download
    raw_zip, manifest, names, files = decode_zip_payload(download)
    assert_zip_names_safe(names)
    assert "artifacts/runner.log" in names, names
    assert "artifacts/escape.log" not in names, names
    assert "artifacts/outside.log" not in names, names
    log_text = files["artifacts/runner.log"].decode("utf-8", errors="replace")
    assert "started" in log_text or "p95=120" in log_text, log_text
    assert_no_fake_secrets(log_text)

    skipped = skipped_metadata_items(manifest)
    skipped_text = payload_text(skipped).lower()
    assert skipped and "escape" in skipped_text and "outside" in skipped_text, manifest
    assert_no_fake_secrets(manifest)
    assert_no_fake_secrets(raw_zip.decode("latin-1", errors="ignore"))


def api_case_expected_status(case: dict[str, Any]) -> int:
    value = case.get("expected_status")
    assert value is not None, case
    return int(value)


def test_test_case_xlsx_export_returns_real_workbook_filters_data_and_sets_mime(client):
    context = seed_export_context()

    response = client.get(
        f"{API_PREFIX}/test-cases/export",
        params={"projectId": context["project_id"], "caseIds": str(context["case_id"]), "format": "xlsx"},
    )
    exported, raw_xlsx = export_xlsx_bytes(response)
    _, text_values, xml_by_name = assert_real_xlsx(raw_xlsx)

    combined = "\n".join([*text_values, *xml_by_name.values()])
    assert exported.get("count") in {None, 1}, exported
    assert_xlsx_contains_only_expected(
        combined,
        present=context["case_title"],
        absent=(context["unselected_case_title"], context["foreign_case_title"]),
    )
    assert_no_fake_secrets(exported)
    assert_no_fake_secrets(combined)


def test_defect_xlsx_export_returns_real_workbook_filters_data_and_sets_mime(client):
    context = seed_export_context()

    response = client.get(
        f"{API_PREFIX}/defects/export",
        params={"projectId": context["project_id"], "status": "open", "format": "xlsx"},
    )
    exported, raw_xlsx = export_xlsx_bytes(response)
    _, text_values, xml_by_name = assert_real_xlsx(raw_xlsx)

    combined = "\n".join([*text_values, *xml_by_name.values()])
    assert exported.get("count") in {None, 1}, exported
    assert_xlsx_contains_only_expected(
        combined,
        present=context["defect_title"],
        absent=(context["closed_defect_title"], context["foreign_defect_title"]),
    )
    assert_no_fake_secrets(exported)
    assert_no_fake_secrets(combined)


@pytest.mark.parametrize("resource", ["test-cases", "defects"])
@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
def test_csv_and_xlsx_exports_neutralize_formula_injection_and_redact_secrets(client, resource: str, fmt: str):
    context = seed_formula_context()
    if resource == "test-cases":
        params = {"projectId": context["project_id"], "caseIds": ",".join(str(item) for item in context["case_ids"]), "format": fmt}
    else:
        params = {"projectId": context["project_id"], "status": "open", "format": fmt}

    response = client.get(f"{API_PREFIX}/{resource}/export", params=params)
    if fmt == "csv":
        exported = data_of(response)
        assert exported["format"] == "csv", exported
        assert str(exported.get("mime_type", "")).startswith("text/csv"), exported
        assert_csv_formula_values_are_neutralized(exported["content"])
        assert_no_fake_secrets(exported)
        return

    exported, raw_xlsx = export_xlsx_bytes(response)
    _, values, xml_by_name = assert_real_xlsx(raw_xlsx)
    assert_xlsx_formula_values_are_neutralized(values, xml_by_name)
    assert_no_fake_secrets(exported)
    assert_no_fake_secrets("\n".join([*values, *xml_by_name.values()]))


@pytest.mark.parametrize("fmt", UNSUPPORTED_FILE_TYPES)
@pytest.mark.parametrize("target", ["test-cases", "defects", "reports"])
def test_unsupported_export_formats_return_structured_errors_without_fake_file_fields(client, target: str, fmt: str):
    if target == "reports":
        response = api_request(client, "get", f"{API_PREFIX}/reports/{seed_report()}/download", params={"format": fmt})
    else:
        response = api_request(client, "get", f"{API_PREFIX}/{target}/export", params={"format": fmt})

    assert_structured_unsupported(response)


@pytest.mark.parametrize("file_type", ("docx", "pdf", "xlsx", "xmind"))
@pytest.mark.parametrize("target", ["requirement-documents", "api-documents", "api-import"])
def test_document_and_api_import_reject_unsupported_file_types_without_fake_collections(client, target: str, file_type: str):
    context = seed_import_context()
    payload = {
        "source_type": file_type,
        "file_type": file_type,
        "source_file_name": f"round30.{file_type}",
        "content": f"fake {file_type} binary source token={FAKE_SECRET}",
        "raw_content": f"fake {file_type} binary source token={FAKE_SECRET}",
        "generate_cases": True,
        "create_cases": True,
    }

    if target == "requirement-documents":
        response = api_request(
            client,
            "post",
            f"{API_PREFIX}/projects/{context['project_id']}/requirement-documents",
            json={"lib_id": context["lib_id"], "name": f"round30-{file_type}", **payload},
        )
    elif target == "api-documents":
        response = api_request(client, "post", f"{API_PREFIX}/api-test-libs/{context['api_lib_id']}/import-documents", json=payload)
    else:
        response = api_request(client, "post", f"{API_PREFIX}/api-test-libs/{context['api_lib_id']}/apis/import", json=payload)

    error_payload = assert_structured_unsupported(response)
    assert_no_fake_collection_fields(error_payload)


@pytest.mark.parametrize("artifact_kind", ["automation", "performance"])
def test_artifact_zip_skips_out_of_bounds_files_records_skipped_metadata_and_redacts_text(tmp_path, client, artifact_kind: str):
    if artifact_kind == "automation":
        execution_id = seed_auto_artifact_execution(tmp_path)
        response = client.get(f"{API_PREFIX}/auto-executions/{execution_id}/artifacts/download")
    else:
        result_id = seed_perf_artifact_result(tmp_path)
        response = client.get(f"{API_PREFIX}/perf-results/{result_id}/artifacts/download")

    download = data_of(response)
    assert_artifact_zip_contract(download)


@pytest.mark.parametrize(
    ("label", "payload", "expected_method", "expected_path", "expected_status"),
    [
        (
            "openapi",
            {
                "source_type": "openapi",
                "content": {
                    "openapi": "3.0.3",
                    "info": {"title": "Round30 OpenAPI", "version": "1.0.0"},
                    "paths": {
                        "/round30/openapi/ping": {
                            "get": {
                                "summary": "Round30 OpenAPI ping",
                                "responses": {"204": {"description": "No Content"}},
                            }
                        }
                    },
                },
            },
            "GET",
            "/round30/openapi/ping",
            204,
        ),
        (
            "har",
            {
                "source_type": "har",
                "document": {
                    "log": {
                        "version": "1.2",
                        "entries": [
                            {
                                "request": {
                                    "method": "POST",
                                    "url": "https://example.invalid/round30/har/orders?trace=basic",
                                    "headers": [{"name": "Content-Type", "value": "application/json"}],
                                    "postData": {"mimeType": "application/json", "text": "{\"sku\":\"R30\"}"},
                                },
                                "response": {
                                    "status": 201,
                                    "headers": [{"name": "X-Round", "value": "30"}],
                                    "content": {"mimeType": "application/json", "text": "{\"id\":\"order-r30\"}"},
                                },
                            }
                        ],
                    }
                },
            },
            "POST",
            "/round30/har/orders",
            201,
        ),
        (
            "postman",
            {
                "source_type": "postman",
                "collection": {
                    "info": {"name": "Round30 Postman", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
                    "item": [
                        {
                            "name": "Round30 Postman update",
                            "request": {
                                "method": "PUT",
                                "url": {
                                    "raw": "https://example.invalid/round30/postman/items?mode=basic",
                                    "path": ["round30", "postman", "items"],
                                    "query": [{"key": "mode", "value": "basic"}],
                                },
                                "body": {"mode": "raw", "raw": "{\"name\":\"round30\"}"},
                            },
                            "response": [{"code": 202, "body": "{\"accepted\":true}"}],
                        }
                    ],
                },
            },
            "PUT",
            "/round30/postman/items",
            202,
        ),
        (
            "curl",
            {
                "source_type": "curl",
                "command": "curl -X PATCH https://example.invalid/round30/curl/items/1?dryRun=true -H 'Content-Type: application/json' -d '{\"name\":\"round30\"}'",
            },
            "PATCH",
            "/round30/curl/items/1",
            200,
        ),
    ],
)
def test_openapi_har_postman_and_curl_import_basic_regressions_still_pass(
    client,
    label: str,
    payload: dict[str, Any],
    expected_method: str,
    expected_path: str,
    expected_status: int,
):
    context = seed_import_context(f"{label}-{uuid4().hex[:8]}")
    imported = data_of(
        client.post(
            f"{API_PREFIX}/api-test-libs/{context['api_lib_id']}/apis/import",
            json={**payload, "generate_cases": True, "create_cases": True, "create_test_cases": True},
        )
    )

    endpoints = list_items(imported.get("apis") if isinstance(imported, dict) else imported)
    endpoint = next((item for item in endpoints if item.get("path") == expected_path), None)
    assert endpoint is not None, {"expected_path": expected_path, "endpoints": endpoints}
    assert endpoint.get("method") == expected_method, endpoint

    cases = list_items(imported.get("test_cases") or data_of(client.get(f"{API_PREFIX}/apis/{object_id(endpoint)}/test-cases")))
    assert cases, imported
    assert any(api_case_expected_status(case) == expected_status for case in cases), cases
    assert_no_fake_secrets(imported)
