from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from aitest_platform.models import (
    ApiEndpoint,
    ApiExecution,
    ApiTestCase,
    ApiTestLib,
    AutoExecution,
    AutoProject,
    Defect,
    Execution,
    OperationLog,
    PerfPlan,
    PerfResult,
    Project,
    Report,
    ReportTodo,
    ReportTemplate,
    RequirementDocument,
    RequirementItem,
    TestCase,
    TestRound,
)
from aitest_platform.services.perf_analysis import build_performance_summary, performance_recommendations, performance_risk_items
from aitest_platform.services.file_formats import UnsupportedFormatError, is_unsupported_export_format, unsupported_export_detail

SENSITIVE_MARKERS = (
    "api_key",
    "api-key",
    "apikey",
    "token",
    "cookie",
    "password",
    "secret",
    "authorization",
    "git_auth",
)

SUCCESS_STATUSES = {"pass", "passed", "success", "succeeded", "ok", "completed"}
FAIL_STATUSES = {"fail", "failed", "error", "timeout"}
OPEN_DEFECT_STATUSES = {"open", "new", "active", "reopen", "reopened", "todo", "待修复", "待处理"}


SUPPORTED_REPORT_FORMATS = {"markdown", "html", "json"}
DEFAULT_MODULE_TYPES = ["functional", "api", "automation", "performance"]
MODULE_ALIASES = {
    "functional": "functional",
    "requirement": "functional",
    "requirements": "functional",
    "testcase": "functional",
    "testcases": "functional",
    "test_case": "functional",
    "test_cases": "functional",
    "execution": "functional",
    "executions": "functional",
    "defect": "functional",
    "defects": "functional",
    "api": "api",
    "interface": "api",
    "interfaces": "api",
    "automation": "automation",
    "auto": "automation",
    "performance": "performance",
    "perf": "performance",
}
SECTION_ALIASES = {
    "summary": "overview",
    "scope": "overview",
    "coverage": "requirements",
    "requirement": "requirements",
    "testcase": "test_cases",
    "testcases": "test_cases",
    "case": "test_cases",
    "cases": "test_cases",
    "round": "test_rounds",
    "rounds": "test_rounds",
    "execution": "executions",
    "defect": "defects",
    "auto": "automation",
    "perf": "performance",
    "risk": "risks",
    "todo": "todos",
    "todos": "todos",
    "recommendation": "recommendations",
    "source": "source_documents",
    "sources": "source_documents",
    "document": "source_documents",
    "documents": "source_documents",
    "evidences": "evidence",
    "refs": "evidence",
}
SECTION_TITLES = {
    "overview": "Overview",
    "metrics": "Metrics",
    "requirements": "Requirements",
    "source_documents": "Source Documents",
    "test_cases": "Test Cases",
    "test_rounds": "Test Rounds",
    "executions": "Executions",
    "defects": "Defects",
    "api": "API",
    "automation": "Automation",
    "performance": "Performance",
    "risks": "Risks",
    "todos": "Todos",
    "recommendations": "Recommendations",
    "evidence": "Evidence",
    "conclusion": "Conclusion",
}
DEFAULT_REPORT_SECTIONS = [
    "overview",
    "metrics",
    "requirements",
    "test_cases",
    "executions",
    "defects",
    "api",
    "automation",
    "performance",
    "risks",
    "todos",
    "recommendations",
    "evidence",
    "conclusion",
]
TODO_STATUSES = {"open", "pending", "todo", "in_progress", "blocked", "done", "dismissed"}


class ReportingPayloadError(ValueError):
    pass


def sanitize_report_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if _is_sensitive_key(lowered) or "placeholder" in lowered:
                continue
            clean[key] = sanitize_report_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_report_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def create_comprehensive_report(
    session: Session,
    *,
    project_id: int,
    name: str,
    report_type: str = "comprehensive",
    requirement_item_ids: Iterable[int] | None = None,
    source_document_ids: Iterable[int] | None = None,
    module_types: Iterable[str] | None = None,
    time_range: dict[str, Any] | None = None,
    template_id: int | None = None,
    related_scope: dict[str, Any] | None = None,
) -> Report:
    context = build_aggregation_context(
        session,
        project_id=project_id,
        requirement_item_ids=list(requirement_item_ids or []),
        source_document_ids=list(source_document_ids or []),
        module_types=list(module_types or []),
        time_range=time_range,
        template_id=template_id,
        report_type=report_type,
    )
    template_version = context["scope_snapshot"]["template"]["version"]
    effective_template_id = context["scope_snapshot"]["template"]["id"]
    report = Report(
        project_id=project_id,
        name=name,
        type=report_type,
        status="generated",
        related_module="project",
        related_scope_json=sanitize_report_payload(related_scope or context["report_scope"]),
        requirement_item_ids_json=context["report_scope"]["requirement_item_ids"],
        source_document_ids_json=context["report_scope"]["source_document_ids"],
        scope_snapshot=context["scope_snapshot"],
        data_snapshot=context["data_snapshot"],
        source_refs_json=context["source_refs_json"],
        content="",
        template_id=effective_template_id,
        template_version=template_version,
        ai_summary_version="rules-v1",
    )
    session.add(report)
    session.flush()
    context["report_id"] = report.id
    report.content = render_markdown_report(name, context)
    _log(session, "generate_comprehensive", report.id, {"project_id": project_id, "type": report_type})
    return report


def create_performance_report(session: Session, *, plan_id: int, template_id: int | None = None) -> tuple[Report, PerfResult | None]:
    plan = _require_active(session, PerfPlan, plan_id, "PerfPlan")
    result = session.scalar(
        select(PerfResult)
        .where(PerfResult.plan_id == plan.id)
        .order_by(PerfResult.executed_at.desc(), PerfResult.id.desc())
        .limit(1)
    )
    context = build_aggregation_context(
        session,
        project_id=plan.project_id,
        requirement_item_ids=plan.requirement_item_ids_json or [],
        source_document_ids=[plan.source_document_id] if plan.source_document_id else [],
        module_types=["performance"],
        template_id=template_id,
        perf_plan_id=plan.id,
        perf_result_id=result.id if result else None,
        report_type="performance",
    )
    name = f"{plan.name} 性能测试报告"
    report = Report(
        project_id=plan.project_id,
        name=name,
        type="performance",
        status="generated",
        related_module="perf_plan",
        related_scope_json={"plan_id": plan.id, "result_id": result.id if result else None},
        requirement_item_ids_json=plan.requirement_item_ids_json or [],
        source_document_ids_json=context["report_scope"]["source_document_ids"],
        scope_snapshot=context["scope_snapshot"],
        data_snapshot=context["data_snapshot"],
        source_refs_json=context["source_refs_json"],
        content="",
        template_id=context["scope_snapshot"]["template"]["id"],
        template_version=context["scope_snapshot"]["template"]["version"],
        ai_summary_version="rules-v1",
    )
    session.add(report)
    session.flush()
    context["report_id"] = report.id
    report.content = render_markdown_report(name, context)
    _log(session, "generate_performance", report.id, {"plan_id": plan.id, "result_id": result.id if result else None})
    return report, result


def build_lightweight_conclusion(
    session: Session,
    *,
    project_id: int | None,
    requirement_item_ids: Iterable[int] | None = None,
    conclusion_type: str = "brief",
    save: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    if project_id is None:
        return {
            "type": conclusion_type,
            "conclusion_type": conclusion_type,
            "conclusion": "缺少 project_id，已使用安全降级结论：请补充项目范围后生成可追溯的测试结论。",
            "metrics": {},
            "saved": False,
            "report": None,
            "fallback": True,
        }

    context = build_aggregation_context(
        session,
        project_id=project_id,
        requirement_item_ids=list(requirement_item_ids or []),
    )
    metrics = context["data_snapshot"]["summary_metrics"]
    risk_items = context["data_snapshot"]["risk_items"]
    conclusion = _brief_conclusion(metrics, risk_items, conclusion_type)
    result: dict[str, Any] = {
        "type": conclusion_type,
        "conclusion_type": conclusion_type,
        "conclusion": conclusion,
        "metrics": {
            "requirements": context["data_snapshot"]["requirements"],
            "test_cases": context["data_snapshot"]["test_cases"],
            "executions": context["data_snapshot"]["executions"],
            "defects": context["data_snapshot"]["defects"],
            "api": context["data_snapshot"]["api"],
            "auto": context["data_snapshot"]["auto"],
            "perf": context["data_snapshot"]["perf"],
            "summary": metrics,
        },
        "risk_items": risk_items[:10],
        "source_refs": context["source_refs_json"],
        "scope": context["report_scope"],
        "saved": False,
        "report": None,
        "fallback": False,
    }
    if save:
        report_name = name or _lightweight_name(conclusion_type)
        report = Report(
            project_id=project_id,
            name=report_name,
            type="lightweight_conclusion",
            status="generated",
            related_module="project",
            related_scope_json=context["report_scope"],
            requirement_item_ids_json=context["report_scope"]["requirement_item_ids"],
            source_document_ids_json=context["report_scope"]["source_document_ids"],
            scope_snapshot=context["scope_snapshot"],
            data_snapshot={**context["data_snapshot"], "lightweight_conclusion": conclusion, "lightweight_conclusion_type": conclusion_type},
            source_refs_json=context["source_refs_json"],
            content=f"# {report_name}\n\n{conclusion}\n",
            template_version=context["scope_snapshot"]["template"]["version"],
            ai_summary_version="rules-v1",
        )
        session.add(report)
        session.flush()
        _log(session, "save_lightweight_conclusion", report.id, {"project_id": project_id, "type": conclusion_type})
        result["saved"] = True
        result["report"] = _model_dict(report)
        result["report_id"] = report.id
    return sanitize_report_payload(result)


def build_aggregation_context(
    session: Session,
    *,
    project_id: int,
    requirement_item_ids: list[int] | None = None,
    source_document_ids: list[int] | None = None,
    module_types: list[str] | None = None,
    time_range: dict[str, Any] | None = None,
    template_id: int | None = None,
    perf_plan_id: int | None = None,
    perf_result_id: int | None = None,
    report_type: str = "comprehensive",
) -> dict[str, Any]:
    project = _require_active(session, Project, project_id, "Project")
    requested_item_ids = _unique_ints(requirement_item_ids or [], "requirement_item_ids")
    requested_document_ids = _unique_ints(source_document_ids or [], "source_document_ids")
    selected_modules = _normalize_module_types(module_types)
    start_at, end_at, normalized_time_range = _normalize_time_range(time_range)
    requested_documents = _require_documents(session, project_id, requested_document_ids)

    fact_filter_item_ids = requested_item_ids
    item_stmt = select(RequirementItem).where(RequirementItem.project_id == project_id, RequirementItem.is_deleted.is_(False))
    if requested_item_ids:
        item_stmt = item_stmt.where(RequirementItem.id.in_(requested_item_ids))
    if requested_document_ids:
        item_stmt = item_stmt.where(RequirementItem.document_id.in_(requested_document_ids))
    item_stmt = _apply_created_range(item_stmt, RequirementItem, start_at, end_at)
    requirement_items = list(session.scalars(item_stmt.order_by(RequirementItem.id)))
    resolved_item_ids = [item.id for item in requirement_items]
    if requested_item_ids and set(resolved_item_ids) != set(requested_item_ids):
        raise ReportingPayloadError("requirement_item_ids must belong to the selected project/source_document scope")
    if requested_document_ids:
        fact_filter_item_ids = resolved_item_ids
    item_filter = resolved_item_ids or requested_item_ids

    documents = _documents_for_scope(session, project_id, requirement_items, requested_documents, start_at, end_at)
    if "functional" in selected_modules:
        test_cases = _test_cases(session, project_id, fact_filter_item_ids, start_at, end_at)
        executions = _executions(session, project_id, fact_filter_item_ids, start_at, end_at)
        defects = _defects(session, project_id, fact_filter_item_ids, start_at, end_at)
        rounds = _test_rounds(session, project_id, fact_filter_item_ids, start_at, end_at)
    else:
        test_cases, executions, defects, rounds = [], [], [], []

    if "api" in selected_modules:
        api_libs, api_endpoints, api_test_cases, api_executions = _api_facts(
            session,
            project_id,
            fact_filter_item_ids,
            requested_document_ids,
            start_at,
            end_at,
        )
    else:
        api_libs, api_endpoints, api_test_cases, api_executions = [], [], [], []

    if "automation" in selected_modules:
        auto_projects, auto_executions = _auto_facts(session, project_id, start_at, end_at)
    else:
        auto_projects, auto_executions = [], []

    if "performance" in selected_modules:
        perf_plans, perf_results = _perf_facts(
            session,
            project_id,
            fact_filter_item_ids,
            requested_document_ids,
            perf_plan_id,
            perf_result_id,
            start_at,
            end_at,
        )
    else:
        perf_plans, perf_results = [], []

    template = _select_report_template(session, report_type, template_id)
    template_sections = normalize_report_sections(template.sections if template else DEFAULT_REPORT_SECTIONS, strict=False)

    resolved_document_ids = sorted({document.id for document in documents})
    report_scope = {
        "project_id": project_id,
        "requirement_item_ids": resolved_item_ids,
        "requested_requirement_item_ids": requested_item_ids,
        "source_document_ids": resolved_document_ids,
        "requested_source_document_ids": requested_document_ids,
        "module_types": selected_modules,
        "time_range": normalized_time_range,
        "perf_plan_id": perf_plan_id,
        "perf_result_id": perf_result_id,
    }
    source_refs = {
        "project_id": project_id,
        "requirement_item_ids": resolved_item_ids,
        "source_document_ids": resolved_document_ids,
        "test_case_ids": [case.id for case in test_cases],
        "test_round_ids": [round_.id for round_ in rounds],
        "execution_ids": [execution.id for execution in executions],
        "defect_ids": [defect.id for defect in defects],
        "api_test_lib_ids": [lib.id for lib in api_libs],
        "api_endpoint_ids": [endpoint.id for endpoint in api_endpoints],
        "api_test_case_ids": [case.id for case in api_test_cases],
        "api_execution_ids": [execution.id for execution in api_executions],
        "auto_project_ids": [project.id for project in auto_projects],
        "auto_execution_ids": [execution.id for execution in auto_executions],
        "perf_plan_ids": [plan.id for plan in perf_plans],
        "perf_result_ids": [result.id for result in perf_results],
    }
    requirement_records = [_requirement_item_dict(item) for item in requirement_items]
    document_records = [_document_dict(document) for document in documents]
    test_case_records = [_test_case_dict(case) for case in test_cases]
    round_records = [_model_dict(round_) for round_ in rounds]
    execution_records = [_execution_dict(execution) for execution in executions]
    defect_records = [_defect_dict(defect) for defect in defects]
    api_execution_records = [_api_execution_dict(execution) for execution in api_executions]
    auto_execution_records = [_auto_execution_dict(execution) for execution in auto_executions]
    perf_result_records = [_perf_result_dict(result) for result in perf_results]
    perf_plan_records = [_perf_plan_dict(plan) for plan in perf_plans]
    data_snapshot = {
        "project": _pick(_model_dict(project), ("id", "code", "name", "description", "owner_name", "created_at", "updated_at")),
        "requirements": {
            "summary": {"count": len(requirement_records), "confirmed": sum(1 for item in requirement_records if _norm(item.get("status")) == "confirmed")},
            "items": requirement_records,
        },
        "source_documents": {"summary": {"count": len(document_records)}, "items": document_records},
        "test_cases": {"summary": {"count": len(test_case_records)}, "items": test_case_records},
        "test_rounds": {"summary": {"count": len(round_records)}, "items": round_records},
        "executions": {"summary": {"count": len(execution_records), **_status_summary([item.get("status") for item in execution_records])}, "items": execution_records},
        "defects": {"summary": {"count": len(defect_records), **_status_summary([item.get("status") for item in defect_records])}, "items": defect_records},
        "api": {
            "summary": {
                "libs": len(api_libs),
                "endpoints": len(api_endpoints),
                "test_cases": len(api_test_cases),
                "executions": len(api_execution_records),
                **_status_summary([item.get("status") for item in api_execution_records]),
            },
            "libs": [_pick(_model_dict(lib), ("id", "name", "description", "import_source")) for lib in api_libs],
            "endpoints": [_pick(_model_dict(endpoint), ("id", "lib_id", "requirement_item_id", "name", "method", "path")) for endpoint in api_endpoints],
            "test_cases": [_pick(_model_dict(case), ("id", "endpoint_id", "lib_id", "requirement_item_id", "name", "category", "status")) for case in api_test_cases],
            "executions": api_execution_records,
        },
        "auto": {
            "summary": {"projects": len(auto_projects), "executions": len(auto_execution_records), **_status_summary([item.get("status") for item in auto_execution_records])},
            "projects": [_pick(_model_dict(project), ("id", "name", "type", "language", "framework")) for project in auto_projects],
            "executions": auto_execution_records,
        },
        "perf": {
            "summary": {"plans": len(perf_plan_records), "results": len(perf_result_records)},
            "plans": perf_plan_records,
            "results": perf_result_records,
        },
        "api_executions": api_execution_records,
        "auto_executions": auto_execution_records,
        "performance_results": perf_result_records,
        "performance_plans": perf_plan_records,
    }
    data_snapshot["summary_metrics"] = _summary_metrics(data_snapshot)
    data_snapshot["execution_summary"] = data_snapshot["executions"]["summary"]
    data_snapshot["defect_summary"] = data_snapshot["defects"]["summary"]
    data_snapshot["api_summary"] = data_snapshot["api"]["summary"]
    data_snapshot["automation_summary"] = data_snapshot["auto"]["summary"]
    data_snapshot["performance_summary"] = _performance_summary(perf_results)
    data_snapshot["threshold"] = _performance_threshold_snapshot(perf_results, data_snapshot["performance_summary"])
    data_snapshot["comparison"] = _performance_comparison_snapshot(perf_results, data_snapshot["performance_summary"])
    data_snapshot["perf"]["summary"].update(data_snapshot["performance_summary"])
    data_snapshot["recommendations"] = performance_recommendations(data_snapshot["performance_summary"])
    data_snapshot["risk_items"] = _risk_items(data_snapshot)

    generated_at = _now_iso()
    context = {
        "report_scope": report_scope,
        "scope_snapshot": {
            **report_scope,
            "project": data_snapshot["project"],
            "template": {
                "id": template.id if template else template_id,
                "name": template.name if template else None,
                "version": template.template_version if template else "v1",
                "report_type": template.report_type if template else report_type,
                "sections": [section["key"] for section in template_sections if section.get("enabled", True)],
                "section_configs": template_sections,
                "supported_formats": _formats_from_sections(template_sections),
            },
            "generated_at": generated_at,
        },
        "data_snapshot": data_snapshot,
        "source_refs_json": {
            **source_refs,
            "counts": {key: len(value) for key, value in source_refs.items() if isinstance(value, list)},
        },
    }
    return sanitize_report_payload(context)


def render_markdown_report(title: str, context: dict[str, Any]) -> str:
    data = context["data_snapshot"]
    template = context.get("scope_snapshot", {}).get("template", {})
    sections = _sections_for_format(template.get("section_configs") or template.get("sections") or DEFAULT_REPORT_SECTIONS, "markdown")
    if not sections:
        sections = _sections_for_format(DEFAULT_REPORT_SECTIONS, "markdown")
    lines = [f"# {_md_text(title)}", ""]
    for section in sections:
        block = _render_markdown_section(section["key"], section.get("title") or SECTION_TITLES.get(section["key"], section["key"]), data, context)
        if block:
            lines.extend(block)
            lines.append("")
    return sanitize_report_payload("\n".join(lines).strip() + "\n")


def export_report(report: Report, output_format: str) -> dict[str, Any]:
    fmt = (output_format or "markdown").strip().lower()
    if is_unsupported_export_format(fmt):
        raise UnsupportedFormatError(unsupported_export_detail(fmt, SUPPORTED_REPORT_FORMATS, error_code="unsupported_report_export_format"))
    if fmt not in SUPPORTED_REPORT_FORMATS:
        raise ReportingPayloadError("format must be one of: markdown, html, json, pdf, docx")
    base_name = _safe_filename(report.name or f"report-{report.id}")
    if fmt == "json":
        content = json.dumps(
            sanitize_report_payload(
                {
                    "report": _model_dict(report),
                    "scope_snapshot": report.scope_snapshot or {},
                    "data_snapshot": report.data_snapshot or {},
                    "source_refs_json": report.source_refs_json or {},
                    "source_refs": report.source_refs_json or {},
                }
            ),
            ensure_ascii=False,
            indent=2,
        )
        return {
            "report_id": report.id,
            "filename": f"{base_name}.json",
            "content": content,
            "mime_type": "application/json",
            "format": "json",
        }
    if fmt == "html":
        content = _markdown_to_simple_html(report.content or "")
        return {
            "report_id": report.id,
            "filename": f"{base_name}.html",
            "content": content,
            "mime_type": "text/html; charset=utf-8",
            "format": "html",
        }
    return {
        "report_id": report.id,
        "filename": f"{base_name}.md",
        "content": sanitize_report_payload(report.content or ""),
        "mime_type": "text/markdown; charset=utf-8",
        "format": "markdown",
    }


def normalize_report_template_payload(data: dict[str, Any], existing: ReportTemplate | None = None) -> dict[str, Any]:
    report_type = str(data.get("report_type") or data.get("type") or (existing.report_type if existing else "comprehensive")).strip() or "comprehensive"
    fields: dict[str, Any] = {
        "name": data.get("name") or (existing.name if existing else "Report Template"),
        "report_type": report_type,
        "template_version": str(data.get("template_version") or (existing.template_version if existing else "v1")),
    }
    if "sections" in data or existing is None:
        sections = data.get("sections") if "sections" in data else DEFAULT_REPORT_SECTIONS
        fields["sections"] = normalize_report_sections(sections, strict=True, supported_formats=data.get("supported_formats"))
    elif "supported_formats" in data and existing is not None:
        fields["sections"] = normalize_report_sections(existing.sections, strict=True, supported_formats=data.get("supported_formats"))
    if "is_default" in data:
        fields["is_default"] = bool(data.get("is_default"))
    elif "enabled" in data:
        fields["is_default"] = bool(data.get("enabled"))
    elif existing is None:
        fields["is_default"] = False
    return sanitize_report_payload(fields)


def report_template_public_dict(template: ReportTemplate) -> dict[str, Any]:
    sections = normalize_report_sections(template.sections or [], strict=False)
    formats = _formats_from_sections(sections)
    return sanitize_report_payload(
        {
            "id": template.id,
            "name": template.name,
            "report_type": template.report_type,
            "type": template.report_type,
            "sections": [section["key"] for section in sections if section.get("enabled", True)],
            "section_configs": sections,
            "supported_formats": formats,
            "is_default": template.is_default,
            "enabled": template.is_default,
            "template_version": template.template_version,
            "created_at": template.created_at.isoformat() if hasattr(template.created_at, "isoformat") else template.created_at,
            "updated_at": template.updated_at.isoformat() if hasattr(template.updated_at, "isoformat") else template.updated_at,
        }
    )


def enforce_single_default_template(session: Session, template: ReportTemplate) -> None:
    if not template.is_default:
        return
    for other in session.scalars(
        select(ReportTemplate).where(ReportTemplate.report_type == template.report_type, ReportTemplate.id != template.id)
    ):
        other.is_default = False


def normalize_report_sections(sections: Any, *, strict: bool = True, supported_formats: Any = None) -> list[dict[str, Any]]:
    raw_sections = DEFAULT_REPORT_SECTIONS if sections in (None, "") else sections
    if not isinstance(raw_sections, list):
        raise ReportingPayloadError("sections must be a list")
    normalized: list[dict[str, Any]] = []
    seen_orders: set[int] = set()
    seen_keys: set[str] = set()
    top_level_formats = _normalize_supported_formats(supported_formats, strict=strict) if supported_formats is not None else None
    for index, raw in enumerate(raw_sections):
        if isinstance(raw, str):
            key = _canonical_section_key(raw)
            title = SECTION_TITLES.get(key, raw.strip() or key)
            enabled = True
            order = index
            section_formats = top_level_formats or sorted(SUPPORTED_REPORT_FORMATS)
        elif isinstance(raw, dict):
            explicit_key = raw.get("key") or raw.get("id") or raw.get("type") or raw.get("name") or raw.get("section")
            key = _canonical_section_key(explicit_key or (DEFAULT_REPORT_SECTIONS[index] if index < len(DEFAULT_REPORT_SECTIONS) else f"section_{index + 1}"))
            title = str(raw.get("title") or SECTION_TITLES.get(key, key)).strip() or key
            enabled_value = raw.get("enabled", True)
            if not isinstance(enabled_value, bool):
                raise ReportingPayloadError("sections[].enabled must be boolean")
            enabled = enabled_value
            try:
                order = int(raw.get("order", index))
            except (TypeError, ValueError) as exc:
                raise ReportingPayloadError("sections[].order must be an integer") from exc
            section_formats = top_level_formats or _normalize_supported_formats(raw.get("supported_formats") or raw.get("formats"), strict=strict)
        else:
            raise ReportingPayloadError("sections items must be strings or objects")
        if order in seen_orders:
            raise ReportingPayloadError("sections[].order must be unique")
        if key in seen_keys and strict:
            raise ReportingPayloadError("sections[].key must be unique")
        seen_orders.add(order)
        seen_keys.add(key)
        normalized.append(
            {
                "key": key,
                "title": title,
                "order": order,
                "enabled": enabled,
                "supported_formats": section_formats,
            }
        )
    return sorted(normalized, key=lambda item: (item["order"], item["key"]))


def report_drilldown(report: Report, section: str) -> dict[str, Any]:
    data = report.data_snapshot or {}
    source_refs = report.source_refs_json or {}
    if not section:
        payload: dict[str, Any] = {
            "report_id": report.id,
            "snapshot_generated_at": (report.scope_snapshot or {}).get("generated_at"),
            "snapshot_based": True,
            "scope_snapshot": report.scope_snapshot or {},
        }
        for key in ("requirements", "executions", "defects", "api", "automation", "performance", "risks"):
            payload[key] = _drilldown_payload(key, data, source_refs)
        return sanitize_report_payload(payload)
    key = _canonical_section_key(section or "overview")
    payload = _drilldown_payload(key, data, source_refs)
    return sanitize_report_payload(
        {
            "report_id": report.id,
            "section": key,
            "snapshot_generated_at": (report.scope_snapshot or {}).get("generated_at"),
            "scope_snapshot": report.scope_snapshot or {},
            "summary": payload.get("summary") or {},
            "items": payload.get("items") or [],
            "groups": payload.get("groups") or {},
            "source_refs": payload.get("source_refs") or source_refs,
            "empty": _is_empty_drilldown(payload),
            "snapshot_based": True,
        }
    )


def report_risks_payload(report: Report) -> dict[str, Any]:
    risks = _normalized_report_risks(report)
    return sanitize_report_payload({"report_id": report.id, "risks": risks, "total": len(risks), "source_refs": report.source_refs_json or {}})


def create_todo_from_report_risk(session: Session, report: Report, risk_key: str, data: dict[str, Any] | None = None) -> tuple[ReportTodo, bool]:
    risk = _find_report_risk(report, risk_key)
    if risk is None:
        raise ReportingPayloadError(f"risk({risk_key}) not found in report snapshot")
    existing = session.scalar(select(ReportTodo).where(ReportTodo.report_id == report.id, ReportTodo.risk_key == risk["risk_key"]).limit(1))
    if existing is not None:
        _sync_report_todos_snapshot(report, [existing])
        return existing, False
    data = data or {}
    source_refs = {**(risk.get("source_refs") or {})}
    if isinstance(data.get("source_refs"), dict):
        source_refs.update(data["source_refs"])
    status = str(data.get("status") or "todo").strip().lower()
    if status not in TODO_STATUSES:
        status = "todo"
    todo = ReportTodo(
        project_id=report.project_id,
        report_id=report.id,
        risk_key=risk["risk_key"],
        title=str(data.get("title") or risk.get("title") or risk["risk_key"])[:255],
        detail=str(data.get("detail") or data.get("note") or risk.get("detail") or ""),
        status=status,
        source_refs_json=sanitize_report_payload(source_refs),
        risk_snapshot=sanitize_report_payload(risk),
        assignee=sanitize_report_payload(data.get("assignee") or data.get("owner")),
        due_at=sanitize_report_payload(data.get("due_at") or data.get("dueAt")),
    )
    session.add(todo)
    session.flush()
    _sync_report_todos_snapshot(report, [todo])
    session.add(OperationLog(module="report", action="risk_to_todo", target_type="report_todo", target_id=todo.id, detail={"report_id": report.id, "risk_key": todo.risk_key}))
    return todo, True


def update_report_todo(todo: ReportTodo, data: dict[str, Any]) -> ReportTodo:
    if "status" in data:
        status = str(data.get("status") or "").strip().lower()
        if status not in TODO_STATUSES:
            raise ReportingPayloadError(f"status must be one of: {', '.join(sorted(TODO_STATUSES))}")
        todo.status = status
    for field in ("title", "detail", "assignee", "due_at"):
        if field in data:
            value = data.get(field)
            setattr(todo, field, sanitize_report_payload(str(value)) if value is not None else None)
    return todo


def _canonical_section_key(value: Any, *, strict: bool = True) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = SECTION_ALIASES.get(key, key)
    if key in SECTION_TITLES:
        return key
    if strict:
        raise ReportingPayloadError(f"sections contains unsupported section: {value}")
    return key


def _normalize_supported_formats(value: Any, *, strict: bool) -> list[str]:
    if value in (None, ""):
        return sorted(SUPPORTED_REPORT_FORMATS)
    raw_values = value if isinstance(value, list) else str(value).split(",")
    formats: list[str] = []
    for raw in raw_values:
        fmt = str(raw or "").strip().lower()
        if not fmt:
            continue
        if fmt not in SUPPORTED_REPORT_FORMATS:
            if strict:
                raise ReportingPayloadError(f"supported_formats contains unsupported format: {fmt}")
            continue
        if fmt not in formats:
            formats.append(fmt)
    return formats or sorted(SUPPORTED_REPORT_FORMATS)


def _formats_from_sections(sections: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    for section in sections:
        for fmt in section.get("supported_formats") or []:
            if fmt in SUPPORTED_REPORT_FORMATS:
                seen.add(fmt)
    preferred = ["markdown", "html", "json"]
    return [fmt for fmt in preferred if fmt in seen] or preferred


def _sections_for_format(sections: Any, output_format: str) -> list[dict[str, Any]]:
    fmt = (output_format or "markdown").strip().lower()
    normalized = normalize_report_sections(sections or DEFAULT_REPORT_SECTIONS, strict=False)
    return [section for section in normalized if section.get("enabled", True) and fmt in set(section.get("supported_formats") or [])]


def _render_markdown_section(title_key: str, title: str, data: dict[str, Any], context: dict[str, Any]) -> list[str]:
    key = _canonical_section_key(title_key, strict=False)
    heading = [f"## {_md_text(title)}"]
    if key == "overview":
        project = data.get("project") or {}
        scope = context.get("report_scope") or context.get("scope_snapshot") or {}
        return heading + _markdown_table(
            ["Field", "Value"],
            [
                ["Project", f"{project.get('name') or ''} (ID: {project.get('id') or scope.get('project_id') or ''})"],
                ["Generated At", (context.get("scope_snapshot") or {}).get("generated_at") or ""],
                ["Requirement Items", ", ".join(map(str, scope.get("requirement_item_ids") or []))],
                ["Source Documents", ", ".join(map(str, scope.get("source_document_ids") or []))],
                ["Modules", ", ".join(map(str, scope.get("module_types") or []))],
            ],
        )
    if key == "metrics":
        metrics = data.get("summary_metrics") or {}
        return heading + _markdown_table(["Metric", "Value"], [[name, value] for name, value in metrics.items()])
    if key == "requirements":
        return heading + _markdown_table(
            ["ID", "Title", "Status", "Priority", "Module"],
            [[item.get("id"), item.get("title"), item.get("status"), item.get("priority"), item.get("module")] for item in _items(data, "requirements")],
        )
    if key == "source_documents":
        return heading + _markdown_table(
            ["ID", "Name", "Type", "Status", "Version"],
            [[item.get("id"), item.get("name"), item.get("source_type"), item.get("parser_status"), item.get("version")] for item in _items(data, "source_documents")],
        )
    if key == "test_cases":
        return heading + _markdown_table(
            ["ID", "Title", "Type", "Status", "Requirement"],
            [[item.get("id"), item.get("title"), item.get("case_type"), item.get("status"), item.get("requirement_item_id")] for item in _items(data, "test_cases")],
        )
    if key == "test_rounds":
        return heading + _markdown_table(
            ["ID", "Name", "Status", "Total", "Passed", "Failed"],
            [[item.get("id"), item.get("name"), item.get("status"), item.get("total_count"), item.get("pass_count"), item.get("fail_count")] for item in _items(data, "test_rounds")],
        )
    if key == "executions":
        return heading + _markdown_table(
            ["ID", "Case", "Requirement", "Status", "Actual Result"],
            [[item.get("id"), item.get("case_id"), item.get("requirement_item_id"), item.get("status"), item.get("actual_result")] for item in _items(data, "executions")],
        )
    if key == "defects":
        return heading + _markdown_table(
            ["ID", "Number", "Title", "Severity", "Status"],
            [[item.get("id"), item.get("defect_number"), item.get("title"), item.get("severity"), item.get("status")] for item in _items(data, "defects")],
        )
    if key == "api":
        api = data.get("api") if isinstance(data.get("api"), dict) else {}
        rows = []
        rows.extend([["Endpoint", item.get("id"), item.get("method"), item.get("path"), item.get("name")] for item in api.get("endpoints") or []])
        rows.extend([["Execution", item.get("id"), item.get("status"), item.get("duration_ms"), item.get("error_message")] for item in api.get("executions") or []])
        return heading + _markdown_table(["Type", "ID", "Status/Method", "Detail", "Name/Error"], rows)
    if key == "automation":
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        rows = []
        rows.extend([["Project", item.get("id"), item.get("name"), item.get("framework"), item.get("language")] for item in auto.get("projects") or []])
        rows.extend([["Execution", item.get("id"), item.get("status"), item.get("duration_ms"), item.get("summary")] for item in auto.get("executions") or []])
        return heading + _markdown_table(["Type", "ID", "Name/Status", "Framework/Duration", "Detail"], rows)
    if key == "performance":
        perf = data.get("perf") if isinstance(data.get("perf"), dict) else {}
        rows = []
        rows.extend([["Plan", item.get("id"), item.get("name"), item.get("status"), item.get("requirement_item_ids_json")] for item in perf.get("plans") or []])
        rows.extend([["Result", item.get("id"), item.get("status"), item.get("duration"), (item.get("summary_data") or {}).get("p95_ms")] for item in perf.get("results") or []])
        return heading + _markdown_table(["Type", "ID", "Name/Status", "Status/Duration", "Requirement/P95"], rows)
    if key == "risks":
        risks = _ensure_risk_keys(data.get("risk_items") or [], {})
        return heading + _markdown_table(
            ["Risk Key", "Level", "Title", "Detail"],
            [[item.get("risk_key"), item.get("level"), _risk_title_for_render(item.get("title")), item.get("detail")] for item in risks],
        )
    if key == "todos":
        return heading + _markdown_table(
            ["ID", "Risk Key", "Status", "Title"],
            [[item.get("id"), item.get("risk_key"), item.get("status"), item.get("title")] for item in _items(data, "todos")],
        )
    if key == "recommendations":
        return heading + _markdown_table(
            ["Priority", "Title", "Action"],
            [[item.get("priority"), item.get("title"), item.get("action")] for item in data.get("recommendations") or []],
        )
    if key == "evidence":
        refs = context.get("source_refs_json") or data.get("source_refs") or {}
        return heading + _markdown_table(["Reference", "IDs"], [[name, value] for name, value in refs.items() if name != "counts"])
    if key == "conclusion":
        return heading + ["", _brief_conclusion(data.get("summary_metrics") or {}, data.get("risk_items") or [], "report")]
    return []


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["", "_No data in this snapshot._"]
    result = [
        "",
        "| " + " | ".join(_md_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows[:50]:
        padded = list(row)[: len(headers)] + [""] * max(0, len(headers) - len(row))
        result.append("| " + " | ".join(_md_cell(value) for value in padded[: len(headers)]) + " |")
    return result


def _md_text(value: Any) -> str:
    return str(sanitize_report_payload(value if value is not None else "")).replace("\r", " ").replace("\n", " ")


def _md_cell(value: Any) -> str:
    text = _md_text(json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else value)
    return text.replace("|", "\\|")


def _risk_title_for_render(value: Any) -> str:
    text = str(value or "")
    return text.replace("Performance ", "").replace("performance ", "")


def _items(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _drilldown_payload(key: str, data: dict[str, Any], source_refs: dict[str, Any]) -> dict[str, Any]:
    if key in {"requirements", "source_documents", "test_cases", "test_rounds", "executions", "defects", "todos"}:
        value = data.get(key) if isinstance(data.get(key), dict) else {}
        return {"summary": value.get("summary") or {}, "items": value.get("items") or [], "source_refs": source_refs}
    if key == "api":
        api = data.get("api") if isinstance(data.get("api"), dict) else {}
        return {"summary": api.get("summary") or {}, "items": api.get("executions") or [], "groups": api, "source_refs": source_refs}
    if key == "automation":
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        return {"summary": auto.get("summary") or {}, "items": auto.get("executions") or [], "groups": auto, "source_refs": source_refs}
    if key == "performance":
        perf = data.get("perf") if isinstance(data.get("perf"), dict) else {}
        return {"summary": {**(perf.get("summary") or {}), **(data.get("performance_summary") or {})}, "items": perf.get("results") or [], "groups": perf, "source_refs": source_refs}
    if key == "risks":
        risks = _ensure_risk_keys(data.get("risk_items") or [], source_refs)
        return {"summary": {"count": len(risks)}, "items": risks, "source_refs": source_refs}
    return {"summary": data.get("summary_metrics") or {}, "items": [], "groups": data, "source_refs": source_refs}


def _is_empty_drilldown(payload: dict[str, Any]) -> bool:
    return not bool(payload.get("items") or payload.get("groups") or payload.get("summary"))


def _normalized_report_risks(report: Report) -> list[dict[str, Any]]:
    return _ensure_risk_keys((report.data_snapshot or {}).get("risk_items") or [], report.source_refs_json or {})


def _ensure_risk_keys(risks: list[Any], source_refs: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(risks):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        source = str(item.get("source") or "risk")
        title = str(item.get("title") or source)
        risk_key = str(item.get("risk_key") or item.get("key") or item.get("id") or _risk_key(source, title, index))
        item["risk_key"] = risk_key
        item.setdefault("key", risk_key)
        item.setdefault("source_refs", _risk_source_refs(source, source_refs))
        normalized.append(item)
    return sanitize_report_payload(normalized)


def _find_report_risk(report: Report, risk_key: str) -> dict[str, Any] | None:
    for risk in _normalized_report_risks(report):
        if risk.get("risk_key") == risk_key or risk.get("key") == risk_key:
            return risk
    return None


def _risk_key(source: str, title: str, index: int) -> str:
    digest = hashlib.sha1(f"{source}:{title}:{index}".encode("utf-8")).hexdigest()[:10]
    return f"{source}-{digest}"


def _risk_source_refs(source: str, source_refs: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "defect": ("defect_ids",),
        "execution": ("execution_ids",),
        "api_execution": ("api_execution_ids", "api_endpoint_ids"),
        "auto_execution": ("auto_execution_ids", "auto_project_ids"),
        "performance": ("perf_result_ids", "perf_plan_ids"),
        "summary": ("project_id",),
    }
    result: dict[str, Any] = {"source": source}
    for key in mapping.get(source, ()):
        if key in source_refs:
            result[key] = source_refs[key]
    return result


def _todo_public_dict(todo: ReportTodo) -> dict[str, Any]:
    data = _model_dict(todo)
    data["todo_id"] = todo.id
    data["source_refs"] = data.get("source_refs_json") or {}
    return sanitize_report_payload(data)


def _sync_report_todos_snapshot(report: Report, todos: list[ReportTodo]) -> None:
    snapshot = dict(report.data_snapshot or {})
    existing = _items(snapshot, "todos")
    by_id = {str(item.get("id")): item for item in existing if item.get("id") is not None}
    for todo in todos:
        by_id[str(todo.id)] = _todo_public_dict(todo)
    items = list(by_id.values())
    snapshot["todos"] = {"summary": {"count": len(items)}, "items": items}
    report.data_snapshot = sanitize_report_payload(snapshot)
    context = {
        "scope_snapshot": report.scope_snapshot or {},
        "report_scope": report.related_scope_json or report.scope_snapshot or {},
        "data_snapshot": report.data_snapshot,
        "source_refs_json": report.source_refs_json or {},
        "report_id": report.id,
    }
    report.content = render_markdown_report(report.name, context)


def _select_report_template(session: Session, report_type: str, template_id: int | None) -> ReportTemplate | None:
    if template_id is not None:
        template = session.get(ReportTemplate, template_id)
        if template is None:
            raise ReportingPayloadError(f"ReportTemplate({template_id}) not found")
        return template
    return session.scalar(
        select(ReportTemplate)
        .where(ReportTemplate.report_type == report_type, ReportTemplate.is_default.is_(True))
        .order_by(ReportTemplate.id.desc())
        .limit(1)
    )


def _normalize_module_types(values: list[str] | None) -> list[str]:
    if not values:
        return list(DEFAULT_MODULE_TYPES)
    result: list[str] = []
    for raw in values:
        key = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        module = MODULE_ALIASES.get(key)
        if module is None:
            raise ReportingPayloadError(f"module_types contains unsupported module: {raw}")
        if module not in result:
            result.append(module)
    return result or list(DEFAULT_MODULE_TYPES)


def _normalize_time_range(value: dict[str, Any] | None) -> tuple[datetime | None, datetime | None, dict[str, Any] | None]:
    if not isinstance(value, dict) or not value:
        return None, None, None
    start_at = _parse_datetime(value.get("from") or value.get("start") or value.get("dateFrom") or value.get("start_at"))
    end_at = _parse_datetime(value.get("to") or value.get("end") or value.get("dateTo") or value.get("end_at"), end_of_day=True)
    if start_at and end_at and start_at > end_at:
        raise ReportingPayloadError("time_range start must be before end")
    normalized = {
        "from": start_at.isoformat() if start_at else None,
        "to": end_at.isoformat() if end_at else None,
    }
    return start_at, end_at, normalized


def _parse_datetime(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        if len(text) == 10:
            suffix = "T23:59:59.999999+00:00" if end_of_day else "T00:00:00+00:00"
            return datetime.fromisoformat(text + suffix)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportingPayloadError("time_range contains invalid datetime") from exc


def _apply_created_range(stmt: Any, model: type[Any], start_at: datetime | None, end_at: datetime | None) -> Any:
    column = getattr(model, "created_at", None)
    if column is None:
        return stmt
    return _apply_datetime_range(stmt, column, start_at, end_at)


def _apply_datetime_range(stmt: Any, column: Any, start_at: datetime | None, end_at: datetime | None) -> Any:
    if start_at is not None:
        stmt = stmt.where(column >= start_at)
    if end_at is not None:
        stmt = stmt.where(column <= end_at)
    return stmt


def _require_documents(session: Session, project_id: int, document_ids: list[int]) -> list[RequirementDocument]:
    if not document_ids:
        return []
    documents = list(
        session.scalars(
            select(RequirementDocument).where(
                RequirementDocument.project_id == project_id,
                RequirementDocument.id.in_(document_ids),
                RequirementDocument.is_deleted.is_(False),
            )
        )
    )
    if {document.id for document in documents} != set(document_ids):
        raise ReportingPayloadError("source_document_ids must belong to the selected project")
    return documents


def _documents_for_scope(
    session: Session,
    project_id: int,
    items: list[RequirementItem],
    requested_documents: list[RequirementDocument],
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[RequirementDocument]:
    if requested_documents:
        documents = requested_documents
    else:
        document_ids = sorted({item.document_id for item in items if item.document_id is not None})
        if not document_ids:
            return []
        stmt = select(RequirementDocument).where(
            RequirementDocument.project_id == project_id,
            RequirementDocument.id.in_(document_ids),
            RequirementDocument.is_deleted.is_(False),
        )
        documents = list(session.scalars(_apply_created_range(stmt, RequirementDocument, start_at, end_at).order_by(RequirementDocument.id)))
    return documents


def _test_cases(session: Session, project_id: int, item_ids: list[int], start_at: datetime | None, end_at: datetime | None) -> list[TestCase]:
    stmt = select(TestCase).where(TestCase.project_id == project_id, TestCase.is_deleted.is_(False))
    if item_ids:
        stmt = stmt.where(TestCase.requirement_item_id.in_(item_ids))
    stmt = _apply_created_range(stmt, TestCase, start_at, end_at)
    return list(session.scalars(stmt.order_by(TestCase.id)))


def _executions(session: Session, project_id: int, item_ids: list[int], start_at: datetime | None, end_at: datetime | None) -> list[Execution]:
    stmt = select(Execution).where(Execution.project_id == project_id)
    if item_ids:
        stmt = stmt.where(Execution.requirement_item_id.in_(item_ids))
    stmt = _apply_datetime_range(stmt, Execution.executed_at, start_at, end_at)
    return list(session.scalars(stmt.order_by(Execution.executed_at.desc(), Execution.id.desc())))


def _defects(session: Session, project_id: int, item_ids: list[int], start_at: datetime | None, end_at: datetime | None) -> list[Defect]:
    stmt = select(Defect).where(Defect.project_id == project_id)
    if item_ids:
        stmt = stmt.where(Defect.requirement_item_id.in_(item_ids))
    stmt = _apply_created_range(stmt, Defect, start_at, end_at)
    return list(session.scalars(stmt.order_by(Defect.id.desc())))


def _test_rounds(session: Session, project_id: int, item_ids: list[int], start_at: datetime | None, end_at: datetime | None) -> list[TestRound]:
    stmt = select(TestRound).where(TestRound.project_id == project_id)
    if item_ids:
        stmt = stmt.where(TestRound.requirement_item_id.in_(item_ids))
    stmt = _apply_created_range(stmt, TestRound, start_at, end_at)
    return list(session.scalars(stmt.order_by(TestRound.id.desc())))


def _api_executions(
    session: Session,
    project_id: int,
    item_ids: list[int],
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[ApiExecution]:
    stmt = (
        select(ApiExecution)
        .join(ApiTestLib, ApiTestLib.id == ApiExecution.lib_id)
        .where(ApiTestLib.project_id == project_id, ApiTestLib.is_deleted.is_(False))
    )
    if item_ids:
        stmt = (
            stmt.outerjoin(ApiTestCase, ApiTestCase.id == ApiExecution.case_id)
            .outerjoin(ApiEndpoint, ApiEndpoint.id == ApiExecution.endpoint_id)
            .where((ApiTestCase.requirement_item_id.in_(item_ids)) | (ApiEndpoint.requirement_item_id.in_(item_ids)))
        )
    stmt = _apply_datetime_range(stmt, ApiExecution.executed_at, start_at, end_at)
    return list(session.scalars(stmt.order_by(ApiExecution.executed_at.desc(), ApiExecution.id.desc())))


def _api_facts(
    session: Session,
    project_id: int,
    item_ids: list[int],
    document_ids: list[int],
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[list[ApiTestLib], list[ApiEndpoint], list[ApiTestCase], list[ApiExecution]]:
    lib_stmt = select(ApiTestLib).where(ApiTestLib.project_id == project_id, ApiTestLib.is_deleted.is_(False))
    if document_ids:
        lib_stmt = lib_stmt.where(ApiTestLib.source_document_id.in_(document_ids))
    lib_stmt = _apply_created_range(lib_stmt, ApiTestLib, start_at, end_at)
    libs = list(session.scalars(lib_stmt.order_by(ApiTestLib.id.desc())))
    lib_ids = [lib.id for lib in libs]
    if not lib_ids:
        return [], [], [], []
    endpoint_stmt = select(ApiEndpoint).where(ApiEndpoint.lib_id.in_(lib_ids), ApiEndpoint.is_deleted.is_(False))
    case_stmt = select(ApiTestCase).where(ApiTestCase.lib_id.in_(lib_ids), ApiTestCase.is_deleted.is_(False))
    if item_ids:
        endpoint_stmt = endpoint_stmt.where(ApiEndpoint.requirement_item_id.in_(item_ids))
        case_stmt = case_stmt.where(ApiTestCase.requirement_item_id.in_(item_ids))
    endpoint_stmt = _apply_created_range(endpoint_stmt, ApiEndpoint, start_at, end_at)
    case_stmt = _apply_created_range(case_stmt, ApiTestCase, start_at, end_at)
    endpoints = list(session.scalars(endpoint_stmt.order_by(ApiEndpoint.id.desc())))
    cases = list(session.scalars(case_stmt.order_by(ApiTestCase.id.desc())))
    executions = _api_executions(session, project_id, item_ids, start_at, end_at)
    return libs, endpoints, cases, executions


def _auto_facts(session: Session, project_id: int, start_at: datetime | None, end_at: datetime | None) -> tuple[list[AutoProject], list[AutoExecution]]:
    project_stmt = select(AutoProject).where(AutoProject.project_id == project_id, AutoProject.is_deleted.is_(False))
    project_stmt = _apply_created_range(project_stmt, AutoProject, start_at, end_at)
    projects = list(session.scalars(project_stmt.order_by(AutoProject.id.desc())))
    stmt = (
        select(AutoExecution)
        .join(AutoProject, AutoProject.id == AutoExecution.auto_project_id)
        .where(AutoProject.project_id == project_id, AutoProject.is_deleted.is_(False))
    )
    stmt = _apply_datetime_range(stmt, AutoExecution.executed_at, start_at, end_at)
    return projects, list(session.scalars(stmt.order_by(AutoExecution.executed_at.desc(), AutoExecution.id.desc())))


def _perf_facts(
    session: Session,
    project_id: int,
    item_ids: list[int],
    document_ids: list[int],
    perf_plan_id: int | None,
    perf_result_id: int | None,
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[list[PerfPlan], list[PerfResult]]:
    plan_stmt = select(PerfPlan).where(PerfPlan.project_id == project_id, PerfPlan.is_deleted.is_(False))
    if perf_plan_id is not None:
        plan_stmt = plan_stmt.where(PerfPlan.id == perf_plan_id)
    if document_ids:
        plan_stmt = plan_stmt.where(PerfPlan.source_document_id.in_(document_ids))
    plan_stmt = _apply_created_range(plan_stmt, PerfPlan, start_at, end_at)
    plans = list(session.scalars(plan_stmt.order_by(PerfPlan.id.desc())))
    if item_ids and perf_plan_id is None:
        item_set = set(item_ids)
        plans = [plan for plan in plans if item_set.intersection(set(plan.requirement_item_ids_json or []))]
    plan_ids = [plan.id for plan in plans]
    if not plan_ids:
        return plans, []
    result_stmt = select(PerfResult).where(PerfResult.project_id == project_id, PerfResult.plan_id.in_(plan_ids))
    if perf_result_id is not None:
        result_stmt = result_stmt.where(PerfResult.id == perf_result_id)
    result_stmt = _apply_datetime_range(result_stmt, PerfResult.executed_at, start_at, end_at)
    results = list(session.scalars(result_stmt.order_by(PerfResult.executed_at.desc(), PerfResult.id.desc())))
    return plans, results


def _summary_metrics(data: dict[str, Any]) -> dict[str, Any]:
    executions = data["executions"]["items"]
    api_executions = data["api"]["executions"]
    auto_executions = data["auto"]["executions"]
    defects = data["defects"]["items"]
    return {
        "requirement_item_count": len(data["requirements"]["items"]),
        "source_document_count": len(data["source_documents"]["items"]),
        "test_case_count": len(data["test_cases"]["items"]),
        "test_round_count": len(data["test_rounds"]["items"]),
        "execution_count": len(executions),
        "execution_pass_rate": _pass_rate([item.get("status") for item in executions]),
        "defect_count": len(defects),
        "open_defect_count": sum(1 for item in defects if _norm(item.get("status")) in OPEN_DEFECT_STATUSES),
        "api_execution_count": len(api_executions),
        "api_pass_rate": _pass_rate([item.get("status") for item in api_executions]),
        "auto_execution_count": len(auto_executions),
        "auto_pass_rate": _pass_rate([item.get("status") for item in auto_executions]),
        "perf_result_count": len(data["perf"]["results"]),
    }


def _performance_summary(results: list[PerfResult]) -> dict[str, Any]:
    return build_performance_summary(results)


def _performance_threshold_snapshot(results: list[PerfResult], performance_summary: dict[str, Any]) -> dict[str, Any]:
    latest_summary = results[0].summary_data or {} if results else {}
    threshold_results = latest_summary.get("threshold_results")
    if threshold_results is None:
        threshold_results = performance_summary.get("threshold_violations") or []
    violation_count = latest_summary.get("threshold_violation_count")
    if violation_count is None:
        violation_count = len(performance_summary.get("threshold_violations") or [])
    return {
        "latest_result_id": performance_summary.get("latest_result_id"),
        "status": latest_summary.get("threshold_status") or performance_summary.get("threshold_status") or "not_configured",
        "results": threshold_results,
        "violation_count": violation_count,
    }


def _performance_comparison_snapshot(results: list[PerfResult], performance_summary: dict[str, Any]) -> dict[str, Any]:
    latest_summary = results[0].summary_data or {} if results else {}
    comparison = latest_summary.get("comparison")
    if isinstance(comparison, dict) and comparison:
        return {
            **comparison,
            "current_result_id": comparison.get("current_result_id") or performance_summary.get("latest_result_id"),
            "baseline_result_id": comparison.get("baseline_result_id") or performance_summary.get("history_baseline_result_id"),
        }
    return {
        "current_result_id": performance_summary.get("latest_result_id"),
        "baseline_result_id": performance_summary.get("history_baseline_result_id"),
        "delta": performance_summary.get("history_delta") or {},
        "regressions": performance_summary.get("history_regressions") or [],
    }


def _risk_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    metrics = data["summary_metrics"]
    if metrics["open_defect_count"]:
        risks.append(
            {
                "level": "high",
                "title": "存在未关闭缺陷",
                "detail": f"当前范围仍有 {metrics['open_defect_count']} 个未关闭缺陷。",
                "source": "defect",
            }
        )
    failed_executions = sum(1 for item in data["executions"]["items"] if _norm(item.get("status")) in FAIL_STATUSES)
    if failed_executions:
        risks.append(
            {
                "level": "medium",
                "title": "存在失败执行记录",
                "detail": f"当前范围有 {failed_executions} 条失败或错误的主链执行记录。",
                "source": "execution",
            }
        )
    api_failed = sum(1 for item in data["api"]["executions"] if _norm(item.get("status")) in FAIL_STATUSES)
    if api_failed:
        risks.append(
            {
                "level": "medium",
                "title": "接口执行存在失败",
                "detail": f"接口执行失败/错误 {api_failed} 次，需要回看请求与响应快照。",
                "source": "api_execution",
            }
        )
    auto_failed = sum(1 for item in data["auto"]["executions"] if _norm(item.get("status")) in FAIL_STATUSES)
    if auto_failed:
        risks.append(
            {
                "level": "medium",
                "title": "自动化执行存在失败",
                "detail": f"自动化执行失败/错误 {auto_failed} 次，需要查看日志与 artifacts。",
                "source": "auto_execution",
            }
        )
    perf = data["performance_summary"]
    if _norm(perf.get("latest_status")) in FAIL_STATUSES:
        risks.append(
            {
                "level": "high",
                "title": "最新性能结果异常",
                "detail": f"最新性能结果状态为 {perf.get('latest_status')}。",
                "source": "performance",
            }
        )
    risks.extend(performance_risk_items(perf))
    if not risks:
        risks.append({"level": "low", "title": "暂无高风险事实", "detail": "当前快照未发现失败执行或未关闭缺陷。", "source": "summary"})
    return risks


def _brief_conclusion(metrics: dict[str, Any], risk_items: list[dict[str, Any]], conclusion_type: str) -> str:
    has_high_risk = any(item.get("level") == "high" for item in risk_items)
    if metrics.get("test_case_count", 0) == 0 and metrics.get("execution_count", 0) == 0:
        return "当前项目已有范围数据较少，暂无法形成充分测试结论；建议先补充用例、执行记录和缺陷状态后再判断。"
    if has_high_risk:
        return (
            "当前测试范围存在需优先处理的风险，不建议直接给出放行结论。"
            f"用例 {metrics.get('test_case_count', 0)} 条，执行 {metrics.get('execution_count', 0)} 条，"
            f"未关闭缺陷 {metrics.get('open_defect_count', 0)} 个。"
        )
    return (
        "当前测试范围整体风险可控，可继续推进后续验证或同步。"
        f"用例 {metrics.get('test_case_count', 0)} 条，执行通过率 {metrics.get('execution_pass_rate', 0)}%，"
        f"接口通过率 {metrics.get('api_pass_rate', 0)}%，未关闭缺陷 {metrics.get('open_defect_count', 0)} 个。"
    )


def _lightweight_name(conclusion_type: str) -> str:
    mapping = {
        "daily": "测试日报",
        "smoke": "提测反馈",
        "release": "上线建议",
        "risk": "风险清单",
        "brief": "轻量测试结论",
    }
    return mapping.get(conclusion_type, "轻量测试结论")


def _model_dict(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[column.name] = value
    return sanitize_report_payload(data)


def _requirement_item_dict(item: RequirementItem) -> dict[str, Any]:
    return _pick(
        _model_dict(item),
        (
            "id",
            "item_number",
            "title",
            "summary",
            "module",
            "priority",
            "status",
            "case_status",
            "document_id",
            "version",
        ),
    )


def _document_dict(document: RequirementDocument) -> dict[str, Any]:
    return _pick(_model_dict(document), ("id", "document_number", "name", "source_type", "parser_status", "version", "created_at"))


def _test_case_dict(case: TestCase) -> dict[str, Any]:
    return _pick(
        _model_dict(case),
        (
            "id",
            "case_number",
            "title",
            "case_type",
            "priority",
            "status",
            "requirement_item_id",
            "test_point_id",
            "version",
        ),
    )


def _execution_dict(execution: Execution) -> dict[str, Any]:
    return _pick(
        _model_dict(execution),
        (
            "id",
            "case_id",
            "round_id",
            "requirement_item_id",
            "executor_type",
            "status",
            "actual_result",
            "block_reason",
            "skip_reason",
            "execution_time",
            "artifact_summary_json",
            "executed_at",
        ),
    )


def _defect_dict(defect: Defect) -> dict[str, Any]:
    return _pick(_model_dict(defect), ("id", "defect_number", "title", "severity", "status", "case_id", "requirement_item_id", "actual_result", "remark"))


def _api_execution_dict(execution: ApiExecution) -> dict[str, Any]:
    return _pick(
        _model_dict(execution),
        (
            "id",
            "lib_id",
            "endpoint_id",
            "case_id",
            "scenario_id",
            "schedule_id",
            "run_type",
            "status",
            "response_snapshot",
            "assertion_results",
            "duration_ms",
            "error_message",
            "executed_at",
        ),
    )


def _auto_execution_dict(execution: AutoExecution) -> dict[str, Any]:
    return _pick(_model_dict(execution), ("id", "auto_project_id", "status", "summary", "artifacts", "log_excerpt", "duration_ms", "executed_at"))


def _perf_result_dict(result: PerfResult) -> dict[str, Any]:
    return _pick(_model_dict(result), ("id", "plan_id", "status", "summary_data", "timeline_data", "error_details", "artifacts", "duration", "executed_at"))


def _perf_plan_dict(plan: PerfPlan) -> dict[str, Any]:
    return _pick(
        _model_dict(plan),
        (
            "id",
            "name",
            "description",
            "requirement_item_ids_json",
            "target_assets_json",
            "plan_schema",
            "status",
            "created_at",
            "updated_at",
        ),
    )


def _pick(data: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    return {key: data.get(key) for key in keys}


def _status_summary(statuses: Iterable[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for status in statuses:
        key = str(status or "unknown")
        result[key] = result.get(key, 0) + 1
    return result


def _pass_rate(statuses: Iterable[Any]) -> float:
    values = [_norm(status) for status in statuses]
    if not values:
        return 0.0
    passed = sum(1 for status in values if status in SUCCESS_STATUSES)
    return round(passed * 100 / len(values), 2)


def _require_active(session: Session, model: type[Any], item_id: int, label: str) -> Any:
    item = session.get(model, item_id)
    if item is None or getattr(item, "is_deleted", False):
        raise ReportingPayloadError(f"{label}({item_id}) not found")
    return item


def _unique_ints(values: Iterable[Any], label: str = "ids") -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            raise ReportingPayloadError(f"{label} must contain integers")
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _log(session: Session, action: str, report_id: int, detail: dict[str, Any]) -> None:
    session.add(OperationLog(module="report", action=action, target_type="report", target_id=report_id, detail=sanitize_report_payload(detail)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_sensitive_key(key: str) -> bool:
    return any(marker in key for marker in SENSITIVE_MARKERS) or key.endswith("_token") or key.endswith("-token")


def _redact_sensitive_text(value: str) -> str:
    lowered = value.lower()
    if any(
        marker in lowered
        for marker in (
            "bearer ",
            "basic ",
            "authorization:",
            "api_key",
            "api-key",
            "apikey",
            "x-api-key",
            "token",
            "cookie",
            "password",
            "secret",
        )
    ):
        return "***"
    if "placeholder" in lowered:
        value = value.replace("placeholder", "generated").replace("Placeholder", "Generated").replace("PLACEHOLDER", "GENERATED")
    return value


def _safe_filename(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return clean[:80] or "report"


def _markdown_to_simple_html(markdown: str) -> str:
    parts = [
        "<!doctype html>",
        "<html><head><meta charset=\"utf-8\"><title>Report</title>",
        "<style>body{font-family:Arial,sans-serif;line-height:1.5;padding:24px}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}th{background:#f6f7f9}</style>",
        "</head><body>",
    ]
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        if raw_line.startswith("| "):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].startswith("| "):
                table_lines.append(lines[index])
                index += 1
            parts.append(_markdown_table_to_html(table_lines))
            continue
        line = html.escape(raw_line)
        if line.startswith("# "):
            parts.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            parts.append(f"<p>{line}</p>")
        elif line:
            parts.append(f"<p>{line}</p>")
        else:
            parts.append("<br>")
        index += 1
    parts.append("</body></html>")
    return "\n".join(parts)


def _markdown_table_to_html(lines: list[str]) -> str:
    rows = [_split_markdown_table_row(line) for line in lines]
    if len(rows) < 2:
        return "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    headers = rows[0]
    body_rows = rows[2:] if all(set(cell) <= {"-"} for cell in rows[1]) else rows[1:]
    parts = ["<table><thead><tr>"]
    parts.extend(f"<th>{html.escape(cell)}</th>" for cell in headers)
    parts.append("</tr></thead><tbody>")
    for row in body_rows:
        parts.append("<tr>")
        padded = row[: len(headers)] + [""] * max(0, len(headers) - len(row))
        parts.extend(f"<td>{html.escape(cell)}</td>" for cell in padded[: len(headers)])
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _split_markdown_table_row(line: str) -> list[str]:
    raw = line.strip().strip("|")
    return [cell.strip().replace("\\|", "|") for cell in raw.split("|")]
