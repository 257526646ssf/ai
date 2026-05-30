from __future__ import annotations

import base64
import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable
from xml.sax.saxutils import escape as xml_escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from aitest_platform.models import (
    AutoCaseFile,
    AutoExecution,
    AutoProject,
    Defect,
    PerfPlan,
    PerfResult,
    RequirementDocument,
    RequirementDocumentBlock,
    RequirementItem,
    TestCase,
    TestPoint,
)
from aitest_platform.services.perf_analysis import render_jmeter_script
from aitest_platform.services.file_formats import (
    UnsupportedFormatError,
    is_unsupported_export_format,
    normalize_format,
    unsupported_export_detail,
)
from aitest_platform.services.office_formats import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    XLSX_MIME_TYPE,
    XMIND_MIME_TYPE,
    markdown_to_blocks,
    render_docx_document,
    render_pdf_document,
    render_xmind_document,
)

SENSITIVE_MARKERS = (
    "authorization",
    "api_key",
    "api-key",
    "apikey",
    "token",
    "cookie",
    "password",
    "secret",
    "git_auth",
)
TEXT_ARTIFACT_SUFFIXES = {".css", ".csv", ".html", ".js", ".json", ".log", ".md", ".txt", ".xml", ".yaml", ".yml"}
TABULAR_EXPORT_FORMATS = {"markdown", "csv", "json", "xlsx", "pdf", "docx", "xmind"}
PERF_RESULT_EXPORT_FORMATS = {"json", "html", "markdown", "pdf", "docx", "xmind"}
REQUIREMENT_EXPORT_FORMATS = {"json", "markdown", "pdf", "docx", "xmind"}
FORMULA_PREFIXES = ("=", "+", "-", "@")


class ExportPayloadError(ValueError):
    pass


def export_test_cases(
    session: Session,
    *,
    project_id: int | None = None,
    requirement_item_id: int | None = None,
    case_ids: Iterable[int] | None = None,
    case_type: str | None = None,
    output_format: str = "markdown",
) -> dict[str, Any]:
    fmt = _normalize_format(output_format, TABULAR_EXPORT_FORMATS)
    stmt = select(TestCase).where(TestCase.is_deleted.is_(False))
    if project_id is not None:
        stmt = stmt.where(TestCase.project_id == project_id)
    if requirement_item_id is not None:
        stmt = stmt.where(TestCase.requirement_item_id == requirement_item_id)
    ids = _unique_ints(case_ids or [])
    if ids:
        stmt = stmt.where(TestCase.id.in_(ids))
    if case_type:
        stmt = stmt.where(TestCase.case_type == case_type)
    cases = list(session.scalars(stmt.order_by(TestCase.id)))
    rows = [_test_case_row(case) for case in cases]
    filename = _filename("test-cases", fmt)
    return _tabular_export(filename, fmt, rows, "测试用例导出", _TEST_CASE_COLUMNS)


def export_defects(
    session: Session,
    *,
    project_id: int | None = None,
    status: str | None = None,
    output_format: str = "markdown",
) -> dict[str, Any]:
    fmt = _normalize_format(output_format, TABULAR_EXPORT_FORMATS)
    stmt = select(Defect)
    if project_id is not None:
        stmt = stmt.where(Defect.project_id == project_id)
    if status:
        stmt = stmt.where(Defect.status == status)
    defects = list(session.scalars(stmt.order_by(Defect.id.desc())))
    rows = [_defect_row(defect) for defect in defects]
    filename = _filename("defects", fmt)
    return _tabular_export(filename, fmt, rows, "缺陷列表导出", _DEFECT_COLUMNS)


def export_requirement_document(
    session: Session,
    *,
    document_id: int,
    output_format: str = "markdown",
) -> dict[str, Any]:
    fmt = _normalize_format(output_format, REQUIREMENT_EXPORT_FORMATS)
    document = _require_active(session, RequirementDocument, document_id, "RequirementDocument")
    blocks = list(
        session.scalars(
            select(RequirementDocumentBlock)
            .where(RequirementDocumentBlock.document_id == document.id)
            .order_by(RequirementDocumentBlock.order_no, RequirementDocumentBlock.id)
        )
    )
    items = list(
        session.scalars(
            select(RequirementItem)
            .where(RequirementItem.document_id == document.id, RequirementItem.is_deleted.is_(False))
            .order_by(RequirementItem.id)
        )
    )
    payload = {
        "document": _requirement_document_row(document),
        "parser_metadata": sanitize_export_payload(document.parser_metadata or {}),
        "items": [_requirement_item_row(item) for item in items],
        "blocks": [_requirement_block_row(block) for block in blocks],
    }
    markdown = _render_requirement_document_markdown(document, blocks, items)
    filename_stem = _safe_filename_stem(document.source_file_name or document.name, fallback=f"requirement-document-{document.id}")
    return _requirement_export_payload(filename_stem, fmt, payload, markdown, count=len(items))


def export_requirement_item(
    session: Session,
    *,
    item_id: int,
    output_format: str = "markdown",
) -> dict[str, Any]:
    fmt = _normalize_format(output_format, REQUIREMENT_EXPORT_FORMATS)
    item = _require_active(session, RequirementItem, item_id, "RequirementItem")
    document = session.get(RequirementDocument, item.document_id)
    all_blocks = list(
        session.scalars(
            select(RequirementDocumentBlock)
            .where(RequirementDocumentBlock.document_id == item.document_id)
            .order_by(RequirementDocumentBlock.order_no, RequirementDocumentBlock.id)
        )
    )
    anchor_ids = {str(anchor) for anchor in (item.source_anchor_ids or []) if anchor not in (None, "")}
    source_blocks = [block for block in all_blocks if str(block.block_key) in anchor_ids] if anchor_ids else all_blocks[:3]
    test_points = list(
        session.scalars(
            select(TestPoint)
            .where(TestPoint.requirement_item_id == item.id, TestPoint.is_deleted.is_(False))
            .order_by(TestPoint.id)
        )
    )
    test_cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.requirement_item_id == item.id, TestCase.is_deleted.is_(False))
            .order_by(TestCase.id)
        )
    )
    payload = {
        "item": _requirement_item_row(item),
        "document": _requirement_document_row(document) if document is not None else None,
        "source_blocks": [_requirement_block_row(block) for block in source_blocks],
        "test_points": [_test_point_row(point) for point in test_points],
        "test_cases": [_test_case_row(case) for case in test_cases],
    }
    markdown = _render_requirement_item_markdown(item, document, source_blocks, test_points, test_cases)
    filename_stem = _safe_filename_stem(item.item_number or item.title, fallback=f"requirement-item-{item.id}")
    return _requirement_export_payload(filename_stem, fmt, payload, markdown, count=1)


def build_auto_project_zip(session: Session, *, auto_project_id: int) -> dict[str, Any]:
    project = _require_active(session, AutoProject, auto_project_id, "AutoProject")
    case_files = list(
        session.scalars(
            select(AutoCaseFile)
            .where(AutoCaseFile.auto_project_id == project.id, AutoCaseFile.is_deleted.is_(False))
            .order_by(AutoCaseFile.id)
        )
    )
    file_map: dict[str, str] = {}
    for path, content in (project.framework_files or {}).items():
        file_map[_safe_zip_path(str(path))] = _text_content(content)
    if project.readme and not any(path.lower().endswith("readme.md") for path in file_map):
        file_map["README.md"] = project.readme
    if not any(path.lower() == "pytest.ini" for path in file_map):
        file_map["pytest.ini"] = "[pytest]\naddopts = -q\n"
    for case_file in case_files:
        path = _safe_zip_path(case_file.file_path or case_file.file_name)
        file_map[path] = case_file.content or ""
    if not file_map:
        file_map["README.md"] = f"# {project.name}\n\nNo generated automation files yet.\n"
    files = sorted(file_map.items())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in files:
            archive.writestr(path, sanitize_export_payload(content))
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "auto_project_id": project.id,
        "download_url": f"/api/v2/auto-projects/{project.id}/download",
        "filename": f"auto-project-{project.id}.zip",
        "mime_type": "application/zip",
        "content_base64": encoded,
        "files": [{"path": path, "size": len(content.encode("utf-8"))} for path, content in files],
        "file_count": len(files),
    }


def build_auto_execution_artifacts_zip(session: Session, *, execution_id: int) -> dict[str, Any]:
    execution = session.get(AutoExecution, execution_id)
    if execution is None:
        raise ExportPayloadError(f"AutoExecution({execution_id}) not found")

    artifacts = sanitize_export_payload(execution.artifacts or {})
    included_files, skipped_files = _collect_artifact_files(artifacts)
    manifest = {
        "execution_id": execution.id,
        "status": execution.status,
        "summary": sanitize_export_payload(execution.summary or {}),
        "duration_ms": execution.duration_ms,
        "artifacts": artifacts,
        "included_artifacts": sanitize_export_payload(included_files),
        "skipped_artifacts": sanitize_export_payload(skipped_files),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for item in included_files:
            source = Path(str(item["path"]))
            archive.writestr(f"artifacts/{item['archive_name']}", _artifact_archive_bytes(source))

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "execution_id": execution.id,
        "filename": f"auto-execution-{execution.id}-artifacts.zip",
        "mime_type": "application/zip",
        "content_base64": encoded,
        "file_count": len(included_files) + 1,
        "skipped_count": len(skipped_files),
    }


def build_perf_result_artifacts_zip(session: Session, *, result_id: int) -> dict[str, Any]:
    result = session.get(PerfResult, result_id)
    if result is None:
        raise ExportPayloadError(f"PerfResult({result_id}) not found")

    artifacts = sanitize_export_payload(result.artifacts or {})
    included_files, skipped_files = _collect_artifact_files(artifacts)
    manifest = {
        "result_id": result.id,
        "plan_id": result.plan_id,
        "project_id": result.project_id,
        "status": result.status,
        "summary_data": sanitize_export_payload(result.summary_data or {}),
        "duration": result.duration,
        "artifacts": artifacts,
        "included_artifacts": sanitize_export_payload(included_files),
        "skipped_artifacts": sanitize_export_payload(skipped_files),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for item in included_files:
            source = Path(str(item["path"]))
            archive.writestr(f"artifacts/{item['archive_name']}", _artifact_archive_bytes(source))

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "result_id": result.id,
        "plan_id": result.plan_id,
        "filename": f"perf-result-{result.id}-artifacts.zip",
        "mime_type": "application/zip",
        "content_base64": encoded,
        "file_count": len(included_files) + 1,
        "skipped_count": len(skipped_files),
    }


def export_perf_script(session: Session, *, plan_id: int) -> dict[str, Any]:
    plan = _require_active(session, PerfPlan, plan_id, "PerfPlan")
    content = sanitize_export_payload(render_jmeter_script(plan.plan_schema or {}, plan.jmx_script))
    return {
        "plan_id": plan.id,
        "filename": f"perf-plan-{plan.id}.jmx",
        "content": content,
        "mime_type": "application/xml; charset=utf-8",
        "format": "jmx",
        "available": bool(content),
    }


def export_perf_result(session: Session, *, plan_id: int, result_id: int | None = None, output_format: str = "json") -> dict[str, Any]:
    fmt = _normalize_format(output_format, PERF_RESULT_EXPORT_FORMATS)
    plan = _require_active(session, PerfPlan, plan_id, "PerfPlan")
    stmt = select(PerfResult).where(PerfResult.plan_id == plan.id)
    if result_id is not None:
        stmt = stmt.where(PerfResult.id == result_id)
    result = session.scalar(stmt.order_by(PerfResult.executed_at.desc(), PerfResult.id.desc()).limit(1))
    if result is None:
        raise ExportPayloadError(f"PerfResult({result_id or 'latest'}) not found")
    payload = sanitize_export_payload(
        {
            "plan": {"id": plan.id, "name": plan.name, "status": plan.status},
            "result": _perf_result_row(result),
            "raw_data": {
                "path": result.raw_data_path,
                "available": bool(result.raw_data_path),
                "note": "原始文件由本地 runner 持久化；缺少路径时请先执行真实 JMeter runner。",
            },
        }
    )
    if fmt == "html":
        content = _render_perf_result_html(payload)
        return {
            "plan_id": plan.id,
            "result_id": result.id,
            "filename": f"perf-result-{result.id}.html",
            "content": content,
            "mime_type": "text/html; charset=utf-8",
            "format": fmt,
            "raw_data_path": payload["raw_data"]["path"],
            "raw_file_available": payload["raw_data"]["available"],
        }
    if fmt in {"markdown", "pdf", "docx", "xmind"}:
        markdown = _render_perf_result_markdown(payload)
        if fmt == "markdown":
            return {
                "plan_id": plan.id,
                "result_id": result.id,
                "filename": f"perf-result-{result.id}.md",
                "content": markdown,
                "mime_type": "text/markdown; charset=utf-8",
                "format": fmt,
                "raw_data_path": payload["raw_data"]["path"],
                "raw_file_available": payload["raw_data"]["available"],
            }
        exported = _binary_document_export(f"perf-result-{result.id}.{fmt}", fmt, markdown)
        exported.update(
            {
                "plan_id": plan.id,
                "result_id": result.id,
                "raw_data_path": payload["raw_data"]["path"],
                "raw_file_available": payload["raw_data"]["available"],
            }
        )
        return exported
    return {
        "plan_id": plan.id,
        "result_id": result.id,
        "filename": f"perf-result-{result.id}.json",
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
        "mime_type": "application/json; charset=utf-8",
        "format": fmt,
        "raw_data_path": payload["raw_data"]["path"],
        "raw_file_available": payload["raw_data"]["available"],
    }


def sanitize_export_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            clean[key] = sanitize_export_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_export_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


_TEST_CASE_COLUMNS = (
    ("case_number", "用例编号"),
    ("title", "标题"),
    ("case_type", "类型"),
    ("priority", "优先级"),
    ("status", "状态"),
    ("precondition", "前置条件"),
    ("steps", "步骤"),
    ("expected_result", "预期结果"),
)

_DEFECT_COLUMNS = (
    ("defect_number", "缺陷编号"),
    ("title", "标题"),
    ("severity", "严重级别"),
    ("status", "状态"),
    ("actual_result", "实际结果"),
    ("remark", "备注"),
)


def _tabular_export(filename: str, fmt: str, rows: list[dict[str, Any]], title: str, columns: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    safe_rows = sanitize_export_payload(rows)
    if fmt == "json":
        content = json.dumps({"title": title, "count": len(safe_rows), "records": safe_rows}, ensure_ascii=False, indent=2)
        mime_type = "application/json; charset=utf-8"
    elif fmt == "csv":
        content = _render_csv(safe_rows, columns)
        mime_type = "text/csv; charset=utf-8"
    elif fmt == "xlsx":
        content_base64 = base64.b64encode(_render_xlsx(safe_rows, columns, title=title)).decode("ascii")
        return {
            "filename": filename,
            "content_base64": content_base64,
            "mime_type": XLSX_MIME_TYPE,
            "format": fmt,
            "count": len(safe_rows),
        }
    elif fmt in {"pdf", "docx", "xmind"}:
        markdown = _render_markdown(title, safe_rows, columns)
        return _binary_document_export(filename, fmt, markdown, count=len(safe_rows))
    else:
        content = _render_markdown(title, safe_rows, columns)
        mime_type = "text/markdown; charset=utf-8"
    return {
        "filename": filename,
        "content": content,
        "mime_type": mime_type,
        "format": fmt,
        "count": len(safe_rows),
    }


def _render_csv(rows: list[dict[str, Any]], columns: tuple[tuple[str, str], ...]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[label for _, label in columns], extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({label: _spreadsheet_cell(row.get(key)) for key, label in columns})
    return output.getvalue()


def _render_xlsx(rows: list[dict[str, Any]], columns: tuple[tuple[str, str], ...], *, title: str) -> bytes:
    sheet_rows = [[label for _, label in columns]]
    sheet_rows.extend([[_spreadsheet_cell(row.get(key)) for key, _ in columns] for row in rows])
    sheet_xml = _xlsx_sheet_xml(sheet_rows)
    workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{_xml_attr(_sheet_name(title))}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types())
        archive.writestr("_rels/.rels", _xlsx_root_relationships())
        archive.writestr("docProps/app.xml", _xlsx_app_props())
        archive.writestr("docProps/core.xml", _xlsx_core_props())
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_relationships())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def _xlsx_sheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_excel_column_name(column_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{_xml_text(value)}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    {''.join(xml_rows)}
  </sheetData>
</worksheet>"""


def _xlsx_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""


def _xlsx_root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _xlsx_workbook_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _xlsx_app_props() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>AI Test Platform</Application>
</Properties>"""


def _xlsx_core_props() -> str:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>AI Test Platform</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>"""


def _render_markdown(title: str, rows: list[dict[str, Any]], columns: tuple[tuple[str, str], ...]) -> str:
    lines = [f"# {title}", "", f"- 数量：{len(rows)}", ""]
    if not rows:
        lines.append("暂无数据。")
        return "\n".join(lines) + "\n"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines.extend([header, divider])
    for row in rows:
        cells = [_escape_markdown(_cell(row.get(key))) for key, _ in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _render_requirement_document_markdown(
    document: RequirementDocument,
    blocks: list[RequirementDocumentBlock],
    items: list[RequirementItem],
) -> str:
    metadata = sanitize_export_payload(document.parser_metadata or {})
    lines = [
        f"# Requirement Document {document.name}",
        "",
        "## Overview",
        f"- Document Number: {_cell(document.document_number)}",
        f"- Source Type: {_cell(document.source_type)}",
        f"- Source File: {_cell(document.source_file_name or document.name)}",
        f"- Parser Status: {_cell(document.parser_status)}",
        f"- Version: {_cell(document.version)}",
        f"- Requirement Items: {len(items)}",
        f"- Parsed Blocks: {len(blocks)}",
        "",
    ]
    if metadata:
        lines.extend(["## Parser Metadata", "| Field | Value |", "| --- | --- |"])
        for key, value in metadata.items():
            lines.append(f"| {key} | {_escape_markdown(_cell(value))} |")
        lines.append("")
    if items:
        lines.extend(
            [
                "## Requirement Items",
                "| Item Number | Title | Priority | Status | Module | Confidence |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in items:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_markdown(_cell(item.item_number)),
                        _escape_markdown(_cell(item.title)),
                        _escape_markdown(_cell(item.priority)),
                        _escape_markdown(_cell(item.status)),
                        _escape_markdown(_cell(item.module)),
                        _escape_markdown(_cell(item.confidence)),
                    ]
                )
                + " |"
            )
        lines.append("")
    else:
        lines.extend(["## Requirement Items", "- No requirement items extracted yet.", ""])
    if blocks:
        lines.append("## Parsed Blocks")
        for block in blocks:
            lines.extend(
                [
                    f"### {block.block_key} ({block.block_type})",
                    f"- Section: {_cell(block.section_path or 'N/A')}",
                    f"- Order: {_cell(block.order_no)}",
                ]
            )
            text = str(sanitize_export_payload(block.raw_text or block.normalized_text or "")).strip()
            if text:
                lines.extend(["", text])
            lines.append("")
    elif document.raw_content:
        lines.extend(["## Raw Content", str(sanitize_export_payload(document.raw_content)).strip(), ""])
    else:
        lines.extend(["## Raw Content", "- No parsed blocks or raw content available.", ""])
    return "\n".join(lines).strip() + "\n"


def _render_requirement_item_markdown(
    item: RequirementItem,
    document: RequirementDocument | None,
    source_blocks: list[RequirementDocumentBlock],
    test_points: list[TestPoint],
    test_cases: list[TestCase],
) -> str:
    lines = [
        f"# Requirement Item {item.title}",
        "",
        "## Overview",
        f"- Item Number: {_cell(item.item_number)}",
        f"- Document: {_cell(document.name if document is not None else item.document_id)}",
        f"- Module: {_cell(item.module)}",
        f"- Priority: {_cell(item.priority)}",
        f"- Status: {_cell(item.status)}",
        f"- Confidence: {_cell(item.confidence)}",
        f"- Granularity Flag: {_cell(item.granularity_flag)}",
        f"- Case Status: {_cell(item.case_status)}",
        f"- Source Anchors: {_cell(item.source_anchor_ids or [])}",
        "",
    ]
    if item.summary:
        lines.extend(["## Summary", str(sanitize_export_payload(item.summary)).strip(), ""])
    for title, value in (
        ("Actor", item.actor),
        ("Goal", item.goal),
        ("Preconditions", item.preconditions_json),
        ("Business Rules", item.business_rules_json),
        ("State Transitions", item.state_transitions_json),
        ("Exceptions", item.exceptions_json),
        ("Permissions", item.permissions_json),
        ("Non Functional", item.non_functional_json),
    ):
        rendered = _render_requirement_detail_section(title, value)
        if rendered:
            lines.extend(rendered)
    if source_blocks:
        lines.append("## Source Blocks")
        for block in source_blocks:
            lines.extend(
                [
                    f"### {block.block_key} ({block.block_type})",
                    f"- Section: {_cell(block.section_path or 'N/A')}",
                ]
            )
            text = str(sanitize_export_payload(block.raw_text or block.normalized_text or "")).strip()
            if text:
                lines.extend(["", text])
            lines.append("")
    if test_points:
        lines.extend(
            [
                "## Test Points",
                "| Title | Type | Priority | Coverage Status |",
                "| --- | --- | --- | --- |",
            ]
        )
        for point in test_points:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_markdown(_cell(point.title)),
                        _escape_markdown(_cell(point.point_type)),
                        _escape_markdown(_cell(point.priority)),
                        _escape_markdown(_cell(point.coverage_status)),
                    ]
                )
                + " |"
            )
        lines.append("")
    if test_cases:
        lines.extend(
            [
                "## Test Cases",
                "| Case Number | Title | Type | Priority | Status |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for case in test_cases:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_markdown(_cell(case.case_number)),
                        _escape_markdown(_cell(case.title)),
                        _escape_markdown(_cell(case.case_type)),
                        _escape_markdown(_cell(case.priority)),
                        _escape_markdown(_cell(case.status)),
                    ]
                )
                + " |"
            )
        lines.append("")
    if not source_blocks and not test_points and not test_cases:
        lines.extend(["## Linked Data", "- No parsed source blocks, test points, or test cases available.", ""])
    return "\n".join(lines).strip() + "\n"


def _render_requirement_detail_section(title: str, value: Any) -> list[str]:
    safe_value = sanitize_export_payload(value)
    if safe_value in (None, "", [], {}):
        return []
    lines = [f"## {title}"]
    if isinstance(safe_value, list):
        for item in safe_value:
            lines.append(f"- {_escape_markdown(_cell(item))}")
    elif isinstance(safe_value, dict):
        lines.extend(["| Field | Value |", "| --- | --- |"])
        for key, item in safe_value.items():
            lines.append(f"| {key} | {_escape_markdown(_cell(item))} |")
    else:
        lines.append(_cell(safe_value))
    lines.append("")
    return lines


def _test_case_row(case: TestCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "project_id": case.project_id,
        "requirement_item_id": case.requirement_item_id,
        "case_number": case.case_number,
        "title": case.title,
        "case_type": case.case_type,
        "priority": case.priority,
        "status": case.status,
        "precondition": case.precondition,
        "steps": case.steps,
        "expected_result": case.expected_result,
        "tags": case.tags,
    }


def _defect_row(defect: Defect) -> dict[str, Any]:
    return {
        "id": defect.id,
        "project_id": defect.project_id,
        "execution_id": defect.execution_id,
        "case_id": defect.case_id,
        "requirement_item_id": defect.requirement_item_id,
        "defect_number": defect.defect_number,
        "title": defect.title,
        "severity": defect.severity,
        "status": defect.status,
        "actual_result": defect.actual_result,
        "remark": defect.remark,
    }


def _requirement_document_row(document: RequirementDocument | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "id": document.id,
        "project_id": document.project_id,
        "lib_id": document.lib_id,
        "document_number": document.document_number,
        "name": document.name,
        "source_type": document.source_type,
        "source_file_name": document.source_file_name,
        "source_file_path": document.source_file_path,
        "raw_content": document.raw_content,
        "parser_status": document.parser_status,
        "parser_metadata": document.parser_metadata,
        "version": document.version,
        "created_at": _iso_value(document.created_at),
        "updated_at": _iso_value(document.updated_at),
    }


def _requirement_block_row(block: RequirementDocumentBlock) -> dict[str, Any]:
    return {
        "id": block.id,
        "document_id": block.document_id,
        "block_key": block.block_key,
        "block_type": block.block_type,
        "section_path": block.section_path,
        "order_no": block.order_no,
        "page_no": block.page_no,
        "raw_text": block.raw_text,
        "normalized_text": block.normalized_text,
        "metadata_json": block.metadata_json,
        "created_at": _iso_value(block.created_at),
    }


def _requirement_item_row(item: RequirementItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "lib_id": item.lib_id,
        "document_id": item.document_id,
        "item_number": item.item_number,
        "title": item.title,
        "summary": item.summary,
        "module": item.module,
        "actor": item.actor,
        "goal": item.goal,
        "preconditions": item.preconditions_json,
        "business_rules": item.business_rules_json,
        "state_transitions": item.state_transitions_json,
        "exceptions": item.exceptions_json,
        "permissions": item.permissions_json,
        "non_functional": item.non_functional_json,
        "priority": item.priority,
        "status": item.status,
        "confidence": item.confidence,
        "granularity_flag": item.granularity_flag,
        "source_anchor_ids": item.source_anchor_ids,
        "case_status": item.case_status,
        "version": item.version,
        "created_at": _iso_value(item.created_at),
        "updated_at": _iso_value(item.updated_at),
    }


def _test_point_row(point: TestPoint) -> dict[str, Any]:
    return {
        "id": point.id,
        "requirement_item_id": point.requirement_item_id,
        "title": point.title,
        "point_type": point.point_type,
        "target": point.target,
        "priority": point.priority,
        "suggested_method": point.suggested_method,
        "coverage_status": point.coverage_status,
        "source_anchor_ids": point.source_anchor_ids,
        "note": point.note,
        "has_generated_cases": point.has_generated_cases,
    }


def _perf_result_row(result: PerfResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "plan_id": result.plan_id,
        "project_id": result.project_id,
        "status": result.status,
        "summary_data": result.summary_data,
        "timeline_data": result.timeline_data,
        "error_details": result.error_details,
        "raw_data_path": result.raw_data_path,
        "artifacts": result.artifacts,
        "duration": result.duration,
        "executed_at": result.executed_at.isoformat() if isinstance(result.executed_at, datetime) else result.executed_at,
    }


def _artifact_entries(artifacts: Any) -> list[dict[str, Any]]:
    if not isinstance(artifacts, dict):
        return []
    entries: list[dict[str, Any]] = []
    for key in ("evidence", "files"):
        value = artifacts.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    runner_log = artifacts.get("runner_log")
    if runner_log:
        entries.append({"kind": "log", "path": runner_log, "relative_path": "runner.log"})
    unique: dict[str, dict[str, Any]] = {}
    for entry in entries:
        path = entry.get("path")
        if path:
            unique[str(path)] = entry
    return list(unique.values())


def _collect_artifact_files(artifacts: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries = _artifact_entries(artifacts)
    root = _artifact_root(artifacts)
    included: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for entry in entries:
        source = _canonical_path(entry.get("path"))
        if source is None:
            skipped.append(_skipped_artifact(entry, "invalid_path"))
            continue
        if root is None:
            skipped.append(_skipped_artifact(entry, "missing_artifact_root", canonical_path=str(source)))
            continue
        if not _path_is_relative_to(source, root):
            skipped.append(_skipped_artifact(entry, "outside_artifact_root", canonical_path=str(source)))
            continue
        if source.is_file():
            if not _artifact_relative_path_allowed(entry):
                skipped.append(_skipped_artifact(entry, "relative_path_outside_artifact_root", canonical_path=str(source)))
                continue
            archive_name = _artifact_archive_name(source, root, entry)
            marker = (str(source), archive_name)
            if marker not in seen:
                seen.add(marker)
                included.append(_included_artifact(source, archive_name, entry, root))
            continue
        if source.is_dir():
            for child in sorted(path for path in source.rglob("*") if path.is_file()):
                child_source = _canonical_path(child)
                if child_source is None or not _path_is_relative_to(child_source, root):
                    skipped.append(_skipped_artifact({"path": str(child)}, "outside_artifact_root"))
                    continue
                archive_name = _safe_zip_path(child_source.relative_to(root).as_posix())
                marker = (str(child_source), archive_name)
                if marker in seen:
                    continue
                seen.add(marker)
                included.append(_included_artifact(child_source, archive_name, entry, root))
            continue
        skipped.append(_skipped_artifact(entry, "not_found", canonical_path=str(source)))

    return included, skipped


def _artifact_root(artifacts: Any) -> Path | None:
    if not isinstance(artifacts, dict):
        return None
    for key in ("artifact_dir", "artifact_root", "root_dir"):
        value = artifacts.get(key)
        if value:
            return _canonical_path(value)
    return None


def _canonical_path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    try:
        return Path(str(value)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _artifact_archive_name(source: Path, root: Path, entry: dict[str, Any]) -> str:
    relative_path = entry.get("relative_path")
    if relative_path:
        return _safe_zip_path(str(relative_path))
    return _safe_zip_path(source.relative_to(root).as_posix())


def _artifact_relative_path_allowed(entry: dict[str, Any]) -> bool:
    relative_path = entry.get("relative_path")
    if relative_path in (None, ""):
        return True
    path = PurePosixPath(str(relative_path).replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and ":" not in path.parts[0]


def _included_artifact(source: Path, archive_name: str, entry: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        size_bytes = source.stat().st_size
    except OSError:
        size_bytes = 0
    return {
        "kind": entry.get("kind") or entry.get("type") or entry.get("artifact_type"),
        "path": str(source),
        "relative_path": source.relative_to(root).as_posix(),
        "archive_name": archive_name,
        "size_bytes": size_bytes,
    }


def _skipped_artifact(entry: dict[str, Any], reason: str, *, canonical_path: str | None = None) -> dict[str, Any]:
    return {
        "reason": reason,
        "kind": entry.get("kind") or entry.get("type") or entry.get("artifact_type"),
        "path": entry.get("path"),
        "relative_path": entry.get("relative_path"),
        "canonical_path": canonical_path,
    }


def _render_perf_result_html(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    result = payload.get("result") or {}
    summary = result.get("summary_data") or {}
    timeline = result.get("timeline_data") or []
    errors = result.get("error_details") or []
    rows = "\n".join(
        f"<tr><td>{_html_escape(item.get('second'))}</td><td>{_html_escape(item.get('samples'))}</td><td>{_html_escape(item.get('avg_ms'))}</td><td>{_html_escape(item.get('failed'))}</td></tr>"
        for item in timeline[:200]
        if isinstance(item, dict)
    )
    error_items = "".join(f"<li>{_html_escape(json.dumps(item, ensure_ascii=False, default=str))}</li>" for item in errors[:20])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Performance Result {result.get('id')}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #0f172a; background: #f8fafc; }}
    h1 {{ font-size: 22px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }}
    .label {{ color: #64748b; font-size: 12px; }}
    .value {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e2e8f0; }}
    th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #e2e8f0; font-size: 12px; }}
    th {{ background: #f1f5f9; }}
    code {{ background: #e2e8f0; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>{_html_escape(plan.get('name') or 'Performance Result')}</h1>
  <p>Result #{_html_escape(result.get('id'))} · Status: <code>{_html_escape(result.get('status'))}</code></p>
  <section class="grid">
    <div class="card"><div class="label">Samples</div><div class="value">{_html_escape(summary.get('total'))}</div></div>
    <div class="card"><div class="label">Average RT</div><div class="value">{_html_escape(summary.get('avg_ms'))}ms</div></div>
    <div class="card"><div class="label">P95 RT</div><div class="value">{_html_escape(summary.get('p95_ms'))}ms</div></div>
    <div class="card"><div class="label">Error Rate</div><div class="value">{_html_escape(summary.get('error_rate'))}</div></div>
  </section>
  <h2>Timeline</h2>
  <table>
    <thead><tr><th>Second</th><th>Samples</th><th>Avg RT</th><th>Failed</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="4">No timeline data</td></tr>'}</tbody>
  </table>
  <h2>Errors</h2>
  <ul>{error_items or '<li>No errors</li>'}</ul>
</body>
</html>"""


def _render_perf_result_markdown(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    result = payload.get("result") or {}
    summary = result.get("summary_data") or {}
    timeline = result.get("timeline_data") or []
    errors = result.get("error_details") or []
    lines = [
        f"# Performance Result {result.get('id') or ''}".strip(),
        "",
        "## Plan",
        f"- Name: {plan.get('name') or 'N/A'}",
        f"- Status: {plan.get('status') or 'unknown'}",
        "",
        "## Result",
        f"- Result ID: {result.get('id') or 'N/A'}",
        f"- Status: {result.get('status') or 'unknown'}",
        f"- Duration: {result.get('duration') or 0}",
        f"- Executed At: {result.get('executed_at') or 'N/A'}",
        "",
        "## Summary",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    if summary:
        for key, value in summary.items():
            lines.append(f"| {key} | {_escape_markdown(_cell(value))} |")
    else:
        lines.append("| summary | no data |")
    lines.extend(["", "## Timeline", "| Item | Value |", "| --- | --- |"])
    if isinstance(timeline, list) and timeline:
        for index, item in enumerate(timeline[:50], start=1):
            lines.append(f"| {index} | {_escape_markdown(_cell(item))} |")
    else:
        lines.append("| timeline | no data |")
    lines.extend(["", "## Errors"])
    if isinstance(errors, list) and errors:
        for item in errors[:20]:
            lines.append(f"- {_escape_markdown(_cell(item))}")
    else:
        lines.append("- No errors")
    lines.extend(
        [
            "",
            "## Raw Data",
            f"- Path: {payload.get('raw_data', {}).get('path') or 'N/A'}",
            f"- Available: {payload.get('raw_data', {}).get('available')}",
            f"- Note: {payload.get('raw_data', {}).get('note') or 'N/A'}",
            "",
        ]
    )
    return "\n".join(lines)


def _html_escape(value: Any) -> str:
    return (
        "" if value is None else str(sanitize_export_payload(value))
    ).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _normalize_format(value: str | None, allowed: set[str]) -> str:
    fmt = normalize_format(value or "markdown") or "markdown"
    if is_unsupported_export_format(fmt):
        raise UnsupportedFormatError(unsupported_export_detail(fmt, allowed))
    if fmt not in allowed:
        raise ExportPayloadError(f"format must be one of: {', '.join(sorted(allowed))}")
    return fmt


def _unique_ints(values: Iterable[Any]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in (None, ""):
            continue
        item = int(value)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _require_active(session: Session, model: type[Any], item_id: int, label: str) -> Any:
    item = session.get(model, item_id)
    if item is None or getattr(item, "is_deleted", False):
        raise ExportPayloadError(f"{label}({item_id}) not found")
    return item


def _filename(prefix: str, fmt: str) -> str:
    ext = {"markdown": "md", "csv": "csv", "json": "json", "xlsx": "xlsx", "pdf": "pdf", "docx": "docx", "xmind": "xmind"}[fmt]
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.{ext}"


def _safe_filename_stem(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in text:
        text = text.rsplit(".", 1)[0]
    text = re.sub(r'[<>:"/\\\\|?*]+', "-", text)
    text = re.sub(r"\s+", "-", text).strip(" .-_")
    return text[:96] or fallback


def _cell(value: Any) -> str:
    value = sanitize_export_payload(value)
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _spreadsheet_cell(value: Any) -> str:
    text = _cell(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def _excel_column_name(index: int) -> str:
    letters = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters or "A"


def _sheet_name(value: str) -> str:
    clean = "".join(ch if ch not in "[]:*?/\\'" else " " for ch in str(value or "Sheet1")).strip()
    return (clean[:31] or "Sheet1")


def _xml_text(value: Any) -> str:
    return xml_escape(_strip_invalid_xml_chars(str(value or "")), {'"': "&quot;"})


def _xml_attr(value: Any) -> str:
    return _xml_text(value)


def _strip_invalid_xml_chars(value: str) -> str:
    return "".join(ch for ch in value if ch in "\t\n\r" or ord(ch) >= 32)


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _text_content(value: Any) -> str:
    value = sanitize_export_payload(value)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _safe_zip_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    parts = [part for part in path.parts if part not in {"", ".", ".."} and ":" not in part]
    clean = "/".join(parts).lstrip("/")
    clean = clean.replace("placeholder", "generated").replace("Placeholder", "Generated").replace("PLACEHOLDER", "GENERATED")
    return clean or "file.txt"


def _artifact_archive_bytes(source: Path) -> bytes:
    if source.suffix.lower() in TEXT_ARTIFACT_SUFFIXES:
        text = source.read_text(encoding="utf-8", errors="replace")
        return str(sanitize_export_payload(text)).encode("utf-8")
    return source.read_bytes()


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS) or lowered.endswith("_token") or lowered.endswith("-token")


def _redact_sensitive_text(value: str) -> str:
    redacted = value
    redacted = re.sub(r"(?im)^\s*authorization\s*:\s*.*$", "***", redacted)
    redacted = re.sub(r"(?im)^\s*cookie\s*:\s*.*$", "***", redacted)
    redacted = re.sub(r"(?i)\b(?:bearer|basic)\s+[^\s,;}\]\"']+", "***", redacted)
    redacted = re.sub(r"(?i)\b(?:api[_-]?key|token|cookie|password|secret)(\s*[:=]\s*)[^\s,;}\]\"']+", "***", redacted)
    for marker in ("sk-round11-fake-secret",):
        redacted = redacted.replace(marker, "***")
    redacted = re.sub(r"(?i)round\d+-[a-z0-9_-]*secret[a-z0-9_-]*", "***", redacted)
    redacted = redacted.replace("placeholder", "generated").replace("Placeholder", "Generated").replace("PLACEHOLDER", "GENERATED")
    return redacted


def _binary_document_export(filename: str, fmt: str, markdown: str, *, count: int | None = None) -> dict[str, Any]:
    safe_markdown = str(sanitize_export_payload(markdown))
    blocks = markdown_to_blocks(safe_markdown)
    title = _document_title_from_blocks(filename, blocks)
    if fmt == "pdf":
        raw_bytes = render_pdf_document(title, blocks)
        mime_type = PDF_MIME_TYPE
    elif fmt == "docx":
        raw_bytes = render_docx_document(title, blocks)
        mime_type = DOCX_MIME_TYPE
    elif fmt == "xmind":
        raw_bytes = render_xmind_document(title, blocks)
        mime_type = XMIND_MIME_TYPE
    else:
        raise ExportPayloadError(f"format must be one of: {fmt}")
    payload = {
        "filename": filename,
        "content_base64": base64.b64encode(raw_bytes).decode("ascii"),
        "mime_type": mime_type,
        "format": fmt,
    }
    if count is not None:
        payload["count"] = count
    return payload


def _document_title_from_blocks(filename: str, blocks: list[dict[str, Any]]) -> str:
    for block in blocks:
        if block.get("type") == "heading" and str(block.get("text") or "").strip():
            return str(block.get("text")).strip()
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[0] or "Document"


def _requirement_export_payload(
    filename_stem: str,
    fmt: str,
    payload: dict[str, Any],
    markdown: str,
    *,
    count: int,
) -> dict[str, Any]:
    if fmt == "json":
        return {
            "filename": f"{filename_stem}.json",
            "content": json.dumps(sanitize_export_payload(payload), ensure_ascii=False, indent=2),
            "mime_type": "application/json; charset=utf-8",
            "format": "json",
            "count": count,
        }
    if fmt == "markdown":
        return {
            "filename": f"{filename_stem}.md",
            "content": str(sanitize_export_payload(markdown)),
            "mime_type": "text/markdown; charset=utf-8",
            "format": "markdown",
            "count": count,
        }
    return _binary_document_export(f"{filename_stem}.{fmt}", fmt, markdown, count=count)


def _iso_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value
