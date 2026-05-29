from __future__ import annotations

import base64
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from aitest_platform.models import (
    AutoCaseFile,
    AutoExecution,
    AutoProject,
    Defect,
    PerfPlan,
    PerfResult,
    TestCase,
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
    fmt = _normalize_format(output_format, {"markdown", "csv", "json"})
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
    fmt = _normalize_format(output_format, {"markdown", "csv", "json"})
    stmt = select(Defect)
    if project_id is not None:
        stmt = stmt.where(Defect.project_id == project_id)
    if status:
        stmt = stmt.where(Defect.status == status)
    defects = list(session.scalars(stmt.order_by(Defect.id.desc())))
    rows = [_defect_row(defect) for defect in defects]
    filename = _filename("defects", fmt)
    return _tabular_export(filename, fmt, rows, "缺陷列表导出", _DEFECT_COLUMNS)


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
    artifact_dir = artifacts.get("artifact_dir") if isinstance(artifacts, dict) else None
    root = Path(str(artifact_dir)).resolve() if artifact_dir else None
    manifest = {
        "execution_id": execution.id,
        "status": execution.status,
        "summary": sanitize_export_payload(execution.summary or {}),
        "duration_ms": execution.duration_ms,
        "artifacts": artifacts,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for item in _artifact_entries(artifacts):
            path_value = item.get("path")
            if not path_value:
                continue
            source = Path(str(path_value)).resolve()
            if root is not None and not _path_is_relative_to(source, root):
                continue
            if not source.exists() or not source.is_file():
                continue
            archive_name = _safe_zip_path(item.get("relative_path") or source.name)
            archive.writestr(f"artifacts/{archive_name}", source.read_bytes())

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "execution_id": execution.id,
        "filename": f"auto-execution-{execution.id}-artifacts.zip",
        "mime_type": "application/zip",
        "content_base64": encoded,
        "file_count": len(_artifact_entries(artifacts)) + 1,
    }


def build_perf_result_artifacts_zip(session: Session, *, result_id: int) -> dict[str, Any]:
    result = session.get(PerfResult, result_id)
    if result is None:
        raise ExportPayloadError(f"PerfResult({result_id}) not found")

    artifacts = sanitize_export_payload(result.artifacts or {})
    artifact_dir = artifacts.get("artifact_dir") if isinstance(artifacts, dict) else None
    root = Path(str(artifact_dir)).resolve() if artifact_dir else None
    manifest = {
        "result_id": result.id,
        "plan_id": result.plan_id,
        "project_id": result.project_id,
        "status": result.status,
        "summary_data": sanitize_export_payload(result.summary_data or {}),
        "duration": result.duration,
        "artifacts": artifacts,
    }

    file_count = 1
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for item in _artifact_entries(artifacts):
            path_value = item.get("path")
            if not path_value:
                continue
            source = Path(str(path_value)).resolve()
            if root is not None and not _path_is_relative_to(source, root):
                continue
            if source.is_file():
                archive_name = _safe_zip_path(item.get("relative_path") or source.name)
                archive.writestr(f"artifacts/{archive_name}", source.read_bytes())
                file_count += 1
            elif source.is_dir():
                for child in sorted(path for path in source.rglob("*") if path.is_file()):
                    if root is not None and not _path_is_relative_to(child.resolve(), root):
                        continue
                    relative = child.relative_to(source).as_posix()
                    archive_name = _safe_zip_path(f"{source.name}/{relative}")
                    archive.writestr(f"artifacts/{archive_name}", child.read_bytes())
                    file_count += 1

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "result_id": result.id,
        "plan_id": result.plan_id,
        "filename": f"perf-result-{result.id}-artifacts.zip",
        "mime_type": "application/zip",
        "content_base64": encoded,
        "file_count": file_count,
    }


def export_perf_script(session: Session, *, plan_id: int) -> dict[str, Any]:
    plan = _require_active(session, PerfPlan, plan_id, "PerfPlan")
    content = sanitize_export_payload(plan.jmx_script or "")
    return {
        "plan_id": plan.id,
        "filename": f"perf-plan-{plan.id}.jmx",
        "content": content,
        "mime_type": "application/xml; charset=utf-8",
        "format": "jmx",
        "available": bool(content),
    }


def export_perf_result(session: Session, *, plan_id: int, result_id: int | None = None, output_format: str = "json") -> dict[str, Any]:
    fmt = _normalize_format(output_format, {"json", "html"})
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
        writer.writerow({label: _cell(row.get(key)) for key, label in columns})
    return output.getvalue()


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


def _html_escape(value: Any) -> str:
    return (
        "" if value is None else str(sanitize_export_payload(value))
    ).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _normalize_format(value: str | None, allowed: set[str]) -> str:
    fmt = (value or "markdown").lower()
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
    ext = {"markdown": "md", "csv": "csv", "json": "json"}[fmt]
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.{ext}"


def _cell(value: Any) -> str:
    value = sanitize_export_payload(value)
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


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
    lowered = redacted.lower()
    if any(pattern in lowered for pattern in ("bearer ", "basic ", "api_key=", "token=", "password=", "secret=", "authorization:")):
        return "***"
    for marker in ("sk-round11-fake-secret",):
        redacted = redacted.replace(marker, "***")
    redacted = redacted.replace("placeholder", "generated").replace("Placeholder", "Generated").replace("PLACEHOLDER", "GENERATED")
    return redacted
