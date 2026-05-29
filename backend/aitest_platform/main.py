from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from aitest_platform.api.compat import patch_starlette_router_for_fastapi

patch_starlette_router_for_fastapi()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute

from aitest_platform.api.router import router as api_router


def envelope(data: Any, trace_id: str, message: str = "ok", code: int = 0) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data, "trace_id": trace_id}


def response_headers(headers: dict[str, str] | Any) -> dict[str, str]:
    return {key: value for key, value in dict(headers).items() if key.lower() != "content-length"}


class UnifiedResponseRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            trace_id = getattr(request.state, "trace_id", str(uuid4()))
            response = await original_handler(request)
            if isinstance(response, StreamingResponse):
                response.headers["X-Trace-Id"] = trace_id
                return response
            if not isinstance(response, JSONResponse):
                return response

            body = getattr(response, "body", b"")
            if not body:
                payload: Any = None
            else:
                import json

                payload = json.loads(body)
            if isinstance(payload, dict) and {"code", "message", "data", "trace_id"}.issubset(payload.keys()):
                return response
            wrapped = envelope(payload, trace_id)
            return JSONResponse(content=wrapped, status_code=response.status_code, headers=response_headers(response.headers))

        return custom_handler


def create_app() -> FastAPI:
    from aitest_platform.db.session import init_db

    init_db()

    app = FastAPI(
        title="AI Test Platform API",
        version="0.1.0-round1",
        description="Round 1 FastAPI API layer for the AI testing platform.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):[0-9]+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.router.route_class = UnifiedResponseRoute

    @app.middleware("http")
    async def attach_trace_id(request: Request, call_next):
        request.state.trace_id = request.headers.get("X-Trace-Id") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        content_type = response.headers.get("content-type", "")
        if request.url.path == app.openapi_url or "application/json" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if not body:
            payload: Any = None
        else:
            payload = json.loads(body)
        if isinstance(payload, dict) and {"code", "message", "data", "trace_id"}.issubset(payload.keys()):
            return JSONResponse(content=payload, status_code=response.status_code, headers=response_headers(response.headers))

        wrapped = envelope(payload, request.state.trace_id)
        return JSONResponse(content=wrapped, status_code=response.status_code, headers=response_headers(response.headers))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(exc.detail, trace_id, message=message, code=exc.status_code),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        return JSONResponse(
            status_code=422,
            content=envelope(exc.errors(), trace_id, message="validation error", code=422),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        return JSONResponse(
            status_code=500,
            content=envelope({"error": exc.__class__.__name__}, trace_id, message="internal server error", code=500),
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api/v2")
    return app


app = create_app()
