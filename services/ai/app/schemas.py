from pydantic import BaseModel, Field


class ParseAssetRequest(BaseModel):
    asset_id: str
    project_id: str
    asset_type: str = Field(pattern="^(prototype|document)$")
    text: str | None = None


class GenerateCaseRequest(BaseModel):
    project_id: str
    requirement_summary: str
    focus_modules: list[str] = []


class Step(BaseModel):
    order: int
    action: str
    expected: str
    selector: str | None = None


class TestCaseOut(BaseModel):
    title: str
    module: str
    priority: str
    type: str
    preconditions: list[str]
    steps: list[Step]
    tags: list[str]
    source: str = "ai"
    confidence: float


class GenerateCaseResponse(BaseModel):
    cases: list[TestCaseOut]


class AnalyzeFailureRequest(BaseModel):
    execution_id: str
    error_log: str


class AnalyzeFailureResponse(BaseModel):
    category: str
    suggestion: str
