from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MemoryStore:
    """Temporary repository-compatible store until the data worker lands."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.counters: dict[str, int] = defaultdict(int)
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        project = self.create(
            "projects",
            {
                "name": "默认项目",
                "description": "第一轮 API 占位项目",
                "status": "active",
            },
        )
        self.create(
            "report_templates",
            {
                "name": "综合测试报告模板",
                "type": "comprehensive",
                "sections": ["overview", "coverage", "executions", "defects", "risks"],
                "enabled": True,
            },
        )
        self.create(
            "prompt_templates",
            {
                "name": "测试用例生成 Prompt",
                "module": "test_case",
                "content": "基于需求项、测试点和约束生成结构化测试用例。",
                "enabled": True,
            },
        )
        self.create(
            "llm_configs",
            {
                "name": "未配置模型",
                "provider": "openai-compatible",
                "model": "placeholder",
                "base_url": "",
                "is_default": True,
                "enabled": False,
            },
        )
        self.create("requirement_libs", {"project_id": project["id"], "name": "默认需求库"})

    def create(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.counters[table] += 1
        item_id = payload.get("id") or f"{table.rstrip('s').replace('_', '-')}-{self.counters[table]}"
        item = {
            "id": item_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            **deepcopy(payload),
            "id": item_id,
        }
        self.tables[table][item_id] = item
        return deepcopy(item)

    def list(
        self,
        table: str,
        *,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        items = list(self.tables[table].values())
        for key, value in (filters or {}).items():
            if value is not None:
                items = [item for item in items if str(item.get(key)) == str(value)]
        total = len(items)
        start = (page - 1) * page_size
        return {"list": deepcopy(items[start : start + page_size]), "total": total, "page": page, "pageSize": page_size}

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        item = self.tables[table].get(item_id)
        return deepcopy(item) if item else None

    def update(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        item = self.tables[table].get(item_id)
        if not item:
            return None
        clean_payload = {key: value for key, value in payload.items() if value is not None}
        item.update(deepcopy(clean_payload))
        item["updated_at"] = now_iso()
        return deepcopy(item)

    def delete(self, table: str, item_id: str) -> bool:
        item = self.tables[table].get(item_id)
        if not item:
            return False
        item["deleted"] = True
        item["updated_at"] = now_iso()
        return True

    def create_job(self, job_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.create(
            "generation_jobs",
            {
                "job_type": job_type,
                "status": "completed",
                "progress": 100,
                "input": payload or {},
                "result": {
                    "placeholder": True,
                    "summary": f"{job_type} finished with structured placeholder output.",
                },
            },
        )

    def log(self, module: str, action: str, target_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
        self.create(
            "operation_logs",
            {
                "module": module,
                "action": action,
                "target_id": target_id,
                "detail": detail or {},
            },
        )

    def backup(self) -> dict[str, Any]:
        return {
            "version": "v2-round1",
            "created_at": now_iso(),
            "tables": deepcopy(dict(self.tables)),
        }

    def search(self, keyword: str, tables: list[str] | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        scope = tables or list(self.tables.keys())
        lowered = keyword.lower()
        for table in scope:
            for item in self.tables[table].values():
                haystack = " ".join(str(value) for value in item.values()).lower()
                if lowered in haystack:
                    results.append({"type": table, "id": item["id"], "title": item.get("name") or item.get("title") or item["id"], "record": deepcopy(item)})
        return results


store = MemoryStore()

