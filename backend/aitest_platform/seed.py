from __future__ import annotations

from sqlalchemy import select

from aitest_platform.db import init_db, session_scope
from aitest_platform.models import LlmConfig, Project, PromptTemplate, ReportTemplate
from aitest_platform.repositories import AitestRepository


def seed_demo_data() -> dict[str, int]:
    init_db()
    with session_scope() as session:
        existing = session.scalar(select(Project).where(Project.code == "PRJ-DEMO"))
        if existing:
            return {"project_id": existing.id}

        repo = AitestRepository(session)
        project = repo.create_project(
            code="PRJ-DEMO",
            name="AI 测试平台 Demo 项目",
            description="本地优先数据层演示项目，用于 API smoke 和前端替换 mock 数据。",
            owner_name="local",
        )
        lib = repo.create_requirement_lib(project.id, "默认需求库", "承载需求文档、需求项、测试点和用例主链。")
        document = repo.create_requirement_document(
            project_id=project.id,
            lib_id=lib.id,
            name="登录与权限需求",
            source_type="text",
            raw_content="用户输入正确账号密码后可以登录系统；连续输错密码应提示错误并限制频繁尝试；未登录用户不能访问受保护页面。",
        )
        repo.parse_requirement_document(document.id)
        repo.extract_requirement_items_placeholder(
            document.id,
            [
                {
                    "title": "用户账号密码登录",
                    "summary": "用户使用正确账号密码登录系统，并进入有权限的默认页面。",
                    "module": "登录",
                    "actor": "普通用户",
                    "goal": "完成身份认证并进入系统。",
                    "preconditions": ["用户账号存在且状态正常"],
                    "business_rules": ["账号密码正确时登录成功", "登录成功后建立会话"],
                    "permissions": ["未登录用户不能访问受保护页面"],
                    "confidence": 0.88,
                },
                {
                    "title": "登录失败与频控提示",
                    "summary": "密码错误时给出明确提示，并对频繁失败尝试进行限制。",
                    "module": "登录",
                    "actor": "普通用户",
                    "goal": "保护账号安全并提供可理解的失败反馈。",
                    "exceptions": ["密码错误", "频繁尝试"],
                    "business_rules": ["连续失败达到阈值后限制继续尝试"],
                    "confidence": 0.82,
                },
            ],
        )

        requirement_items = lib.requirement_items
        for item in requirement_items:
            repo.confirm_requirement_item(item.id)
            repo.generate_test_points(item.id)
            repo.generate_test_cases(item.id, generation_mode="smoke")

        first_case = requirement_items[0].test_cases[0]
        round_ = repo.create_test_round(project.id, "Demo 第一轮冒烟", requirement_item_id=requirement_items[0].id)
        repo.create_execution_record(first_case.id, "pass", round_id=round_.id, pass_remark="Demo 数据通过")
        report = repo.generate_report_snapshot(project.id, "Demo 综合测试报告")
        backup = repo.create_backup_snapshot(project.id, "Demo 初始备份")

        session.add_all(
            [
                ReportTemplate(
                    name="默认综合报告模板",
                    report_type="comprehensive",
                    sections=[
                        {"title": "概览", "enabled": True},
                        {"title": "执行摘要", "enabled": True},
                        {"title": "缺陷风险", "enabled": True},
                    ],
                    is_default=True,
                ),
                PromptTemplate(
                    scene="req_extract_placeholder",
                    name="需求项拆解占位模板",
                    content="基于原始需求材料拆解结构化需求项，保留来源锚点。",
                    variables=["document", "blocks"],
                    is_builtin=True,
                ),
                LlmConfig(
                    name="未配置模型",
                    base_url=None,
                    api_key_ref=None,
                    model_name="placeholder",
                    is_default=True,
                    is_enabled=False,
                    module_binding={"requirement": True, "testcase": True, "report": True},
                ),
            ]
        )

        return {
            "project_id": project.id,
            "lib_id": lib.id,
            "document_id": document.id,
            "report_id": report.id,
            "backup_id": backup.id,
            "item_id_count": len(requirement_items),
        }


if __name__ == "__main__":
    print(seed_demo_data())
