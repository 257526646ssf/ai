from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from aitest_platform.models import (
    ApiEndpoint,
    ApiEnvironment,
    ApiExecution,
    ApiScenario,
    ApiSchedule,
    ApiTestCase,
    ApiTestLib,
    AutoCaseFile,
    AutoExecution,
    AutoProject,
    BackupSnapshot,
    Defect,
    Execution,
    GenerationJob,
    LlmConfig,
    LlmUsage,
    OperationLog,
    PerfPlan,
    PerfResult,
    Project,
    PromptTemplate,
    Report,
    ReportTemplate,
    RequirementDocument,
    RequirementDocumentBlock,
    RequirementItem,
    RequirementLib,
    TestCase,
    TestPoint,
    TestRound,
)


class NotFoundError(ValueError):
    pass


class AitestRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_project(self, name: str, description: str | None = None, code: str | None = None, owner_name: str | None = None) -> Project:
        project = Project(
            code=code or self._next_code("PRJ", Project),
            name=name,
            description=description,
            owner_name=owner_name,
        )
        self.session.add(project)
        self.session.flush()
        self._log("project", "create", "project", project.id, {"name": name})
        return project

    def list_projects(self) -> list[Project]:
        return list(self.session.scalars(select(Project).where(Project.is_deleted.is_(False)).order_by(Project.id.desc())))

    def get_project(self, project_id: int) -> Project:
        return self._get(Project, project_id)

    def create_requirement_lib(self, project_id: int, name: str, description: str | None = None) -> RequirementLib:
        self.get_project(project_id)
        lib = RequirementLib(project_id=project_id, name=name, description=description)
        self.session.add(lib)
        self.session.flush()
        self._log("requirement", "create_lib", "requirement_lib", lib.id, {"project_id": project_id, "name": name})
        return lib

    def list_requirement_libs(self, project_id: int) -> list[RequirementLib]:
        stmt = (
            select(RequirementLib)
            .where(RequirementLib.project_id == project_id, RequirementLib.is_deleted.is_(False))
            .order_by(RequirementLib.id.desc())
        )
        return list(self.session.scalars(stmt))

    def create_requirement_document(
        self,
        project_id: int,
        lib_id: int,
        name: str,
        source_type: str = "text",
        raw_content: str | None = None,
        source_file_name: str | None = None,
        source_file_path: str | None = None,
    ) -> RequirementDocument:
        self._get(RequirementLib, lib_id)
        document = RequirementDocument(
            project_id=project_id,
            lib_id=lib_id,
            document_number=self._next_code("DOC", RequirementDocument, "document_number"),
            name=name,
            source_type=source_type,
            raw_content=raw_content,
            source_file_name=source_file_name,
            source_file_path=source_file_path,
        )
        self.session.add(document)
        self.session.flush()
        self._log("requirement", "create_document", "requirement_document", document.id, {"name": name, "source_type": source_type})
        return document

    def parse_requirement_document(self, document_id: int) -> GenerationJob:
        document = self._get(RequirementDocument, document_id)
        document.parser_status = "parsed"
        summary = self._summary(document.raw_content or document.name)
        document.parser_metadata = {
            "summary": summary,
            "parser": "placeholder",
            "parsed_at": self._now_iso(),
        }

        existing_blocks = self.session.scalar(
            select(func.count()).select_from(RequirementDocumentBlock).where(RequirementDocumentBlock.document_id == document.id)
        )
        if not existing_blocks:
            block = RequirementDocumentBlock(
                document_id=document.id,
                block_key=f"doc-{document.id}-blk-1",
                block_type="paragraph",
                raw_text=document.raw_content or document.name,
                normalized_text=document.raw_content or document.name,
                order_no=1,
                metadata_json={"source_type": document.source_type},
            )
            self.session.add(block)

        job = self._create_job(
            project_id=document.project_id,
            document_id=document.id,
            requirement_item_id=None,
            job_type="parse_document",
            input_payload={"document_id": document.id},
            output_payload={"summary": summary, "status": "parsed"},
        )
        self._log("requirement", "parse_document", "requirement_document", document.id, {"job_id": job.id})
        return job

    def extract_requirement_items_placeholder(self, document_id: int, items: Iterable[dict[str, Any]] | None = None) -> GenerationJob:
        document = self._get(RequirementDocument, document_id)
        blocks = list(
            self.session.scalars(
                select(RequirementDocumentBlock)
                .where(RequirementDocumentBlock.document_id == document.id)
                .order_by(RequirementDocumentBlock.order_no)
            )
        )
        if not blocks:
            self.parse_requirement_document(document.id)
            self.session.flush()
            blocks = list(
                self.session.scalars(
                    select(RequirementDocumentBlock)
                    .where(RequirementDocumentBlock.document_id == document.id)
                    .order_by(RequirementDocumentBlock.order_no)
                )
            )

        created_items: list[RequirementItem] = []
        source_items = list(items) if items is not None else [self._placeholder_requirement_item(document, blocks)]
        for payload in source_items:
            item = RequirementItem(
                project_id=document.project_id,
                lib_id=document.lib_id,
                document_id=document.id,
                item_number=self._next_code("REQ", RequirementItem, "item_number"),
                title=payload.get("title") or document.name,
                summary=payload.get("summary") or payload.get("description"),
                module=payload.get("module"),
                actor=payload.get("actor"),
                goal=payload.get("goal"),
                preconditions_json=payload.get("preconditions") or [],
                business_rules_json=payload.get("business_rules") or [],
                state_transitions_json=payload.get("state_transitions") or [],
                exceptions_json=payload.get("exceptions") or [],
                permissions_json=payload.get("permissions") or [],
                non_functional_json=payload.get("non_functional") or [],
                priority=payload.get("priority", "P2"),
                status=payload.get("status", "draft"),
                confidence=float(payload.get("confidence", 0.7)),
                granularity_flag=payload.get("granularity_flag", "normal"),
                source_anchor_ids=payload.get("source_anchor_ids") or [block.block_key for block in blocks[:1]],
            )
            self.session.add(item)
            created_items.append(item)

        document.parser_status = "parsed"
        self.session.flush()
        job = self._create_job(
            project_id=document.project_id,
            document_id=document.id,
            requirement_item_id=None,
            job_type="extract_items",
            input_payload={"document_id": document.id, "placeholder": items is None},
            output_payload={"item_ids": [item.id for item in created_items]},
        )
        self._log("requirement", "extract_items", "requirement_document", document.id, {"job_id": job.id, "count": len(created_items)})
        return job

    def confirm_requirement_item(self, item_id: int) -> RequirementItem:
        item = self._get(RequirementItem, item_id)
        item.status = "confirmed"
        item.version += 1
        self.session.flush()
        self._log("requirement", "confirm_item", "requirement_item", item.id, {"version": item.version})
        return item

    def update_requirement_item(self, item_id: int, **fields: Any) -> RequirementItem:
        item = self._get(RequirementItem, item_id)
        allowed = {
            "title",
            "summary",
            "module",
            "actor",
            "goal",
            "priority",
            "status",
            "granularity_flag",
            "preconditions_json",
            "business_rules_json",
            "state_transitions_json",
            "exceptions_json",
            "permissions_json",
            "non_functional_json",
        }
        changed: dict[str, Any] = {}
        for key, value in fields.items():
            if key in allowed and getattr(item, key) != value:
                setattr(item, key, value)
                changed[key] = value
        if changed:
            item.version += 1
            for point in item.test_points:
                point.coverage_status = "todo"
            for case in item.test_cases:
                case.status = "requirement_changed"
            self._log("requirement", "update_item", "requirement_item", item.id, {"changed_fields": list(changed)})
        return item

    def generate_test_points(self, item_id: int, points: Iterable[dict[str, Any]] | None = None) -> GenerationJob:
        item = self._get(RequirementItem, item_id)
        source_points = list(points) if points is not None else self._placeholder_test_points(item)
        created_points: list[TestPoint] = []
        for payload in source_points:
            point = TestPoint(
                requirement_item_id=item.id,
                title=payload["title"],
                point_type=payload.get("point_type", "functional"),
                target=payload.get("target"),
                priority=payload.get("priority", "P2"),
                suggested_method=payload.get("suggested_method", "manual"),
                coverage_status=payload.get("coverage_status", "todo"),
                source_anchor_ids=payload.get("source_anchor_ids") or item.source_anchor_ids,
                note=payload.get("note"),
            )
            self.session.add(point)
            created_points.append(point)

        self.session.flush()
        job = self._create_job(
            project_id=item.project_id,
            document_id=item.document_id,
            requirement_item_id=item.id,
            job_type="generate_points",
            input_payload={"requirement_item_id": item.id, "placeholder": points is None},
            output_payload={"test_point_ids": [point.id for point in created_points]},
        )
        self._log("test_point", "generate", "requirement_item", item.id, {"job_id": job.id, "count": len(created_points)})
        return job

    def generate_test_cases(
        self,
        item_id: int,
        test_point_ids: Iterable[int] | None = None,
        generation_mode: str = "standard",
        cases: Iterable[dict[str, Any]] | None = None,
    ) -> GenerationJob:
        item = self._get(RequirementItem, item_id)
        point_stmt = select(TestPoint).where(TestPoint.requirement_item_id == item.id, TestPoint.is_deleted.is_(False))
        if test_point_ids:
            point_stmt = point_stmt.where(TestPoint.id.in_(list(test_point_ids)))
        points = list(self.session.scalars(point_stmt.order_by(TestPoint.id)))
        if not points:
            self.generate_test_points(item.id)
            self.session.flush()
            points = list(self.session.scalars(point_stmt.order_by(TestPoint.id)))

        created_cases: list[TestCase] = []
        source_cases = list(cases) if cases is not None else self._placeholder_test_cases(item, points, generation_mode)
        point_by_id = {point.id: point for point in points}
        default_point = points[0] if points else None
        case_sequence = self.session.scalar(select(func.count()).select_from(TestCase)) or 0
        for offset, payload in enumerate(source_cases, start=1):
            point = point_by_id.get(payload.get("test_point_id")) or default_point
            case = TestCase(
                project_id=item.project_id,
                lib_id=item.lib_id,
                document_id=item.document_id,
                requirement_item_id=item.id,
                test_point_id=point.id if point else None,
                case_number=self._unique_code("TC", TestCase, "case_number", case_sequence + offset),
                title=payload["title"],
                case_type=payload.get("case_type", "functional"),
                precondition=payload.get("precondition"),
                steps=payload.get("steps") or [],
                expected_result=payload.get("expected_result") or "结果符合需求描述和验收口径。",
                priority=payload.get("priority", "P2"),
                tags=payload.get("tags") or [generation_mode],
                source_anchor_ids=payload.get("source_anchor_ids") or item.source_anchor_ids,
                evidence_type=payload.get("evidence_type", "original"),
                generation_reason=payload.get("generation_reason", f"{generation_mode} placeholder generation"),
                status=payload.get("status", "draft"),
            )
            self.session.add(case)
            created_cases.append(case)
            if point:
                point.has_generated_cases = True

        item.case_status = "generated"
        self.session.flush()
        job = self._create_job(
            project_id=item.project_id,
            document_id=item.document_id,
            requirement_item_id=item.id,
            job_type="generate_cases",
            input_payload={"requirement_item_id": item.id, "generation_mode": generation_mode, "placeholder": cases is None},
            output_payload={"test_case_ids": [case.id for case in created_cases]},
        )
        self._log("test_case", "generate", "requirement_item", item.id, {"job_id": job.id, "count": len(created_cases)})
        return job

    def create_test_round(self, project_id: int, name: str, requirement_item_id: int | None = None, document_id: int | None = None) -> TestRound:
        round_ = TestRound(project_id=project_id, requirement_item_id=requirement_item_id, document_id=document_id, name=name)
        self.session.add(round_)
        self.session.flush()
        self._log("execution", "create_round", "test_round", round_.id, {"project_id": project_id})
        return round_

    def create_execution_record(
        self,
        case_id: int,
        status: str,
        round_id: int | None = None,
        executor_type: str = "manual",
        actual_result: str | None = None,
        execution_time: int | None = None,
        **extra: Any,
    ) -> Execution:
        case = self._get(TestCase, case_id)
        execution = Execution(
            project_id=case.project_id,
            lib_id=case.lib_id,
            document_id=case.document_id,
            requirement_item_id=case.requirement_item_id,
            case_id=case.id,
            round_id=round_id,
            executor_type=executor_type,
            status=status,
            actual_result=actual_result,
            execution_time=execution_time,
            block_reason=extra.get("block_reason"),
            skip_reason=extra.get("skip_reason"),
            pass_remark=extra.get("pass_remark"),
            ai_analysis=extra.get("ai_analysis"),
            request_snapshot=extra.get("request_snapshot"),
            response_snapshot=extra.get("response_snapshot"),
            artifact_summary_json=extra.get("artifact_summary_json"),
        )
        self.session.add(execution)
        self.session.flush()
        if round_id:
            self._update_round_counts(round_id)
        if status == "fail" and extra.get("create_defect", True):
            self.create_defect_from_execution(execution, extra.get("defect_title"))
        self._log("execution", "create", "execution_record", execution.id, {"case_id": case_id, "status": status})
        return execution

    def create_defect_from_execution(self, execution: Execution, title: str | None = None) -> Defect:
        case = self._get(TestCase, execution.case_id)
        defect = Defect(
            defect_number=self._next_code("DEF", Defect, "defect_number"),
            project_id=execution.project_id,
            execution_id=execution.id,
            case_id=execution.case_id,
            requirement_item_id=execution.requirement_item_id,
            title=title or f"{case.title} 执行失败",
            actual_result=execution.actual_result,
            severity="normal",
            status="open",
        )
        self.session.add(defect)
        self.session.flush()
        return defect

    def generate_report_snapshot(
        self,
        project_id: int,
        name: str,
        report_type: str = "comprehensive",
        requirement_item_ids: Iterable[int] | None = None,
        template_id: int | None = None,
    ) -> Report:
        scope_item_ids = list(requirement_item_ids or [])
        data_snapshot = self._build_report_data(project_id, scope_item_ids)
        report = Report(
            project_id=project_id,
            name=name,
            type=report_type,
            related_module="project",
            related_scope_json={"project_id": project_id, "requirement_item_ids": scope_item_ids},
            requirement_item_ids_json=scope_item_ids,
            source_document_ids_json=data_snapshot["source_document_ids"],
            scope_snapshot={"project_id": project_id, "requirement_item_ids": scope_item_ids, "generated_at": self._now_iso()},
            data_snapshot=data_snapshot,
            source_refs_json=data_snapshot["source_refs"],
            content=self._render_report_content(name, data_snapshot),
            template_id=template_id,
        )
        self.session.add(report)
        self.session.flush()
        self._log("report", "generate_snapshot", "report", report.id, {"project_id": project_id, "type": report_type})
        return report

    def create_api_lib(self, project_id: int, name: str, description: str | None = None, **fields: Any) -> ApiTestLib:
        self.get_project(project_id)
        lib = ApiTestLib(
            project_id=project_id,
            source_document_id=fields.get("source_document_id"),
            name=name,
            description=description,
            import_source=fields.get("import_source"),
        )
        self.session.add(lib)
        self.session.flush()
        self._log("api_testing", "create_lib", "api_test_lib", lib.id, {"project_id": project_id, "name": name})
        return lib

    def list_api_libs(self, project_id: int) -> list[ApiTestLib]:
        return list(
            self.session.scalars(
                select(ApiTestLib)
                .where(ApiTestLib.project_id == project_id, ApiTestLib.is_deleted.is_(False))
                .order_by(ApiTestLib.id.desc())
            )
        )

    def update_api_lib(self, lib_id: int, **fields: Any) -> ApiTestLib:
        lib = self._get(ApiTestLib, lib_id)
        self._assign_fields(lib, fields, {"name", "description", "source_document_id", "import_source"})
        self._log("api_testing", "update_lib", "api_test_lib", lib.id, {"fields": self._public_field_names(fields)})
        return lib

    def delete_api_lib(self, lib_id: int) -> ApiTestLib:
        lib = self._soft_delete(ApiTestLib, lib_id)
        self._log("api_testing", "delete_lib", "api_test_lib", lib.id, {})
        return lib

    def create_api_endpoint(self, lib_id: int, name: str, method: str, path: str, **fields: Any) -> ApiEndpoint:
        self._get(ApiTestLib, lib_id)
        endpoint = ApiEndpoint(
            lib_id=lib_id,
            requirement_item_id=fields.get("requirement_item_id"),
            name=name,
            method=method.upper(),
            path=path,
            headers_schema=fields.get("headers_schema") or fields.get("headers") or {},
            query_schema=fields.get("query_schema") or fields.get("query") or {},
            body_schema=fields.get("body_schema") or fields.get("body") or {},
            response_schema=fields.get("response_schema") or fields.get("response") or {},
            description=fields.get("description"),
        )
        self.session.add(endpoint)
        self.session.flush()
        self._log("api_testing", "create_endpoint", "api_endpoint", endpoint.id, {"lib_id": lib_id, "method": endpoint.method, "path": path})
        return endpoint

    def import_api_endpoints(self, lib_id: int, endpoints: Iterable[dict[str, Any]], import_source: str = "manual") -> list[ApiEndpoint]:
        lib = self._get(ApiTestLib, lib_id)
        created = [
            self.create_api_endpoint(
                lib_id,
                payload.get("name") or f"{payload.get('method', 'GET').upper()} {payload.get('path', '/')}",
                payload.get("method", "GET"),
                payload.get("path", "/"),
                **payload,
            )
            for payload in endpoints
        ]
        lib.import_source = import_source
        lib.latest_sync_at = datetime.now(timezone.utc)
        self._log("api_testing", "import_endpoints", "api_test_lib", lib.id, {"count": len(created), "source": import_source})
        return created

    def list_api_endpoints(self, lib_id: int) -> list[ApiEndpoint]:
        return list(
            self.session.scalars(
                select(ApiEndpoint)
                .where(ApiEndpoint.lib_id == lib_id, ApiEndpoint.is_deleted.is_(False))
                .order_by(ApiEndpoint.id.desc())
            )
        )

    def update_api_endpoint(self, endpoint_id: int, **fields: Any) -> ApiEndpoint:
        endpoint = self._get(ApiEndpoint, endpoint_id)
        if "method" in fields and fields["method"] is not None:
            fields["method"] = str(fields["method"]).upper()
        self._assign_fields(
            endpoint,
            fields,
            {"name", "method", "path", "requirement_item_id", "headers_schema", "query_schema", "body_schema", "response_schema", "description"},
        )
        self._log("api_testing", "update_endpoint", "api_endpoint", endpoint.id, {"fields": self._public_field_names(fields)})
        return endpoint

    def delete_api_endpoint(self, endpoint_id: int) -> ApiEndpoint:
        endpoint = self._soft_delete(ApiEndpoint, endpoint_id)
        self._log("api_testing", "delete_endpoint", "api_endpoint", endpoint.id, {})
        return endpoint

    def generate_api_cases(self, endpoint_id: int, cases: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        endpoint = self._get(ApiEndpoint, endpoint_id)
        source_cases = list(cases) if cases is not None else self._placeholder_api_cases(endpoint)
        created: list[ApiTestCase] = []
        for offset, payload in enumerate(source_cases, start=1):
            case = ApiTestCase(
                endpoint_id=endpoint.id,
                lib_id=endpoint.lib_id,
                requirement_item_id=payload.get("requirement_item_id") or endpoint.requirement_item_id,
                name=payload.get("name") or f"{endpoint.name} case {offset}",
                category=payload.get("category", "contract"),
                request_headers=self._sanitize_secret_map(payload.get("request_headers") or {}),
                request_query=payload.get("request_query") or {},
                request_body=self._sanitize_secret_map(payload.get("request_body")),
                content_type=payload.get("content_type", "application/json"),
                expected_status=int(payload.get("expected_status", 200)),
                assertions=payload.get("assertions") or [{"type": "status_code", "expected": int(payload.get("expected_status", 200))}],
                pre_script=payload.get("pre_script"),
                post_script=payload.get("post_script"),
                status=payload.get("status", "ready"),
                sort_order=int(payload.get("sort_order", offset)),
            )
            self.session.add(case)
            created.append(case)
        self.session.flush()
        self._log("api_testing", "generate_cases", "api_endpoint", endpoint.id, {"count": len(created)})
        return {"endpoint_id": endpoint.id, "case_ids": [case.id for case in created], "count": len(created)}

    def list_api_cases(self, lib_id: int | None = None, endpoint_id: int | None = None) -> list[ApiTestCase]:
        stmt = select(ApiTestCase).where(ApiTestCase.is_deleted.is_(False))
        if lib_id is not None:
            stmt = stmt.where(ApiTestCase.lib_id == lib_id)
        if endpoint_id is not None:
            stmt = stmt.where(ApiTestCase.endpoint_id == endpoint_id)
        return list(self.session.scalars(stmt.order_by(ApiTestCase.sort_order, ApiTestCase.id)))

    def execute_api_case(self, case_id: int, environment_id: int | None = None, run_type: str = "case", **extra: Any) -> ApiExecution:
        case = self._get(ApiTestCase, case_id)
        endpoint = self._get(ApiEndpoint, case.endpoint_id)
        environment = self._get(ApiEnvironment, environment_id) if environment_id else self._active_api_environment(case.lib_id)
        request_url = f"{environment.base_url.rstrip('/') if environment else 'http://placeholder.local'}{endpoint.path}"
        execution = ApiExecution(
            lib_id=case.lib_id,
            endpoint_id=endpoint.id,
            case_id=case.id,
            environment_id=environment.id if environment else None,
            scenario_id=extra.get("scenario_id"),
            schedule_id=extra.get("schedule_id"),
            run_type=run_type,
            status=extra.get("status", "passed"),
            request_snapshot=self._sanitize_secret_map(
                {
                    "method": endpoint.method,
                    "url": request_url,
                    "headers": case.request_headers or {},
                    "query": case.request_query or {},
                    "body": case.request_body,
                }
            ),
            response_snapshot={"status_code": case.expected_status, "body": {"placeholder": True}},
            assertion_results=[{"name": "status_code", "passed": True, "expected": case.expected_status, "actual": case.expected_status}],
            duration_ms=int(extra.get("duration_ms", 24)),
        )
        self.session.add(execution)
        self.session.flush()
        self._log("api_testing", "execute_case", "api_execution", execution.id, {"case_id": case.id, "status": execution.status})
        return execution

    def execute_api_cases_batch(self, case_ids: Iterable[int], environment_id: int | None = None) -> dict[str, Any]:
        executions = [self.execute_api_case(case_id, environment_id=environment_id, run_type="batch") for case_id in case_ids]
        return {"execution_ids": [execution.id for execution in executions], "total": len(executions), "passed": len(executions), "failed": 0}

    def create_api_environment(self, lib_id: int, name: str, base_url: str, **fields: Any) -> ApiEnvironment:
        self._get(ApiTestLib, lib_id)
        env = ApiEnvironment(
            lib_id=lib_id,
            name=name,
            base_url=base_url,
            headers=self._sanitize_secret_map(fields.get("headers") or {}),
            variables=self._sanitize_secret_map(fields.get("variables") or {}),
            is_active=bool(fields.get("is_active", False)),
            sort_order=int(fields.get("sort_order", 0)),
        )
        self.session.add(env)
        self.session.flush()
        if env.is_active:
            self.activate_api_environment(env.id)
        self._log("api_testing", "create_environment", "api_environment", env.id, {"lib_id": lib_id, "name": name})
        return env

    def list_api_environments(self, lib_id: int) -> list[ApiEnvironment]:
        return list(
            self.session.scalars(
                select(ApiEnvironment)
                .where(ApiEnvironment.lib_id == lib_id, ApiEnvironment.is_deleted.is_(False))
                .order_by(ApiEnvironment.sort_order, ApiEnvironment.id)
            )
        )

    def update_api_environment(self, environment_id: int, **fields: Any) -> ApiEnvironment:
        env = self._get(ApiEnvironment, environment_id)
        if "headers" in fields:
            fields["headers"] = self._sanitize_secret_map(fields["headers"])
        if "variables" in fields:
            fields["variables"] = self._sanitize_secret_map(fields["variables"])
        self._assign_fields(env, fields, {"name", "base_url", "headers", "variables", "sort_order"})
        if fields.get("is_active") is True:
            self.activate_api_environment(env.id)
        self._log("api_testing", "update_environment", "api_environment", env.id, {"fields": self._public_field_names(fields)})
        return env

    def activate_api_environment(self, environment_id: int) -> ApiEnvironment:
        env = self._get(ApiEnvironment, environment_id)
        for item in self.session.scalars(select(ApiEnvironment).where(ApiEnvironment.lib_id == env.lib_id)):
            item.is_active = item.id == env.id
        self.session.flush()
        self._log("api_testing", "activate_environment", "api_environment", env.id, {"lib_id": env.lib_id})
        return env

    def create_api_scenario(self, lib_id: int, name: str, **fields: Any) -> ApiScenario:
        self._get(ApiTestLib, lib_id)
        scenario = ApiScenario(
            lib_id=lib_id,
            name=name,
            description=fields.get("description"),
            nodes=fields.get("nodes") or [],
            edges=fields.get("edges") or [],
            data_mappings=fields.get("data_mappings") or {},
        )
        self.session.add(scenario)
        self.session.flush()
        self._log("api_testing", "create_scenario", "api_scenario", scenario.id, {"lib_id": lib_id})
        return scenario

    def list_api_scenarios(self, lib_id: int) -> list[ApiScenario]:
        return list(self.session.scalars(select(ApiScenario).where(ApiScenario.lib_id == lib_id).order_by(ApiScenario.id.desc())))

    def update_api_scenario(self, scenario_id: int, **fields: Any) -> ApiScenario:
        scenario = self._get(ApiScenario, scenario_id)
        self._assign_fields(scenario, fields, {"name", "description", "nodes", "edges", "data_mappings"})
        self._log("api_testing", "update_scenario", "api_scenario", scenario.id, {"fields": self._public_field_names(fields)})
        return scenario

    def execute_api_scenario(self, scenario_id: int, environment_id: int | None = None) -> dict[str, Any]:
        scenario = self._get(ApiScenario, scenario_id)
        case_ids = [node.get("case_id") for node in scenario.nodes if isinstance(node, dict) and node.get("case_id")]
        executions = [self.execute_api_case(case_id, environment_id=environment_id, run_type="scenario", scenario_id=scenario.id) for case_id in case_ids]
        if not executions:
            execution = ApiExecution(
                lib_id=scenario.lib_id,
                scenario_id=scenario.id,
                environment_id=environment_id,
                run_type="scenario",
                status="passed",
                request_snapshot={"scenario_id": scenario.id, "node_count": len(scenario.nodes)},
                response_snapshot={"placeholder": True},
                assertion_results=[],
                duration_ms=10,
            )
            self.session.add(execution)
            self.session.flush()
            executions = [execution]
        self._log("api_testing", "execute_scenario", "api_scenario", scenario.id, {"execution_ids": [item.id for item in executions]})
        return {"scenario_id": scenario.id, "execution_ids": [item.id for item in executions], "status": "passed"}

    def create_api_schedule(self, lib_id: int, name: str, cron_expression: str, target_type: str, target_ids: Iterable[int], **fields: Any) -> ApiSchedule:
        self._get(ApiTestLib, lib_id)
        schedule = ApiSchedule(
            lib_id=lib_id,
            name=name,
            cron_expression=cron_expression,
            target_type=target_type,
            target_ids=list(target_ids),
            is_enabled=bool(fields.get("is_enabled", True)),
            last_result=fields.get("last_result"),
        )
        self.session.add(schedule)
        self.session.flush()
        self._log("api_testing", "create_schedule", "api_schedule", schedule.id, {"target_type": target_type, "target_ids": schedule.target_ids})
        return schedule

    def list_api_schedules(self, lib_id: int) -> list[ApiSchedule]:
        return list(
            self.session.scalars(
                select(ApiSchedule)
                .where(ApiSchedule.lib_id == lib_id, ApiSchedule.is_deleted.is_(False))
                .order_by(ApiSchedule.id.desc())
            )
        )

    def update_api_schedule(self, schedule_id: int, **fields: Any) -> ApiSchedule:
        schedule = self._get(ApiSchedule, schedule_id)
        if "target_ids" in fields and fields["target_ids"] is not None:
            fields["target_ids"] = list(fields["target_ids"])
        self._assign_fields(schedule, fields, {"name", "cron_expression", "target_type", "target_ids", "is_enabled", "last_result"})
        self._log("api_testing", "update_schedule", "api_schedule", schedule.id, {"fields": self._public_field_names(fields)})
        return schedule

    def toggle_api_schedule(self, schedule_id: int, is_enabled: bool | None = None) -> ApiSchedule:
        schedule = self._get(ApiSchedule, schedule_id)
        schedule.is_enabled = (not schedule.is_enabled) if is_enabled is None else bool(is_enabled)
        self._log("api_testing", "toggle_schedule", "api_schedule", schedule.id, {"is_enabled": schedule.is_enabled})
        return schedule

    def create_auto_project(self, project_id: int, name: str, type: str = "ui", language: str = "python", framework: str = "pytest", **fields: Any) -> AutoProject:
        self.get_project(project_id)
        auto_project = AutoProject(
            project_id=project_id,
            name=name,
            type=type,
            language=language,
            framework=framework,
            extra_config=self._sanitize_secret_map(fields.get("extra_config") or {}),
            git_repo_url=fields.get("git_repo_url"),
            git_auth_ref=self._secret_reference(fields.get("git_auth_ref") or fields.get("git_auth")),
            framework_files=fields.get("framework_files"),
            readme=fields.get("readme"),
        )
        self.session.add(auto_project)
        self.session.flush()
        self._log("automation", "create_project", "auto_project", auto_project.id, {"project_id": project_id, "framework": framework})
        return auto_project

    def list_auto_projects(self, project_id: int) -> list[AutoProject]:
        return list(
            self.session.scalars(
                select(AutoProject)
                .where(AutoProject.project_id == project_id, AutoProject.is_deleted.is_(False))
                .order_by(AutoProject.id.desc())
            )
        )

    def update_auto_project(self, auto_project_id: int, **fields: Any) -> AutoProject:
        project = self._get(AutoProject, auto_project_id)
        if "extra_config" in fields:
            fields["extra_config"] = self._sanitize_secret_map(fields["extra_config"])
        if "git_auth" in fields:
            fields["git_auth_ref"] = self._secret_reference(fields.pop("git_auth"))
        self._assign_fields(project, fields, {"name", "type", "language", "framework", "extra_config", "git_repo_url", "git_auth_ref", "framework_files", "readme"})
        self._log("automation", "update_project", "auto_project", project.id, {"fields": self._public_field_names(fields)})
        return project

    def delete_auto_project(self, auto_project_id: int) -> AutoProject:
        project = self._soft_delete(AutoProject, auto_project_id)
        self._log("automation", "delete_project", "auto_project", project.id, {})
        return project

    def screen_auto_candidates(self, project_id: int, limit: int = 50) -> list[dict[str, Any]]:
        cases = list(
            self.session.scalars(
                select(TestCase)
                .where(TestCase.project_id == project_id, TestCase.status.in_(["confirmed", "ready", "draft"]), TestCase.is_deleted.is_(False))
                .order_by(TestCase.id)
                .limit(limit)
            )
        )
        if not cases:
            cases = list(
                self.session.scalars(
                    select(TestCase)
                    .where(TestCase.project_id == project_id, TestCase.is_deleted.is_(False))
                    .order_by(TestCase.id)
                    .limit(limit)
                )
            )
        return [{"case_id": case.id, "case_number": case.case_number, "title": case.title, "priority": case.priority, "score": 80} for case in cases]

    def generate_auto_framework_files(self, auto_project_id: int) -> dict[str, Any]:
        project = self._get(AutoProject, auto_project_id)
        files = {
            "pytest.ini": "[pytest]\naddopts = -q\n",
            "requirements.txt": "pytest\n",
            "README.md": f"# {project.name}\n\nGenerated placeholder automation framework.\n",
        }
        project.framework_files = files
        project.readme = files["README.md"]
        self._log("automation", "generate_framework", "auto_project", project.id, {"file_count": len(files)})
        return {"auto_project_id": project.id, "files": files, "file_count": len(files)}

    def generate_auto_cases(self, auto_project_id: int, source_case_ids: Iterable[int] | None = None) -> dict[str, Any]:
        project = self._get(AutoProject, auto_project_id)
        case_ids = list(source_case_ids or [item["case_id"] for item in self.screen_auto_candidates(project.project_id, limit=5)])
        created: list[AutoCaseFile] = []
        for case_id in case_ids:
            case = self._get(TestCase, case_id)
            content = self._render_auto_case_file(project, case)
            case_file = AutoCaseFile(
                auto_project_id=project.id,
                source_case_id=case.id,
                file_name=f"test_case_{case.id}.py",
                file_path=f"tests/test_case_{case.id}.py",
                content=content,
                case_count=1,
                automation_dsl={"case_id": case.id, "steps": case.steps},
            )
            self.session.add(case_file)
            created.append(case_file)
        self.session.flush()
        self._log("automation", "generate_cases", "auto_project", project.id, {"file_ids": [item.id for item in created]})
        return {"auto_project_id": project.id, "file_ids": [item.id for item in created], "count": len(created)}

    def list_auto_case_files(self, auto_project_id: int) -> list[AutoCaseFile]:
        return list(
            self.session.scalars(
                select(AutoCaseFile)
                .where(AutoCaseFile.auto_project_id == auto_project_id, AutoCaseFile.is_deleted.is_(False))
                .order_by(AutoCaseFile.id)
            )
        )

    def execute_auto_project(self, auto_project_id: int) -> AutoExecution:
        project = self._get(AutoProject, auto_project_id)
        files = self.list_auto_case_files(project.id)
        summary = {"total": sum(file.case_count for file in files), "passed": sum(file.case_count for file in files), "failed": 0}
        execution = AutoExecution(
            auto_project_id=project.id,
            status="passed",
            summary=summary,
            artifacts={"report": f"auto-execution-{project.id}.html"},
            log_excerpt="Placeholder automation execution completed.",
            duration_ms=100 + len(files) * 10,
        )
        self.session.add(execution)
        for file in files:
            file.last_result = {"status": "passed", "execution": "placeholder"}
        self.session.flush()
        self._log("automation", "execute_project", "auto_execution", execution.id, summary)
        return execution

    def get_auto_download_metadata(self, auto_project_id: int) -> dict[str, Any]:
        project = self._get(AutoProject, auto_project_id)
        files = self.list_auto_case_files(project.id)
        return {
            "auto_project_id": project.id,
            "archive_name": f"auto-project-{project.id}.zip",
            "file_count": len(files) + len(project.framework_files or {}),
            "case_file_ids": [file.id for file in files],
            "framework_files": sorted((project.framework_files or {}).keys()),
        }

    def create_perf_plan(self, project_id: int, name: str, description: str | None = None, **fields: Any) -> PerfPlan:
        self.get_project(project_id)
        plan = PerfPlan(
            project_id=project_id,
            source_document_id=fields.get("source_document_id"),
            name=name,
            description=description,
            requirement_item_ids_json=list(fields.get("requirement_item_ids") or []),
            target_assets_json=fields.get("target_assets") or {},
            target_doc=fields.get("target_doc"),
            plan_content=fields.get("plan_content"),
            plan_schema=fields.get("plan_schema"),
            jmx_script=fields.get("jmx_script"),
            status=fields.get("status", "draft"),
        )
        self.session.add(plan)
        self.session.flush()
        self._log("performance", "create_plan", "perf_plan", plan.id, {"project_id": project_id})
        return plan

    def list_perf_plans(self, project_id: int) -> list[PerfPlan]:
        return list(
            self.session.scalars(
                select(PerfPlan)
                .where(PerfPlan.project_id == project_id, PerfPlan.is_deleted.is_(False))
                .order_by(PerfPlan.id.desc())
            )
        )

    def update_perf_plan(self, plan_id: int, **fields: Any) -> PerfPlan:
        plan = self._get(PerfPlan, plan_id)
        if "requirement_item_ids" in fields:
            fields["requirement_item_ids_json"] = list(fields.pop("requirement_item_ids") or [])
        if "target_assets" in fields:
            fields["target_assets_json"] = fields.pop("target_assets") or {}
        self._assign_fields(plan, fields, {"name", "description", "source_document_id", "requirement_item_ids_json", "target_assets_json", "target_doc", "plan_content", "plan_schema", "jmx_script", "status"})
        self._log("performance", "update_plan", "perf_plan", plan.id, {"fields": self._public_field_names(fields)})
        return plan

    def delete_perf_plan(self, plan_id: int) -> PerfPlan:
        plan = self._soft_delete(PerfPlan, plan_id)
        self._log("performance", "delete_plan", "perf_plan", plan.id, {})
        return plan

    def generate_perf_structured_plan(self, plan_id: int) -> dict[str, Any]:
        plan = self._get(PerfPlan, plan_id)
        schema = {
            "stages": [
                {"name": "warmup", "users": 5, "duration_seconds": 60},
                {"name": "load", "users": 20, "duration_seconds": 300},
            ],
            "thresholds": {"p95_ms": 800, "error_rate": 0.01},
            "targets": plan.target_assets_json or {},
        }
        plan.plan_schema = schema
        plan.plan_content = "Placeholder performance plan with warmup and load stages."
        plan.status = "planned"
        self._log("performance", "generate_structured_plan", "perf_plan", plan.id, {})
        return schema

    def generate_perf_script(self, plan_id: int) -> dict[str, Any]:
        plan = self._get(PerfPlan, plan_id)
        script = "<jmeterTestPlan><hashTree><!-- placeholder deterministic JMX --></hashTree></jmeterTestPlan>"
        plan.jmx_script = script
        plan.status = "scripted"
        self._log("performance", "generate_script", "perf_plan", plan.id, {"script_type": "jmx"})
        return {"plan_id": plan.id, "script_type": "jmx", "content": script}

    def execute_perf_plan(self, plan_id: int) -> PerfResult:
        plan = self._get(PerfPlan, plan_id)
        summary = {"total_requests": 1200, "success_rate": 1.0, "p95_ms": 320, "avg_ms": 145}
        result = PerfResult(
            plan_id=plan.id,
            project_id=plan.project_id,
            status="completed",
            summary_data=summary,
            timeline_data=[{"second": 1, "rps": 20}, {"second": 2, "rps": 21}],
            error_details=[],
            artifacts={"jtl": f"perf-result-{plan.id}.jtl"},
            is_baseline=False,
            duration=60,
        )
        plan.status = "executed"
        self.session.add(result)
        self.session.flush()
        self._log("performance", "execute_plan", "perf_result", result.id, summary)
        return result

    def generate_performance_report(self, result_id: int, template_id: int | None = None) -> Report:
        result = self._get(PerfResult, result_id)
        plan = self._get(PerfPlan, result.plan_id)
        report = Report(
            project_id=result.project_id,
            name=f"{plan.name} Performance Report",
            type="performance",
            status="generated",
            related_module="performance",
            related_scope_json={"plan_id": plan.id, "result_id": result.id},
            requirement_item_ids_json=plan.requirement_item_ids_json or [],
            scope_snapshot={"plan": self._model_dict(plan), "result_id": result.id},
            data_snapshot={"summary": result.summary_data, "timeline": result.timeline_data, "errors": result.error_details},
            source_refs_json={"perf_plan_id": plan.id, "perf_result_id": result.id},
            content=self._render_perf_report_content(plan, result),
            template_id=template_id,
        )
        self.session.add(report)
        self.session.flush()
        self._log("performance", "generate_report", "report", report.id, {"result_id": result.id})
        return report

    def create_report_template(self, name: str, report_type: str = "comprehensive", sections: Iterable[Any] | None = None, **fields: Any) -> ReportTemplate:
        template = ReportTemplate(
            name=name,
            report_type=report_type,
            sections=list(sections or fields.get("sections") or []),
            is_default=bool(fields.get("is_default", False)),
            template_version=fields.get("template_version", "v1"),
        )
        self.session.add(template)
        self.session.flush()
        self._log("config", "create_report_template", "report_template", template.id, {"report_type": report_type})
        return template

    def list_report_templates(self, report_type: str | None = None) -> list[ReportTemplate]:
        stmt = select(ReportTemplate)
        if report_type:
            stmt = stmt.where(ReportTemplate.report_type == report_type)
        return list(self.session.scalars(stmt.order_by(ReportTemplate.id.desc())))

    def update_report_template(self, template_id: int, **fields: Any) -> ReportTemplate:
        template = self._get(ReportTemplate, template_id)
        if "sections" in fields and fields["sections"] is not None:
            fields["sections"] = list(fields["sections"])
        self._assign_fields(template, fields, {"name", "report_type", "sections", "is_default", "template_version"})
        self._log("config", "update_report_template", "report_template", template.id, {"fields": self._public_field_names(fields)})
        return template

    def delete_report_template(self, template_id: int) -> None:
        template = self._get(ReportTemplate, template_id)
        for report in self.session.scalars(select(Report).where(Report.template_id == template_id)):
            report.template_id = None
        self.session.flush()
        self.session.delete(template)
        self.session.flush()
        self._log("config", "delete_report_template", "report_template", template_id, {})

    def create_llm_config(self, name: str, model_name: str, **fields: Any) -> LlmConfig:
        config = LlmConfig(
            name=name,
            base_url=fields.get("base_url"),
            api_key_ref=self._secret_reference(fields.get("api_key_ref") or fields.get("api_key")),
            model_name=model_name,
            max_tokens=int(fields.get("max_tokens", 4096)),
            temperature=float(fields.get("temperature", 0.7)),
            is_default=bool(fields.get("is_default", False)),
            is_enabled=bool(fields.get("is_enabled", True)),
            module_binding=fields.get("module_binding") or {},
            sort_order=int(fields.get("sort_order", 0)),
        )
        self.session.add(config)
        self.session.flush()
        if config.is_default:
            self._set_only_default_llm(config.id)
        self._log("config", "create_llm_config", "llm_config", config.id, {"model_name": model_name})
        return config

    def list_llm_configs(self) -> list[dict[str, Any]]:
        return [self._llm_config_public_dict(config) for config in self.session.scalars(select(LlmConfig).order_by(LlmConfig.sort_order, LlmConfig.id))]

    def update_llm_config(self, config_id: int, **fields: Any) -> LlmConfig:
        config = self._get(LlmConfig, config_id)
        if "api_key" in fields:
            fields["api_key_ref"] = self._secret_reference(fields.pop("api_key"))
        if "api_key_ref" in fields:
            fields["api_key_ref"] = self._secret_reference(fields["api_key_ref"])
        self._assign_fields(config, fields, {"name", "base_url", "api_key_ref", "model_name", "max_tokens", "temperature", "is_default", "is_enabled", "module_binding", "sort_order"})
        if config.is_default:
            self._set_only_default_llm(config.id)
        self._log("config", "update_llm_config", "llm_config", config.id, {"fields": self._public_field_names(fields)})
        return config

    def delete_llm_config(self, config_id: int) -> None:
        config = self._get(LlmConfig, config_id)
        for usage in self.session.scalars(select(LlmUsage).where(LlmUsage.config_id == config_id)):
            self.session.delete(usage)
        self.session.flush()
        self.session.delete(config)
        self.session.flush()
        self._log("config", "delete_llm_config", "llm_config", config_id, {})

    def test_llm_config(self, config_id: int, module: str = "config") -> dict[str, Any]:
        config = self._get(LlmConfig, config_id)
        usage = LlmUsage(config_id=config.id, module=module, input_tokens=12, output_tokens=8, duration_ms=30)
        self.session.add(usage)
        self.session.flush()
        self._log("config", "test_llm_config", "llm_config", config.id, {"usage_id": usage.id})
        return {"config_id": config.id, "status": "ok" if config.is_enabled else "disabled", "model_name": config.model_name, "usage_id": usage.id}

    def llm_usage_statistics(self) -> dict[str, Any]:
        usages = list(self.session.scalars(select(LlmUsage)))
        return {
            "total_calls": len(usages),
            "input_tokens": sum(item.input_tokens for item in usages),
            "output_tokens": sum(item.output_tokens for item in usages),
            "by_module": self._count_by([item.module for item in usages]),
        }

    def list_prompt_templates(self) -> list[PromptTemplate]:
        return list(self.session.scalars(select(PromptTemplate).order_by(PromptTemplate.scene)))

    def update_prompt_template(self, template_id: int, **fields: Any) -> PromptTemplate:
        template = self._get(PromptTemplate, template_id)
        if "variables" in fields and fields["variables"] is not None:
            fields["variables"] = list(fields["variables"])
        self._assign_fields(template, fields, {"scene", "name", "content", "variables", "is_builtin"})
        self._log("config", "update_prompt_template", "prompt_template", template.id, {"fields": self._public_field_names(fields)})
        return template

    def test_prompt_template(self, template_id: int, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        template = self._get(PromptTemplate, template_id)
        rendered = template.content
        for key, value in (variables or {}).items():
            rendered = rendered.replace("{{" + key + "}}", str(value))
        self._log("config", "test_prompt_template", "prompt_template", template.id, {"variables": sorted((variables or {}).keys())})
        return {"template_id": template.id, "scene": template.scene, "rendered_preview": rendered[:500], "missing_variables": []}

    def search_db(self, keyword: str, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
        pattern = f"%{keyword}%"
        results: dict[str, list[dict[str, Any]]] = {}
        searchable = [
            ("projects", Project, [Project.name, Project.code]),
            ("requirements", RequirementItem, [RequirementItem.title, RequirementItem.summary]),
            ("test_cases", TestCase, [TestCase.title, TestCase.case_number]),
            ("api_libs", ApiTestLib, [ApiTestLib.name, ApiTestLib.description]),
            ("api_endpoints", ApiEndpoint, [ApiEndpoint.name, ApiEndpoint.path]),
            ("auto_projects", AutoProject, [AutoProject.name]),
            ("perf_plans", PerfPlan, [PerfPlan.name, PerfPlan.description]),
            ("reports", Report, [Report.name, Report.content]),
        ]
        for name, model, columns in searchable:
            stmt = select(model).where(or_(*[column.like(pattern) for column in columns]))
            rows = list(self.session.scalars(stmt.limit(limit)))
            results[name] = [self._model_dict_public(row) for row in rows]
        return results

    def list_operation_logs(self, module: str | None = None, limit: int = 100) -> list[OperationLog]:
        stmt = select(OperationLog)
        if module:
            stmt = stmt.where(OperationLog.module == module)
        return list(self.session.scalars(stmt.order_by(OperationLog.id.desc()).limit(limit)))

    def create_backup_snapshot(self, project_id: int | None = None, name: str | None = None) -> BackupSnapshot:
        scope = {"project_id": project_id, "created_at": self._now_iso()}
        point_stmt = select(TestPoint).where(TestPoint.is_deleted.is_(False))
        if project_id is not None:
            point_stmt = point_stmt.join(RequirementItem, RequirementItem.id == TestPoint.requirement_item_id).where(
                RequirementItem.project_id == project_id
            )
        data = {
            "projects": [self._model_dict(project) for project in self._select_active(Project, project_id)],
            "requirement_libs": [self._model_dict(lib) for lib in self._select_active(RequirementLib, project_id)],
            "documents": [self._model_dict(doc) for doc in self._select_active(RequirementDocument, project_id)],
            "requirement_items": [self._model_dict(item) for item in self._select_active(RequirementItem, project_id)],
            "test_points": [self._model_dict(point) for point in self.session.scalars(point_stmt)],
            "test_cases": [self._model_dict(case) for case in self._select_active(TestCase, project_id)],
            "api_test_libs": [self._model_dict_public(lib) for lib in self._select_active(ApiTestLib, project_id)],
            "api_endpoints": [
                self._model_dict_public(endpoint)
                for endpoint in self._select_children(ApiEndpoint, ApiTestLib, "lib_id", project_id)
            ],
            "api_test_cases": [
                self._model_dict_public(case)
                for case in self._select_children(ApiTestCase, ApiTestLib, "lib_id", project_id)
            ],
            "api_environments": [
                self._model_dict_public(env)
                for env in self._select_children(ApiEnvironment, ApiTestLib, "lib_id", project_id)
            ],
            "api_scenarios": [
                self._model_dict_public(scenario)
                for scenario in self._select_children(ApiScenario, ApiTestLib, "lib_id", project_id)
            ],
            "api_schedules": [
                self._model_dict_public(schedule)
                for schedule in self._select_children(ApiSchedule, ApiTestLib, "lib_id", project_id)
            ],
            "api_executions": [
                self._model_dict_public(execution)
                for execution in self._select_children(ApiExecution, ApiTestLib, "lib_id", project_id)
            ],
            "auto_projects": [self._model_dict_public(project) for project in self._select_active(AutoProject, project_id)],
            "auto_case_files": [
                self._model_dict_public(file)
                for file in self._select_children(AutoCaseFile, AutoProject, "auto_project_id", project_id)
            ],
            "auto_executions": [
                self._model_dict_public(execution)
                for execution in self._select_children(AutoExecution, AutoProject, "auto_project_id", project_id)
            ],
            "perf_plans": [self._model_dict_public(plan) for plan in self._select_active(PerfPlan, project_id)],
            "perf_results": [self._model_dict_public(result) for result in self._select_active(PerfResult, project_id)],
            "reports": [self._model_dict_public(report) for report in self._select_active(Report, project_id)],
            "report_templates": [self._model_dict_public(template) for template in self.session.scalars(select(ReportTemplate))],
            "llm_configs": [self._llm_config_public_dict(config) for config in self.session.scalars(select(LlmConfig))],
            "prompt_templates": [self._model_dict_public(template) for template in self.session.scalars(select(PromptTemplate))],
        }
        snapshot = BackupSnapshot(
            project_id=project_id,
            name=name or f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            scope_json=scope,
            data_json=data,
        )
        self.session.add(snapshot)
        self.session.flush()
        self._log("backup", "create_snapshot", "backup_snapshot", snapshot.id, scope)
        return snapshot

    def _assign_fields(self, model: Any, fields: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
        changed: dict[str, Any] = {}
        for key, value in fields.items():
            if key in allowed and value is not None and getattr(model, key) != value:
                setattr(model, key, value)
                changed[key] = value
        if changed:
            self.session.flush()
        return changed

    def _soft_delete(self, model: type[Any], item_id: int) -> Any:
        item = self._get(model, item_id)
        if hasattr(item, "is_deleted"):
            item.is_deleted = True
            self.session.flush()
            return item
        raise ValueError(f"{model.__name__} does not support soft delete")

    def _active_api_environment(self, lib_id: int) -> ApiEnvironment | None:
        return self.session.scalar(
            select(ApiEnvironment)
            .where(ApiEnvironment.lib_id == lib_id, ApiEnvironment.is_deleted.is_(False), ApiEnvironment.is_active.is_(True))
            .order_by(ApiEnvironment.id.desc())
            .limit(1)
        )

    def _set_only_default_llm(self, config_id: int) -> None:
        for config in self.session.scalars(select(LlmConfig)):
            config.is_default = config.id == config_id
        self.session.flush()

    def _select_children(self, model: type[Any], parent_model: type[Any], parent_key: str, project_id: int | None) -> list[Any]:
        stmt: Select[Any] = select(model).join(parent_model, parent_model.id == getattr(model, parent_key))
        if hasattr(model, "is_deleted"):
            stmt = stmt.where(model.is_deleted.is_(False))
        if project_id is not None:
            stmt = stmt.where(parent_model.project_id == project_id)
        return list(self.session.scalars(stmt))

    def _llm_config_public_dict(self, config: LlmConfig) -> dict[str, Any]:
        data = self._model_dict(config)
        data["api_key_ref"] = self._mask_secret_ref(data.get("api_key_ref"))
        return data

    def _model_dict_public(self, model: Any) -> dict[str, Any]:
        return self._sanitize_secret_map(self._model_dict(model))

    def _public_field_names(self, fields: dict[str, Any]) -> list[str]:
        return [key for key in fields if not self._is_secret_key(key)]

    def _secret_reference(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        text = str(value)
        if text.startswith("ref:"):
            return text
        return f"ref:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"

    def _mask_secret_ref(self, value: Any) -> Any:
        if value in (None, ""):
            return value
        text = str(value)
        if text.startswith("ref:"):
            return f"{text[:7]}***"
        return "***"

    def _sanitize_secret_map(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if self._is_secret_key(str(key)):
                    sanitized[key] = self._secret_reference(item)
                else:
                    sanitized[key] = self._sanitize_secret_map(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_secret_map(item) for item in value]
        return value

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        lowered = key.lower()
        return any(marker in lowered for marker in ("api_key", "apikey", "token", "cookie", "secret", "password", "git_auth"))

    @staticmethod
    def _placeholder_api_cases(endpoint: ApiEndpoint) -> list[dict[str, Any]]:
        return [
            {
                "name": f"{endpoint.name} success",
                "category": "happy_path",
                "request_headers": {},
                "request_query": {},
                "request_body": {},
                "expected_status": 200,
                "assertions": [{"type": "status_code", "expected": 200}],
                "status": "ready",
            },
            {
                "name": f"{endpoint.name} validation",
                "category": "negative",
                "request_headers": {},
                "request_query": {"invalid": True},
                "request_body": {},
                "expected_status": 400,
                "assertions": [{"type": "status_code", "expected": 400}],
                "status": "ready",
            },
        ]

    @staticmethod
    def _render_auto_case_file(project: AutoProject, case: TestCase) -> str:
        title = case.title.replace('"', '\\"')
        return (
            "def test_generated_case():\n"
            f"    \"\"\"{title}\"\"\"\n"
            f"    steps = {case.steps!r}\n"
            "    assert steps is not None\n"
        )

    @staticmethod
    def _render_perf_report_content(plan: PerfPlan, result: PerfResult) -> str:
        summary = result.summary_data
        return (
            f"# {plan.name} Performance Report\n\n"
            f"- status: {result.status}\n"
            f"- total_requests: {summary.get('total_requests', 0)}\n"
            f"- success_rate: {summary.get('success_rate', 0)}\n"
            f"- p95_ms: {summary.get('p95_ms', 0)}\n"
        )

    def _get(self, model: type[Any], item_id: int) -> Any:
        item = self.session.get(model, item_id)
        if item is None or getattr(item, "is_deleted", False):
            raise NotFoundError(f"{model.__name__}({item_id}) not found")
        return item

    def _next_code(self, prefix: str, model: type[Any], field_name: str = "code") -> str:
        count = self.session.scalar(select(func.count()).select_from(model)) or 0
        return self._unique_code(prefix, model, field_name, count + 1)

    def _unique_code(self, prefix: str, model: type[Any], field_name: str, start: int) -> str:
        count = start - 1
        candidate = f"{prefix}-{start:04d}"
        field = getattr(model, field_name)
        while self.session.scalar(select(model).where(field == candidate).limit(1)) is not None:
            count += 1
            candidate = f"{prefix}-{count + 1:04d}"
        return candidate

    def _create_job(
        self,
        project_id: int,
        document_id: int | None,
        requirement_item_id: int | None,
        job_type: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
    ) -> GenerationJob:
        job = GenerationJob(
            project_id=project_id,
            document_id=document_id,
            requirement_item_id=requirement_item_id,
            job_type=job_type,
            status="succeeded",
            progress=100,
            input_payload=input_payload,
            output_payload=output_payload,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def _update_round_counts(self, round_id: int) -> None:
        round_ = self._get(TestRound, round_id)
        statuses = list(self.session.scalars(select(Execution.status).where(Execution.round_id == round_id)))
        round_.total_count = len(statuses)
        round_.pass_count = statuses.count("pass")
        round_.fail_count = statuses.count("fail")
        round_.block_count = statuses.count("blocked")
        round_.skip_count = statuses.count("skipped")

    def _build_report_data(self, project_id: int, requirement_item_ids: list[int]) -> dict[str, Any]:
        item_stmt = select(RequirementItem).where(RequirementItem.project_id == project_id, RequirementItem.is_deleted.is_(False))
        case_stmt = select(TestCase).where(TestCase.project_id == project_id, TestCase.is_deleted.is_(False))
        execution_stmt = select(Execution).where(Execution.project_id == project_id)
        defect_stmt = select(Defect).where(Defect.project_id == project_id)
        if requirement_item_ids:
            item_stmt = item_stmt.where(RequirementItem.id.in_(requirement_item_ids))
            case_stmt = case_stmt.where(TestCase.requirement_item_id.in_(requirement_item_ids))
            execution_stmt = execution_stmt.where(Execution.requirement_item_id.in_(requirement_item_ids))
            defect_stmt = defect_stmt.where(Defect.requirement_item_id.in_(requirement_item_ids))

        items = list(self.session.scalars(item_stmt))
        cases = list(self.session.scalars(case_stmt))
        executions = list(self.session.scalars(execution_stmt))
        defects = list(self.session.scalars(defect_stmt))
        source_document_ids = sorted({item.document_id for item in items})
        status_counts = self._count_by([execution.status for execution in executions])
        return {
            "summary_metrics": {
                "requirement_item_count": len(items),
                "test_case_count": len(cases),
                "execution_count": len(executions),
                "defect_count": len(defects),
            },
            "execution_summary": status_counts,
            "defect_summary": self._count_by([defect.status for defect in defects]),
            "source_document_ids": source_document_ids,
            "source_refs": {
                "requirement_item_ids": [item.id for item in items],
                "test_case_ids": [case.id for case in cases],
                "execution_ids": [execution.id for execution in executions],
                "defect_ids": [defect.id for defect in defects],
            },
        }

    def _render_report_content(self, name: str, data: dict[str, Any]) -> str:
        metrics = data["summary_metrics"]
        return (
            f"# {name}\n\n"
            f"- 需求项数量：{metrics['requirement_item_count']}\n"
            f"- 测试用例数量：{metrics['test_case_count']}\n"
            f"- 执行记录数量：{metrics['execution_count']}\n"
            f"- 缺陷数量：{metrics['defect_count']}\n"
        )

    def _select_active(self, model: type[Any], project_id: int | None = None) -> list[Any]:
        stmt: Select[Any] = select(model)
        if hasattr(model, "is_deleted"):
            stmt = stmt.where(model.is_deleted.is_(False))
        if project_id is not None and hasattr(model, "project_id"):
            stmt = stmt.where(model.project_id == project_id)
        elif project_id is not None and model is Project:
            stmt = stmt.where(Project.id == project_id)
        return list(self.session.scalars(stmt))

    def _log(self, module: str, action: str, target_type: str, target_id: int, detail: dict[str, Any] | None = None) -> None:
        self.session.add(
            OperationLog(
                module=module,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=detail or {},
            )
        )

    @staticmethod
    def _placeholder_requirement_item(document: RequirementDocument, blocks: list[RequirementDocumentBlock]) -> dict[str, Any]:
        text = blocks[0].normalized_text if blocks else document.raw_content
        return {
            "title": document.name,
            "summary": (text or document.name)[:500],
            "module": "主流程",
            "actor": "测试用户",
            "goal": "根据原始需求材料完成可验证的业务能力。",
            "business_rules": ["占位拆解结果，等待真实 AI/规则解析器替换。"],
            "source_anchor_ids": [blocks[0].block_key] if blocks else [],
            "confidence": 0.65,
        }

    @staticmethod
    def _placeholder_test_points(item: RequirementItem) -> list[dict[str, Any]]:
        return [
            {
                "title": f"{item.title} - 主流程验证",
                "point_type": "happy_path",
                "target": "验证需求描述中的核心成功路径可以完成。",
                "priority": "P1",
                "suggested_method": "manual",
            },
            {
                "title": f"{item.title} - 异常与边界验证",
                "point_type": "boundary",
                "target": "验证异常输入、边界条件和限制规则有明确反馈。",
                "priority": "P2",
                "suggested_method": "manual",
            },
        ]

    @staticmethod
    def _placeholder_test_cases(item: RequirementItem, points: list[TestPoint], generation_mode: str) -> list[dict[str, Any]]:
        cases = []
        for point in points:
            cases.append(
                {
                    "test_point_id": point.id,
                    "title": f"验证{point.title}",
                    "case_type": "functional" if point.point_type != "boundary" else "boundary",
                    "precondition": "测试环境可用，测试账号和基础数据已准备。",
                    "steps": [
                        {"step": 1, "action": "进入被测功能入口。"},
                        {"step": 2, "action": f"按需求执行：{item.title}。"},
                        {"step": 3, "action": "观察页面、接口或数据状态变化。"},
                    ],
                    "expected_result": point.target or "实际结果符合需求项和测试点目标。",
                    "priority": point.priority,
                    "tags": [generation_mode, point.point_type],
                }
            )
        return cases

    @staticmethod
    def _summary(text: str, limit: int = 300) -> str:
        clean = " ".join(text.split())
        return clean[:limit]

    @staticmethod
    def _count_by(values: Iterable[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        for value in values:
            result[value] = result.get(value, 0) + 1
        return result

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _model_dict(model: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for column in model.__table__.columns:
            value = getattr(model, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            data[column.name] = value
        return data
