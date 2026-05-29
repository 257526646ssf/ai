from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None
    trace_id: str


class PageQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200, alias="pageSize")


class PageResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    list: list[dict[str, Any]]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")


class WritePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class ChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None


class RestorePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: dict[str, Any] = Field(default_factory=dict)
