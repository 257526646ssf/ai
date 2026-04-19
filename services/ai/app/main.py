import os
from typing import Any

from fastapi import FastAPI
from pydantic import ValidationError

from .openai_client import OpenAIClient
from .schemas import (
    AnalyzeFailureRequest,
    AnalyzeFailureResponse,
    GenerateCaseRequest,
    GenerateCaseResponse,
    ParseAssetRequest,
)

app = FastAPI(title="AI Service", version="0.1.0")


def _test_case_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "module": {"type": "string"},
                        "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                        "type": {
                            "type": "string",
                            "enum": ["functional", "boundary", "exception", "ui", "performance", "compatibility"],
                        },
                        "preconditions": {"type": "array", "items": {"type": "string"}},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "order": {"type": "number"},
                                    "action": {"type": "string"},
                                    "expected": {"type": "string"},
                                    "selector": {"type": ["string", "null"]},
                                },
                                "required": ["order", "action", "expected", "selector"],
                            },
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "source": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "title",
                        "module",
                        "priority",
                        "type",
                        "preconditions",
                        "steps",
                        "tags",
                        "source",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["cases"],
        "additionalProperties": False,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse")
def parse_asset(payload: ParseAssetRequest) -> dict[str, Any]:
    return {
        "assetId": payload.asset_id,
        "projectId": payload.project_id,
        "type": payload.asset_type,
        "summary": payload.text or "No text provided; parsed with placeholder pipeline.",
        "ocrText": payload.text or "",
        "pages": 1,
    }


@app.post("/generate", response_model=GenerateCaseResponse)
def generate_cases(payload: GenerateCaseRequest) -> GenerateCaseResponse:
    prompt = (
        "Generate executable browser test cases from requirement summary. "
        "Use atomic steps, explicit expected outcomes, and include selectors when possible."
    )

    user_prompt = f"Requirement: {payload.requirement_summary}\nModules: {payload.focus_modules}"

    if os.getenv("OPENAI_API_KEY"):
        client = OpenAIClient()
        generated = client.generate_json(prompt, user_prompt, _test_case_schema())
    else:
        generated = {
            "cases": [
                {
                    "title": "User logs in with valid credentials",
                    "module": "auth",
                    "priority": "P0",
                    "type": "functional",
                    "preconditions": ["User account exists"],
                    "steps": [
                        {
                            "order": 1,
                            "action": "Open /login page",
                            "expected": "Login form is visible",
                            "selector": None,
                        },
                        {
                            "order": 2,
                            "action": "Fill username and password",
                            "expected": "Inputs contain values",
                            "selector": "input[name='username']",
                        },
                    ],
                    "tags": ["smoke", "auth"],
                    "source": "ai",
                    "confidence": 0.85,
                }
            ]
        }

    try:
        return GenerateCaseResponse.model_validate(generated)
    except ValidationError as exc:
        raise ValueError(f"Generated content failed schema validation: {exc}") from exc


@app.post("/analyze-failure", response_model=AnalyzeFailureResponse)
def analyze_failure(payload: AnalyzeFailureRequest) -> AnalyzeFailureResponse:
    log = payload.error_log.lower()
    if "selector" in log or "not found" in log:
        return AnalyzeFailureResponse(category="selector_not_found", suggestion="Update locator with stable data-testid.")
    if "assert" in log:
        return AnalyzeFailureResponse(category="assertion_failed", suggestion="Adjust assertions and verify expected copy.")
    if "timeout" in log:
        return AnalyzeFailureResponse(category="network_timeout", suggestion="Increase timeout or stabilize network dependency.")
    if "crash" in log:
        return AnalyzeFailureResponse(category="page_crash", suggestion="Inspect browser console and stack traces.")
    return AnalyzeFailureResponse(category="env_error", suggestion="Check env vars and base URL setup.")
