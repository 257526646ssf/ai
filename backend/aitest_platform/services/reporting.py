from __future__ import annotations

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
    ReportTemplate,
    RequirementDocument,
    RequirementItem,
    TestCase,
    TestRound,
)

SENSITIVE_MARKERS = (
    "api_key",
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
    template_id: int | None = None,
    related_scope: dict[str, Any] | None = None,
) -> Report:
    context = build_aggregation_context(
        session,
        project_id=project_id,
        requirement_item_ids=list(requirement_item_ids or []),
        template_id=template_id,
    )
    template_version = context["scope_snapshot"]["template"]["version"]
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
        content=render_markdown_report(name, context),
        template_id=template_id,
        template_version=template_version,
        ai_summary_version="rules-v1",
    )
    session.add(report)
    session.flush()
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
        template_id=template_id,
        perf_plan_id=plan.id,
        perf_result_id=result.id if result else None,
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
        content=render_markdown_report(name, context),
        template_id=template_id,
        template_version=context["scope_snapshot"]["template"]["version"],
        ai_summary_version="rules-v1",
    )
    session.add(report)
    session.flush()
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
            data_snapshot={**context["data_snapshot"], "lightweight_conclusion": conclusion},
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
    template_id: int | None = None,
    perf_plan_id: int | None = None,
    perf_result_id: int | None = None,
) -> dict[str, Any]:
    project = _require_active(session, Project, project_id, "Project")
    requested_item_ids = _unique_ints(requirement_item_ids or [])
    fact_filter_item_ids = requested_item_ids
    item_stmt = select(RequirementItem).where(RequirementItem.project_id == project_id, RequirementItem.is_deleted.is_(False))
    if requested_item_ids:
        item_stmt = item_stmt.where(RequirementItem.id.in_(requested_item_ids))
    requirement_items = list(session.scalars(item_stmt.order_by(RequirementItem.id)))
    resolved_item_ids = [item.id for item in requirement_items]
    item_filter = resolved_item_ids or requested_item_ids

    documents = _documents_for_items(session, project_id, requirement_items)
    test_cases = _test_cases(session, project_id, fact_filter_item_ids)
    executions = _executions(session, project_id, fact_filter_item_ids)
    defects = _defects(session, project_id, fact_filter_item_ids)
    rounds = _test_rounds(session, project_id, fact_filter_item_ids)
    api_libs, api_endpoints, api_test_cases, api_executions = _api_facts(session, project_id, fact_filter_item_ids)
    auto_projects, auto_executions = _auto_facts(session, project_id)
    perf_plans, perf_results = _perf_facts(session, project_id, fact_filter_item_ids, perf_plan_id, perf_result_id)
    template = session.get(ReportTemplate, template_id) if template_id is not None else None

    source_document_ids = sorted({item.document_id for item in requirement_items if item.document_id is not None})
    report_scope = {
        "project_id": project_id,
        "requirement_item_ids": resolved_item_ids,
        "requested_requirement_item_ids": requested_item_ids,
        "source_document_ids": source_document_ids,
        "module_types": ["functional", "api", "automation", "performance"],
        "perf_plan_id": perf_plan_id,
        "perf_result_id": perf_result_id,
    }
    source_refs = {
        "project_id": project_id,
        "requirement_item_ids": resolved_item_ids,
        "source_document_ids": source_document_ids,
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
    data_snapshot["perf"]["summary"].update(data_snapshot["performance_summary"])
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
                "sections": template.sections if template else ["overview", "requirements", "executions", "defects", "api", "automation", "performance"],
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
    metrics = data["summary_metrics"]
    perf = data["performance_summary"]
    lines = [
        f"# {title}",
        "",
        "## 范围快照",
        f"- 项目：{data['project'].get('name')}（ID: {data['project'].get('id')}）",
        f"- 需求项：{metrics['requirement_item_count']}",
        f"- 来源文档：{metrics['source_document_count']}",
        f"- 生成时间：{context['scope_snapshot']['generated_at']}",
        "",
        "## 核心指标",
        f"- 测试用例：{metrics['test_case_count']}",
        f"- 手工/主链执行：{metrics['execution_count']}，通过率：{metrics['execution_pass_rate']}%",
        f"- 缺陷：{metrics['defect_count']}，未关闭：{metrics['open_defect_count']}",
        f"- 接口执行：{metrics['api_execution_count']}，通过率：{metrics['api_pass_rate']}%",
        f"- 自动化执行：{metrics['auto_execution_count']}，通过率：{metrics['auto_pass_rate']}%",
        f"- 性能结果：{metrics['perf_result_count']}，最新 P95：{perf.get('latest_p95_ms')}",
        "",
        "## 事实汇总",
        f"- 执行状态分布：{json.dumps(data['execution_summary'], ensure_ascii=False)}",
        f"- 缺陷状态分布：{json.dumps(data['defect_summary'], ensure_ascii=False)}",
        f"- 接口状态分布：{json.dumps(data['api_summary'], ensure_ascii=False)}",
        f"- 自动化状态分布：{json.dumps(data['automation_summary'], ensure_ascii=False)}",
        "",
        "## 结论",
        _brief_conclusion(metrics, data["risk_items"], "report"),
    ]
    if data["risk_items"]:
        lines.extend(["", "## 风险项"])
        for index, risk in enumerate(data["risk_items"][:10], start=1):
            lines.append(f"{index}. [{risk['level']}] {risk['title']} - {risk['detail']}")
    return sanitize_report_payload("\n".join(lines).strip() + "\n")


def export_report(report: Report, output_format: str) -> dict[str, Any]:
    fmt = (output_format or "markdown").lower()
    if fmt not in {"markdown", "html", "json"}:
        raise ReportingPayloadError("format must be one of: markdown, html, json")
    base_name = _safe_filename(report.name or f"report-{report.id}")
    if fmt == "json":
        content = json.dumps(
            sanitize_report_payload(
                {
                    "report": _model_dict(report),
                    "scope_snapshot": report.scope_snapshot or {},
                    "data_snapshot": report.data_snapshot or {},
                    "source_refs_json": report.source_refs_json or {},
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


def _documents_for_items(session: Session, project_id: int, items: list[RequirementItem]) -> list[RequirementDocument]:
    document_ids = sorted({item.document_id for item in items if item.document_id is not None})
    if document_ids:
        return list(
            session.scalars(
                select(RequirementDocument)
                .where(RequirementDocument.project_id == project_id, RequirementDocument.id.in_(document_ids), RequirementDocument.is_deleted.is_(False))
                .order_by(RequirementDocument.id)
            )
        )
    return []


def _test_cases(session: Session, project_id: int, item_ids: list[int]) -> list[TestCase]:
    stmt = select(TestCase).where(TestCase.project_id == project_id, TestCase.is_deleted.is_(False))
    if item_ids:
        stmt = stmt.where(TestCase.requirement_item_id.in_(item_ids))
    return list(session.scalars(stmt.order_by(TestCase.id)))


def _executions(session: Session, project_id: int, item_ids: list[int]) -> list[Execution]:
    stmt = select(Execution).where(Execution.project_id == project_id)
    if item_ids:
        stmt = stmt.where(Execution.requirement_item_id.in_(item_ids))
    return list(session.scalars(stmt.order_by(Execution.executed_at.desc(), Execution.id.desc())))


def _defects(session: Session, project_id: int, item_ids: list[int]) -> list[Defect]:
    stmt = select(Defect).where(Defect.project_id == project_id)
    if item_ids:
        stmt = stmt.where(Defect.requirement_item_id.in_(item_ids))
    return list(session.scalars(stmt.order_by(Defect.id.desc())))


def _test_rounds(session: Session, project_id: int, item_ids: list[int]) -> list[TestRound]:
    stmt = select(TestRound).where(TestRound.project_id == project_id)
    if item_ids:
        stmt = stmt.where(TestRound.requirement_item_id.in_(item_ids))
    return list(session.scalars(stmt.order_by(TestRound.id.desc())))


def _api_executions(session: Session, project_id: int, item_ids: list[int]) -> list[ApiExecution]:
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
    return list(session.scalars(stmt.order_by(ApiExecution.executed_at.desc(), ApiExecution.id.desc())))


def _api_facts(session: Session, project_id: int, item_ids: list[int]) -> tuple[list[ApiTestLib], list[ApiEndpoint], list[ApiTestCase], list[ApiExecution]]:
    libs = list(
        session.scalars(
            select(ApiTestLib)
            .where(ApiTestLib.project_id == project_id, ApiTestLib.is_deleted.is_(False))
            .order_by(ApiTestLib.id.desc())
        )
    )
    lib_ids = [lib.id for lib in libs]
    if not lib_ids:
        return [], [], [], []
    endpoint_stmt = select(ApiEndpoint).where(ApiEndpoint.lib_id.in_(lib_ids), ApiEndpoint.is_deleted.is_(False))
    case_stmt = select(ApiTestCase).where(ApiTestCase.lib_id.in_(lib_ids), ApiTestCase.is_deleted.is_(False))
    if item_ids:
        endpoint_stmt = endpoint_stmt.where(ApiEndpoint.requirement_item_id.in_(item_ids))
        case_stmt = case_stmt.where(ApiTestCase.requirement_item_id.in_(item_ids))
    endpoints = list(session.scalars(endpoint_stmt.order_by(ApiEndpoint.id.desc())))
    cases = list(session.scalars(case_stmt.order_by(ApiTestCase.id.desc())))
    executions = _api_executions(session, project_id, item_ids)
    return libs, endpoints, cases, executions


def _auto_facts(session: Session, project_id: int) -> tuple[list[AutoProject], list[AutoExecution]]:
    projects = list(
        session.scalars(
            select(AutoProject)
            .where(AutoProject.project_id == project_id, AutoProject.is_deleted.is_(False))
            .order_by(AutoProject.id.desc())
        )
    )
    stmt = (
        select(AutoExecution)
        .join(AutoProject, AutoProject.id == AutoExecution.auto_project_id)
        .where(AutoProject.project_id == project_id, AutoProject.is_deleted.is_(False))
        .order_by(AutoExecution.executed_at.desc(), AutoExecution.id.desc())
    )
    return projects, list(session.scalars(stmt))


def _perf_facts(
    session: Session,
    project_id: int,
    item_ids: list[int],
    perf_plan_id: int | None,
    perf_result_id: int | None,
) -> tuple[list[PerfPlan], list[PerfResult]]:
    plan_stmt = select(PerfPlan).where(PerfPlan.project_id == project_id, PerfPlan.is_deleted.is_(False))
    if perf_plan_id is not None:
        plan_stmt = plan_stmt.where(PerfPlan.id == perf_plan_id)
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
    if not results:
        return {"latest_result_id": None, "latest_status": None, "latest_p95_ms": None, "latest_error_rate": None}
    latest = results[0]
    summary = latest.summary_data or {}
    return {
        "latest_result_id": latest.id,
        "latest_status": latest.status,
        "latest_avg_ms": summary.get("avg_ms") or summary.get("average_ms"),
        "latest_p95_ms": summary.get("p95_ms") or summary.get("p95"),
        "latest_error_rate": summary.get("error_rate"),
        "latest_success_rate": summary.get("success_rate"),
        "result_count": len(results),
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


def _unique_ints(values: Iterable[Any]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            raise ReportingPayloadError("requirement_item_ids must contain integers")
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
    if any(marker in lowered for marker in ("bearer ", "basic ", "api_key=", "token=", "password=", "secret=")):
        return "***"
    if "placeholder" in lowered:
        value = value.replace("placeholder", "generated").replace("Placeholder", "Generated").replace("PLACEHOLDER", "GENERATED")
    return value


def _safe_filename(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return clean[:80] or "report"


def _markdown_to_simple_html(markdown: str) -> str:
    parts = ["<!doctype html>", "<html><head><meta charset=\"utf-8\"><title>Report</title></head><body>"]
    for raw_line in markdown.splitlines():
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
    parts.append("</body></html>")
    return "\n".join(parts)
