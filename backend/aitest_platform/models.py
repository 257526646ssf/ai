from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aitest_platform.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class Project(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "project_app"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_name: Mapped[str | None] = mapped_column(String(128))

    requirement_libs: Mapped[list[RequirementLib]] = relationship(back_populates="project")
    documents: Mapped[list[RequirementDocument]] = relationship(back_populates="project")
    requirement_items: Mapped[list[RequirementItem]] = relationship(back_populates="project")


class RequirementLib(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "requirement_lib"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    brain_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    project: Mapped[Project] = relationship(back_populates="requirement_libs")
    documents: Mapped[list[RequirementDocument]] = relationship(back_populates="lib")
    requirement_items: Mapped[list[RequirementItem]] = relationship(back_populates="lib")


class RequirementDocument(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "requirement_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("requirement_lib.id"), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_file_name: Mapped[str | None] = mapped_column(String(255))
    source_file_path: Mapped[str | None] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)
    parser_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    parser_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="documents")
    lib: Mapped[RequirementLib] = relationship(back_populates="documents")
    blocks: Mapped[list[RequirementDocumentBlock]] = relationship(back_populates="document")
    requirement_items: Mapped[list[RequirementItem]] = relationship(back_populates="document")


class RequirementDocumentBlock(Base):
    __tablename__ = "requirement_document_block"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("requirement_document.id"), nullable=False, index=True)
    block_key: Mapped[str] = mapped_column(String(128), nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    page_no: Mapped[int | None] = mapped_column(Integer)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata_json", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[RequirementDocument] = relationship(back_populates="blocks")


class RequirementItem(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "requirement_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("requirement_lib.id"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("requirement_document.id"), nullable=False, index=True)
    item_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    module: Mapped[str | None] = mapped_column(String(128))
    actor: Mapped[str | None] = mapped_column(String(128))
    goal: Mapped[str | None] = mapped_column(Text)
    preconditions_json: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    business_rules_json: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    state_transitions_json: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    exceptions_json: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    permissions_json: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    non_functional_json: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    priority: Mapped[str] = mapped_column(String(8), default="P2", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    granularity_flag: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    source_anchor_ids: Mapped[list[Any] | None] = mapped_column(JSON)
    case_status: Mapped[str] = mapped_column(String(32), default="not_generated", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="requirement_items")
    lib: Mapped[RequirementLib] = relationship(back_populates="requirement_items")
    document: Mapped[RequirementDocument] = relationship(back_populates="requirement_items")
    test_points: Mapped[list[TestPoint]] = relationship(back_populates="requirement_item")
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="requirement_item")


class TestPoint(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_item_id: Mapped[int] = mapped_column(ForeignKey("requirement_item.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    point_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(8), default="P2", nullable=False)
    suggested_method: Mapped[str | None] = mapped_column(String(48), index=True)
    coverage_status: Mapped[str] = mapped_column(String(32), default="todo", nullable=False, index=True)
    source_anchor_ids: Mapped[list[Any] | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    has_generated_cases: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    requirement_item: Mapped[RequirementItem] = relationship(back_populates="test_points")
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="test_point")


class TestCase(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("requirement_lib.id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_document.id"), index=True)
    requirement_item_id: Mapped[int] = mapped_column(ForeignKey("requirement_item.id"), nullable=False, index=True)
    test_point_id: Mapped[int | None] = mapped_column(ForeignKey("test_point.id"), index=True)
    case_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    case_level: Mapped[str] = mapped_column(String(32), default="requirement_item", nullable=False)
    case_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    precondition: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[Any] | str] = mapped_column(JSON, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(8), default="P2", nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    source_anchor_ids: Mapped[list[Any] | None] = mapped_column(JSON)
    evidence_type: Mapped[str] = mapped_column(String(32), default="original", nullable=False)
    generation_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    directory_path: Mapped[str] = mapped_column(String(512), default="/", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    requirement_item: Mapped[RequirementItem] = relationship(back_populates="test_cases")
    test_point: Mapped[TestPoint | None] = relationship(back_populates="test_cases")
    executions: Mapped[list[Execution]] = relationship(back_populates="case")


class GenerationJob(TimestampMixin, Base):
    __tablename__ = "generation_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_document.id"), index=True)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_item.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)


class TestRound(TimestampMixin, Base):
    __tablename__ = "test_round"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_item.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_document.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    block_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Execution(Base):
    __tablename__ = "execution_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    lib_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_lib.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_document.id"), index=True)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_item.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False, index=True)
    round_id: Mapped[int | None] = mapped_column(ForeignKey("test_round.id"), index=True)
    executor_type: Mapped[str] = mapped_column(String(48), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actual_result: Mapped[str | None] = mapped_column(Text)
    block_reason: Mapped[str | None] = mapped_column(Text)
    skip_reason: Mapped[str | None] = mapped_column(Text)
    pass_remark: Mapped[str | None] = mapped_column(Text)
    execution_time: Mapped[int | None] = mapped_column(Integer)
    ai_analysis: Mapped[str | None] = mapped_column(Text)
    request_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    artifact_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[TestCase] = relationship(back_populates="executions")


class Defect(TimestampMixin, Base):
    __tablename__ = "defect"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    defect_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("execution_record.id"), index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("test_case.id"), index=True)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_item.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_result: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    remark: Mapped[str | None] = mapped_column(Text)


class ApiTestLib(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "api_test_lib"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_document.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    import_source: Mapped[str | None] = mapped_column(String(64))
    latest_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiEndpoint(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "api_endpoint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("api_test_lib.id"), nullable=False, index=True)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_item.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    headers_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    query_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    body_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text)


class ApiTestCase(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "api_test_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("api_endpoint.id"), nullable=False, index=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("api_test_lib.id"), nullable=False, index=True)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_item.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="contract", nullable=False, index=True)
    request_headers: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_query: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_body: Mapped[dict[str, Any] | list[Any] | str | None] = mapped_column(JSON)
    content_type: Mapped[str] = mapped_column(String(128), default="application/json", nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    assertions: Mapped[list[Any] | None] = mapped_column(JSON)
    pre_script: Mapped[str | None] = mapped_column(Text)
    post_script: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ApiEnvironment(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "api_environment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("api_test_lib.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ApiScenario(TimestampMixin, Base):
    __tablename__ = "api_scenario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("api_test_lib.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    nodes: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    edges: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    data_mappings: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ApiSchedule(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "api_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("api_test_lib.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ApiExecution(Base):
    __tablename__ = "api_execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lib_id: Mapped[int] = mapped_column(ForeignKey("api_test_lib.id"), nullable=False, index=True)
    endpoint_id: Mapped[int | None] = mapped_column(ForeignKey("api_endpoint.id"), index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("api_test_case.id"), index=True)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("api_environment.id"), index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("api_scenario.id"), index=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("api_schedule.id"), index=True)
    run_type: Mapped[str] = mapped_column(String(48), default="case", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    assertion_results: Mapped[list[Any] | None] = mapped_column(JSON)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AutoProject(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "auto_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(48), nullable=False)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    extra_config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    git_repo_url: Mapped[str | None] = mapped_column(String(512))
    git_auth_ref: Mapped[str | None] = mapped_column(String(255))
    framework_files: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    readme: Mapped[str | None] = mapped_column(Text)


class AutoCaseFile(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "auto_case_file"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    auto_project_id: Mapped[int] = mapped_column(ForeignKey("auto_project.id"), nullable=False, index=True)
    source_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_case.id"), index=True)
    source_api_case_id: Mapped[int | None] = mapped_column(ForeignKey("api_test_case.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    automation_dsl: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AutoExecution(Base):
    __tablename__ = "auto_execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    auto_project_id: Mapped[int] = mapped_column(ForeignKey("auto_project.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    log_excerpt: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PerfPlan(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "perf_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_document.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    requirement_item_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    target_assets_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    target_doc: Mapped[str | None] = mapped_column(Text)
    plan_content: Mapped[str | None] = mapped_column(Text)
    plan_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    jmx_script: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)


class PerfResult(Base):
    __tablename__ = "perf_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("perf_plan.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False, index=True)
    summary_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    timeline_data: Mapped[list[Any] | None] = mapped_column(JSON)
    error_details: Mapped[list[Any] | None] = mapped_column(JSON)
    raw_data_path: Mapped[str | None] = mapped_column(Text)
    artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration: Mapped[int | None] = mapped_column(Integer)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ReportTemplate(TimestampMixin, Base):
    __tablename__ = "report_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), default="comprehensive", nullable=False)
    sections: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)


class Report(Base):
    __tablename__ = "report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="generated", nullable=False)
    related_module: Mapped[str | None] = mapped_column(String(64))
    related_scope_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    requirement_item_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    source_document_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    scope_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    data_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_refs_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("report_template.id"))
    template_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    ai_summary_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportTodo(TimestampMixin, Base):
    __tablename__ = "report_todo"
    __table_args__ = (UniqueConstraint("report_id", "risk_key", name="uq_report_todo_report_risk"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_app.id"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"), nullable=False, index=True)
    risk_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="todo", nullable=False, index=True)
    source_refs_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    risk_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    assignee: Mapped[str | None] = mapped_column(String(128))
    due_at: Mapped[str | None] = mapped_column(String(64))


class LlmConfig(TimestampMixin, Base):
    __tablename__ = "llm_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512))
    api_key_ref: Mapped[str | None] = mapped_column(String(255))
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    module_binding: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("llm_config.id"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PromptTemplate(TimestampMixin, Base):
    __tablename__ = "prompt_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str] | None] = mapped_column(JSON)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OperationLog(Base):
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict[str, Any] | str | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BackupSnapshot(Base):
    __tablename__ = "backup_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project_app.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("idx_requirement_lib_project_name", RequirementLib.project_id, RequirementLib.name)
Index("idx_requirement_item_lib_status", RequirementItem.lib_id, RequirementItem.status)
Index("idx_test_round_project_status", TestRound.project_id, TestRound.status)
Index("idx_report_project_type", Report.project_id, Report.type)
Index("idx_report_todo_project_status", ReportTodo.project_id, ReportTodo.status)
Index("idx_api_case_lib_endpoint", ApiTestCase.lib_id, ApiTestCase.endpoint_id)
Index("idx_api_execution_lib_status", ApiExecution.lib_id, ApiExecution.status)
Index("idx_auto_file_project_path", AutoCaseFile.auto_project_id, AutoCaseFile.file_path)
Index("idx_perf_result_plan_status", PerfResult.plan_id, PerfResult.status)
