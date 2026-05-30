from __future__ import annotations

import base64
import csv
import io
import json
import re
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

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
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
XMIND_UPLOAD_MIME = "application/x-xmind"
XMIND_MIME_CANDIDATES = {
    "application/octet-stream",
    "application/vnd.xmind.workbook",
    "application/x-xmind",
    "application/xmind",
    "application/zip",
}
REAL_BINARY_EXPORT_FORMATS = ("pdf", "docx", "xmind")
OCR_HINT_MARKERS = ("ocr", "text insufficient", "insufficient text", "needs_ocr", "文本不足", "无文本")
FAKE_FILE_FIELDS = {"filename", "content", "content_base64", "mime_type"}


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
            "document_id": document.id,
            "document_name": document.name,
            "item_id": item.id,
            "item_title": item.title,
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


def seed_report_export_context(marker: str | None = None) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = _create_project(session, marker, "report-export")
        report_name = f"round30-report-export-{marker}"
        report = Report(
            project_id=project.id,
            name=report_name,
            type="comprehensive",
            status="generated",
            related_module="project",
            related_scope_json={"project_id": project.id},
            requirement_item_ids_json=[],
            source_document_ids_json=[],
            scope_snapshot={"project_id": project.id, "token": FAKE_SECRET},
            data_snapshot={"marker": marker, "summary": f"Round30 report export summary {marker}", "cookie": COOKIE_SECRET},
            source_refs_json={"authorization": AUTH_SECRET},
            content=(
                f"# {report_name}\n\n"
                f"Round30 report export visible marker {marker}.\n"
                f"Do not leak token={FAKE_SECRET} or cookie={COOKIE_SECRET}.\n"
            ),
            template_version="r30",
            ai_summary_version="rules",
            generated_at=datetime.now(timezone.utc),
        )
        session.add(report)
        session.flush()
        return {
            "project_id": project.id,
            "report_id": report.id,
            "report_name": report_name,
            "visible_marker": f"Round30 report export visible marker {marker}",
            "marker": marker,
        }


def seed_perf_export_context(marker: str | None = None) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = _create_project(session, marker, "perf-export")
        plan = PerfPlan(
            project_id=project.id,
            name=f"round30-perf-export-{marker}",
            target_doc="p95 <= 300ms",
            plan_schema={"thresholds": {"p95_ms": 300}, "authorization": AUTH_SECRET},
            status="scripted",
        )
        session.add(plan)
        session.flush()
        result = PerfResult(
            plan_id=plan.id,
            project_id=project.id,
            status="completed",
            summary_data={
                "total": 12,
                "passed": 12,
                "failed": 0,
                "p95_ms": 120,
                "visible_note": f"Round30 perf export marker {marker}",
                "api_key": API_KEY_SECRET,
            },
            timeline_data=[{"second": 1, "p95_ms": 120}],
            error_details=[{"note": f"cookie={COOKIE_SECRET}"}],
            artifacts={"token": FAKE_SECRET},
            duration=5,
        )
        session.add(result)
        session.flush()
        return {
            "project_id": project.id,
            "plan_id": plan.id,
            "result_id": result.id,
            "plan_name": plan.name,
            "visible_marker": f"Round30 perf export marker {marker}",
            "marker": marker,
        }


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


def export_binary_bytes(response, *, expected_format: str, allowed_mime_types: set[str]) -> tuple[dict[str, Any], bytes]:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        assert response.status_code == 200, response.text
        mime = content_type.split(";", 1)[0]
        assert mime in allowed_mime_types, response.headers
        disposition = response.headers.get("content-disposition", "")
        if disposition:
            assert f".{expected_format}" in disposition.lower(), disposition
        return {"mime_type": mime, "format": expected_format}, response.content

    payload = response_payload(response)
    assert response.status_code in {200, 201}, response.text
    assert payload.get("code") in {0, 200}, payload
    data = payload.get("data")
    assert isinstance(data, dict), payload
    assert data.get("format") == expected_format, data
    if data.get("filename"):
        assert str(data["filename"]).lower().endswith(f".{expected_format}"), data
    mime = str(data.get("mime_type") or data.get("mime") or "").split(";", 1)[0]
    assert mime in allowed_mime_types, data
    if isinstance(data.get("content_base64"), str):
        return data, base64.b64decode(data["content_base64"])
    if isinstance(data.get("content"), str):
        content = data["content"]
        try:
            return data, base64.b64decode(content, validate=True)
        except Exception:
            return data, content.encode("latin-1")
    pytest.fail(f"{expected_format} export must provide raw bytes or content_base64: {data!r}", pytrace=False)


def xml_text_values(raw_xml: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return []
    return [element.text.strip() for element in root.iter() if element.text and element.text.strip()]


def assert_real_docx(raw_docx: bytes) -> tuple[set[str], str]:
    assert raw_docx.startswith(b"PK"), raw_docx[:8]
    with zipfile.ZipFile(io.BytesIO(raw_docx)) as archive:
        names = set(archive.namelist())
        assert_zip_names_safe(names)
        required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        assert required <= names, names
        xml_fragments: list[str] = []
        for name in names:
            if name.endswith(".xml"):
                raw_xml = archive.read(name)
                xml_fragments.append(raw_xml.decode("utf-8", errors="replace"))
                xml_fragments.extend(xml_text_values(raw_xml))
        combined = "\n".join(xml_fragments)
        return names, combined


def collect_json_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(collect_json_strings(item))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(collect_json_strings(item))
        return result
    return []


def assert_real_xmind(raw_xmind: bytes) -> tuple[set[str], str]:
    assert raw_xmind.startswith(b"PK"), raw_xmind[:8]
    with zipfile.ZipFile(io.BytesIO(raw_xmind)) as archive:
        names = set(archive.namelist())
        assert_zip_names_safe(names)
        assert "content.json" in names or "content.xml" in names, names
        fragments: list[str] = []
        if "content.json" in names:
            content_json = json.loads(archive.read("content.json").decode("utf-8"))
            fragments.extend(collect_json_strings(content_json))
        if "content.xml" in names:
            raw_xml = archive.read("content.xml")
            fragments.append(raw_xml.decode("utf-8", errors="replace"))
            fragments.extend(xml_text_values(raw_xml))
        combined = "\n".join(item for item in fragments if item)
        assert combined.strip(), combined
        return names, combined


def pdf_candidate_text(raw_pdf: bytes) -> str:
    fragments = [raw_pdf.decode("latin-1", errors="ignore")]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw_pdf, re.DOTALL):
        chunk = match.group(1).strip(b"\r\n")
        if not chunk:
            continue
        for candidate in (chunk, _maybe_inflate_pdf_stream(chunk)):
            if not candidate:
                continue
            for encoding in ("utf-8", "latin-1", "utf-16-be", "utf-16-le"):
                try:
                    fragments.append(candidate.decode(encoding))
                except UnicodeDecodeError:
                    continue
            fragments.extend(_decode_pdf_hex_strings(candidate))
    return "\n".join(fragments)


def _maybe_inflate_pdf_stream(value: bytes) -> bytes | None:
    try:
        return zlib.decompress(value)
    except Exception:
        return None


def assert_real_pdf(raw_pdf: bytes) -> str:
    assert raw_pdf.startswith(b"%PDF-"), raw_pdf[:8]
    assert b"%%EOF" in raw_pdf[-2048:], raw_pdf[-2048:]
    combined = pdf_candidate_text(raw_pdf)
    assert combined.strip(), combined
    return combined


def assert_text_contains_expected_markers(text: str, *, present: tuple[str, ...], absent: tuple[str, ...] = ()) -> None:
    for marker in present:
        assert marker in text, {"missing": marker, "text": text}
    for marker in absent:
        assert marker not in text, {"unexpected": marker, "text": text}


def _decode_pdf_hex_strings(raw_bytes: bytes) -> list[str]:
    decoded: list[str] = []
    for match in re.finditer(rb"<([0-9A-Fa-f\s]+)>", raw_bytes):
        compact = re.sub(rb"\s+", b"", match.group(1))
        if not compact or len(compact) % 2:
            continue
        try:
            binary = bytes.fromhex(compact.decode("ascii"))
        except ValueError:
            continue
        for encoding in ("utf-16-be", "utf-8", "latin-1"):
            try:
                text = binary.decode(encoding)
            except UnicodeDecodeError:
                continue
            if text.strip():
                decoded.append(text)
    return decoded


def _excel_column_name(index: int) -> str:
    letters = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters or "A"


def docx_payload_bytes(paragraphs: list[str], table_rows: list[list[str]]) -> bytes:
    def paragraph_xml(text: str) -> str:
        return f"<w:p><w:r><w:t>{xml_escape(text)}</w:t></w:r></w:p>"

    table_xml = ""
    if table_rows:
        table_rows_xml = []
        for row in table_rows:
            cells = "".join(
                f"<w:tc><w:p><w:r><w:t>{xml_escape(cell)}</w:t></w:r></w:p></w:tc>"
                for cell in row
            )
            table_rows_xml.append(f"<w:tr>{cells}</w:tr>")
        table_xml = f"<w:tbl>{''.join(table_rows_xml)}</w:tbl>"

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(paragraph_xml(item) for item in paragraphs)}
    {table_xml}
    <w:sectPr/>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def xlsx_payload_bytes(rows: list[list[str]]) -> bytes:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}

    def string_id(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_excel_column_name(column_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="s"><v>{string_id(value)}</v></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Round30" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(xml_rows)}</sheetData>
</worksheet>"""
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        + "".join(f"<si><t>{xml_escape(item)}</t></si>" for item in shared_strings)
        + "</sst>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
    return buffer.getvalue()


def xmind_payload_bytes(lines: list[str]) -> bytes:
    topic_nodes = [
        {"id": f"topic-{index}", "title": line}
        for index, line in enumerate(lines, start=1)
    ]
    content_json = [
        {
            "id": "sheet-1",
            "class": "sheet",
            "title": "Round30 XMind Sheet",
            "rootTopic": {
                "id": "root-1",
                "title": lines[0],
                "children": {"attached": topic_nodes[1:]},
            },
        }
    ]
    xml_topics = "".join(
        f'<topic id="topic-{index}"><title>{xml_escape(line)}</title></topic>'
        for index, line in enumerate(lines[1:], start=1)
    )
    content_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" version="2.0">
  <sheet id="sheet-1">
    <title>Round30 XMind Sheet</title>
    <topic id="root-1">
      <title>{xml_escape(lines[0])}</title>
      <children>
        <topics type="attached">{xml_topics}</topics>
      </children>
    </topic>
  </sheet>
</xmap-content>"""
    manifest_xml = """<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns="urn:xmind:xmap:xmlns:manifest:1.0">
  <file-entry full-path="content.json" media-type="text/plain"/>
  <file-entry full-path="content.xml" media-type="text/xml"/>
</manifest>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.json", json.dumps(content_json, ensure_ascii=False))
        archive.writestr("content.xml", content_xml)
        archive.writestr("META-INF/manifest.xml", manifest_xml)
    return buffer.getvalue()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_payload_bytes(lines: list[str], *, title: str = "Round30 PDF") -> bytes:
    text_ops = ["BT", "/F1 12 Tf", "72 760 Td"]
    for index, line in enumerate(lines):
        if index:
            text_ops.append("0 -18 Td")
        text_ops.append(f"({_pdf_escape(line)}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream\nendobj\n",
        f"6 0 obj\n<< /Title ({_pdf_escape(title)}) >>\nendobj\n".encode("latin-1"),
    ]
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref_pos = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.write(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF"
        ).encode("latin-1")
    )
    return buffer.getvalue()


def build_requirement_binary_sample(file_type: str) -> dict[str, Any]:
    if file_type == "docx":
        visible = ("Round30 DOCX Heading", "Visible paragraph for docx parsing", "Priority", "P0")
        raw_bytes = docx_payload_bytes(
            [visible[0], visible[1], f"token={FAKE_SECRET} should be redacted"],
            [["Field", "Value"], [visible[2], visible[3]], ["Cookie", COOKIE_SECRET]],
        )
        mime_type = DOCX_MIME
    elif file_type == "xlsx":
        visible = ("Module", "Round30 XLSX table row", "Status", "Ready")
        raw_bytes = xlsx_payload_bytes(
            [
                ["Column", "Value"],
                [visible[0], visible[1]],
                [visible[2], visible[3]],
                ["Authorization", AUTH_SECRET],
            ]
        )
        mime_type = XLSX_MIME
    elif file_type == "xmind":
        visible = ("Round30 XMind Root", "Requirement Branch", "Scenario Leaf")
        raw_bytes = xmind_payload_bytes([*visible, f"secret {FAKE_SECRET} must be redacted"])
        mime_type = XMIND_UPLOAD_MIME
    elif file_type == "pdf":
        visible = ("Round30 PDF Requirement", "Visible text PDF body", "Export contract must parse text")
        raw_bytes = pdf_payload_bytes([*visible, f"api_key={API_KEY_SECRET} must be redacted"], title=visible[0])
        mime_type = PDF_MIME
    else:
        raise AssertionError(file_type)
    return {"bytes": raw_bytes, "mime_type": mime_type, "expected_markers": visible}


def build_binary_curl_container(file_type: str) -> dict[str, Any]:
    command = (
        f"curl -X GET https://example.invalid/round30/binary/{file_type}/health?mode={file_type} "
        f"-H 'Authorization: {AUTH_SECRET}' "
        f"-H 'Cookie: {COOKIE_SECRET}' "
        "-H 'Content-Type: application/json'"
    )
    if file_type == "docx":
        raw_bytes = docx_payload_bytes(
            ["Round30 API binary import docx", "Visible curl command follows"],
            [["Command", command], ["Note", f"api_key={API_KEY_SECRET}"]],
        )
        mime_type = DOCX_MIME
    elif file_type == "xlsx":
        raw_bytes = xlsx_payload_bytes(
            [["Type", "Value"], ["Command", command], ["Secret", f"token={FAKE_SECRET}"]]
        )
        mime_type = XLSX_MIME
    elif file_type == "xmind":
        raw_bytes = xmind_payload_bytes(
            ["Round30 API binary root", "Curl command", command, f"cookie {COOKIE_SECRET}"]
        )
        mime_type = XMIND_UPLOAD_MIME
    elif file_type == "pdf":
        raw_bytes = pdf_payload_bytes(["Round30 API binary PDF", command, f"secret {FAKE_SECRET}"], title="Round30 API binary PDF")
        mime_type = PDF_MIME
    else:
        raise AssertionError(file_type)
    return {
        "bytes": raw_bytes,
        "mime_type": mime_type,
        "path": f"/round30/binary/{file_type}/health",
        "method": "GET",
        "expected_status": 200,
    }


def build_blank_pdf_container() -> bytes:
    return pdf_payload_bytes([], title="")


def binary_upload_payload(
    *,
    file_type: str,
    mime_type: str,
    raw_bytes: bytes,
    source_type: str,
    source_file_name: str,
    name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_type": source_type,
        "file_type": file_type,
        "source_file_name": source_file_name,
        "mime_type": mime_type,
        "content_base64": base64.b64encode(raw_bytes).decode("ascii"),
    }
    if name is not None:
        payload["name"] = name
    if extra:
        payload.update(extra)
    return payload


def post_api_binary_import(client, target: str, api_lib_id: int, payload: dict[str, Any]):
    path = (
        f"{API_PREFIX}/api-test-libs/{api_lib_id}/import-documents"
        if target == "api-documents"
        else f"{API_PREFIX}/api-test-libs/{api_lib_id}/apis/import"
    )
    return api_request(client, "post", path, json=payload)


def assert_ocr_needed_contract(response) -> dict[str, Any]:
    payload = response_payload(response)
    assert {"code", "message", "data"} <= payload.keys(), payload
    dumped = payload_text(payload).lower()
    assert "unsupported" not in dumped, payload
    assert any(marker in dumped for marker in OCR_HINT_MARKERS), payload
    if response.status_code in {200, 201}:
        assert payload["code"] in {0, 200}, payload
        data = payload.get("data")
        assert isinstance(data, dict), payload
        data_dump = payload_text(data).lower()
        assert any(marker in data_dump for marker in OCR_HINT_MARKERS), data
        for key in ("blocks", "items", "apis", "test_cases"):
            value = data.get(key)
            assert value in (None, [], {}), data
    else:
        assert response.status_code in {400, 409, 415, 422}, response.text
        assert payload["code"] not in {0, 200, 201}, payload
    assert_no_fake_secrets(payload)
    return payload


def assert_export_file_contract(
    fmt: str,
    raw_bytes: bytes,
    *,
    present_markers: tuple[str, ...],
    absent_markers: tuple[str, ...] = (),
) -> str:
    if fmt == "docx":
        _, combined = assert_real_docx(raw_bytes)
    elif fmt == "xmind":
        _, combined = assert_real_xmind(raw_bytes)
    elif fmt == "pdf":
        combined = assert_real_pdf(raw_bytes)
    else:
        raise AssertionError(fmt)
    assert_text_contains_expected_markers(combined, present=present_markers, absent=absent_markers)
    assert_no_fake_secrets(combined)
    assert_no_fake_secrets(raw_bytes.decode("latin-1", errors="ignore"))
    return combined


def export_mime_candidates(fmt: str) -> set[str]:
    if fmt == "pdf":
        return {PDF_MIME}
    if fmt == "docx":
        return {DOCX_MIME}
    if fmt == "xmind":
        return XMIND_MIME_CANDIDATES
    raise AssertionError(fmt)


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


@pytest.mark.parametrize("fmt", REAL_BINARY_EXPORT_FORMATS)
def test_test_case_binary_exports_return_real_files_filter_data_and_redact_secrets(client, fmt: str):
    context = seed_export_context()

    response = client.get(
        f"{API_PREFIX}/test-cases/export",
        params={"projectId": context["project_id"], "caseIds": str(context["case_id"]), "format": fmt},
    )
    exported, raw_bytes = export_binary_bytes(response, expected_format=fmt, allowed_mime_types=export_mime_candidates(fmt))
    assert exported.get("count") in {None, 1}, exported
    assert_export_file_contract(
        fmt,
        raw_bytes,
        present_markers=(context["case_title"],),
        absent_markers=(context["unselected_case_title"], context["foreign_case_title"]),
    )
    assert_no_fake_secrets(exported)


@pytest.mark.parametrize("fmt", REAL_BINARY_EXPORT_FORMATS)
def test_defect_binary_exports_return_real_files_filter_data_and_redact_secrets(client, fmt: str):
    context = seed_export_context()

    response = client.get(
        f"{API_PREFIX}/defects/export",
        params={"projectId": context["project_id"], "status": "open", "format": fmt},
    )
    exported, raw_bytes = export_binary_bytes(response, expected_format=fmt, allowed_mime_types=export_mime_candidates(fmt))
    assert exported.get("count") in {None, 1}, exported
    assert_export_file_contract(
        fmt,
        raw_bytes,
        present_markers=(context["defect_title"],),
        absent_markers=(context["closed_defect_title"], context["foreign_defect_title"]),
    )
    assert_no_fake_secrets(exported)


@pytest.mark.parametrize("fmt", REAL_BINARY_EXPORT_FORMATS)
def test_report_binary_exports_return_real_files_and_redact_secrets(client, fmt: str):
    context = seed_report_export_context()

    response = api_request(
        client,
        "get",
        f"{API_PREFIX}/reports/{context['report_id']}/download",
        params={"format": fmt},
    )
    exported, raw_bytes = export_binary_bytes(response, expected_format=fmt, allowed_mime_types=export_mime_candidates(fmt))
    assert_export_file_contract(
        fmt,
        raw_bytes,
        present_markers=(context["report_name"],),
    )
    assert_no_fake_secrets(exported)


@pytest.mark.parametrize("fmt", REAL_BINARY_EXPORT_FORMATS)
def test_performance_binary_exports_return_real_files_and_redact_secrets(client, fmt: str):
    context = seed_perf_export_context()

    response = api_request(
        client,
        "get",
        f"{API_PREFIX}/perf-plans/{context['plan_id']}/results/{context['result_id']}/download",
        params={"format": fmt},
    )
    exported, raw_bytes = export_binary_bytes(response, expected_format=fmt, allowed_mime_types=export_mime_candidates(fmt))
    assert_export_file_contract(
        fmt,
        raw_bytes,
        present_markers=(context["plan_name"], context["visible_marker"]),
    )
    assert_no_fake_secrets(exported)


@pytest.mark.parametrize("fmt", REAL_BINARY_EXPORT_FORMATS)
def test_requirement_document_binary_exports_return_real_files_and_redact_secrets(client, fmt: str):
    context = seed_export_context()

    response = api_request(
        client,
        "get",
        f"{API_PREFIX}/requirement-documents/{context['document_id']}/export",
        params={"format": fmt},
    )
    exported, raw_bytes = export_binary_bytes(response, expected_format=fmt, allowed_mime_types=export_mime_candidates(fmt))
    assert_export_file_contract(
        fmt,
        raw_bytes,
        present_markers=(context["document_name"], context["item_title"]),
    )
    assert_no_fake_secrets(exported)


@pytest.mark.parametrize("fmt", REAL_BINARY_EXPORT_FORMATS)
def test_requirement_item_binary_exports_return_real_files_and_redact_secrets(client, fmt: str):
    context = seed_export_context()

    response = api_request(
        client,
        "get",
        f"{API_PREFIX}/requirement-items/{context['item_id']}/export",
        params={"format": fmt},
    )
    exported, raw_bytes = export_binary_bytes(response, expected_format=fmt, allowed_mime_types=export_mime_candidates(fmt))
    assert_export_file_contract(
        fmt,
        raw_bytes,
        present_markers=(context["item_title"],),
    )
    assert_no_fake_secrets(exported)


@pytest.mark.parametrize("file_type", ("docx", "xlsx", "xmind", "pdf"))
def test_requirement_documents_parse_binary_files_extract_visible_content_and_redact_secrets(client, file_type: str):
    context = seed_import_context(f"req-{file_type}-{uuid4().hex[:6]}")
    sample = build_requirement_binary_sample(file_type)
    create_payload = binary_upload_payload(
        file_type=file_type,
        mime_type=sample["mime_type"],
        raw_bytes=sample["bytes"],
        source_type=file_type,
        source_file_name=f"round30-requirement.{file_type}",
        name=f"Round30 {file_type} requirement import",
        extra={"lib_id": context["lib_id"]},
    )

    document = data_of(
        api_request(
            client,
            "post",
            f"{API_PREFIX}/projects/{context['project_id']}/requirement-documents",
            json=create_payload,
        )
    )
    document_id = object_id(document, "id", "document_id")
    parsed = data_of(api_request(client, "post", f"{API_PREFIX}/requirement-documents/{document_id}/parse", json={"mode": "round30-binary"}))
    blocks = parsed.get("blocks") or []
    assert isinstance(blocks, list) and blocks, parsed
    extracted = data_of(
        api_request(
            client,
            "post",
            f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
            json={"mode": "round30-binary"},
        )
    )
    items = list_items(extracted.get("items") or extracted)
    assert items, extracted

    combined = payload_text({"document": document, "parse": parsed, "items": items})
    assert_text_contains_expected_markers(combined, present=sample["expected_markers"])
    assert_no_fake_secrets(document)
    assert_no_fake_secrets(parsed)
    assert_no_fake_secrets(items)


def test_requirement_document_blank_pdf_returns_structured_ocr_needed_instead_of_unsupported(client):
    context = seed_import_context(f"req-pdf-ocr-{uuid4().hex[:6]}")
    payload = binary_upload_payload(
        file_type="pdf",
        mime_type=PDF_MIME,
        raw_bytes=build_blank_pdf_container(),
        source_type="pdf",
        source_file_name="round30-blank.pdf",
        name="Round30 blank pdf import",
        extra={"lib_id": context["lib_id"]},
    )

    create_response = api_request(
        client,
        "post",
        f"{API_PREFIX}/projects/{context['project_id']}/requirement-documents",
        json=payload,
    )
    if create_response.status_code not in {200, 201}:
        assert_ocr_needed_contract(create_response)
        return

    document = data_of(create_response)
    parse_response = api_request(
        client,
        "post",
        f"{API_PREFIX}/requirement-documents/{object_id(document, 'id', 'document_id')}/parse",
        json={"mode": "round30-binary"},
    )
    assert_ocr_needed_contract(parse_response)


@pytest.mark.parametrize("target", ["api-documents", "api-import"])
@pytest.mark.parametrize("file_type", ("docx", "xlsx", "xmind", "pdf"))
def test_api_import_parses_binary_wrappers_and_keeps_case_generation_working(client, target: str, file_type: str):
    context = seed_import_context(f"api-{target}-{file_type}-{uuid4().hex[:6]}")
    sample = build_binary_curl_container(file_type)
    payload = binary_upload_payload(
        file_type=file_type,
        mime_type=sample["mime_type"],
        raw_bytes=sample["bytes"],
        source_type="curl",
        source_file_name=f"round30-api-import.{file_type}",
        extra={"generate_cases": True, "create_cases": True, "create_test_cases": True},
    )

    imported = data_of(post_api_binary_import(client, target, context["api_lib_id"], payload))
    endpoints = list_items(imported.get("apis") if isinstance(imported, dict) else imported)
    endpoint = next((item for item in endpoints if item.get("path") == sample["path"]), None)
    assert endpoint is not None, {"expected_path": sample["path"], "endpoints": endpoints}
    assert endpoint.get("method") == sample["method"], endpoint

    cases = list_items(imported.get("test_cases") or data_of(client.get(f"{API_PREFIX}/apis/{object_id(endpoint)}/test-cases")))
    assert any(api_case_expected_status(case) == sample["expected_status"] for case in cases), cases
    assert_no_fake_secrets(imported)
    assert_no_fake_secrets(cases)


@pytest.mark.parametrize("target", ["api-documents", "api-import"])
def test_api_import_blank_pdf_returns_structured_ocr_needed_instead_of_unsupported(client, target: str):
    context = seed_import_context(f"api-{target}-pdf-ocr-{uuid4().hex[:6]}")
    payload = binary_upload_payload(
        file_type="pdf",
        mime_type=PDF_MIME,
        raw_bytes=build_blank_pdf_container(),
        source_type="curl",
        source_file_name="round30-api-blank.pdf",
        extra={"generate_cases": True, "create_cases": True, "create_test_cases": True},
    )

    response = post_api_binary_import(client, target, context["api_lib_id"], payload)
    assert_ocr_needed_contract(response)


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
