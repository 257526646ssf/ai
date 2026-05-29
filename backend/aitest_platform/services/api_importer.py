from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlparse


HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)


class ApiImportError(ValueError):
    pass


@dataclass(frozen=True)
class ApiImportResult:
    source: str
    endpoints: list[dict[str, Any]]
    generate_cases: bool
    test_cases: list[dict[str, Any]]


def parse_api_import_payload(payload: dict[str, Any]) -> ApiImportResult:
    data = payload if isinstance(payload, dict) else {}
    source = _source_type(data)
    generate_cases = bool(data.get("generate_cases") or data.get("create_cases") or data.get("create_test_cases"))

    if source in {"openapi", "swagger"}:
        document = _document_from_payload(data)
        endpoints = _parse_openapi_document(document)
    elif source == "postman":
        document = _document_from_payload(data)
        endpoints = _parse_postman_collection(document)
    elif source == "curl":
        command = _curl_command_from_payload(data)
        endpoints = [_parse_curl_command(command)]
    else:
        endpoints = _parse_manual_payload(data)
        source = "manual"

    if not endpoints:
        raise ApiImportError("No API endpoints found in import payload")

    clean_endpoints = [_normalize_endpoint(endpoint) for endpoint in endpoints]
    test_cases = [_case_for_endpoint(endpoint) for endpoint in clean_endpoints] if generate_cases else []
    return ApiImportResult(source=source, endpoints=clean_endpoints, generate_cases=generate_cases, test_cases=test_cases)


def sanitize_import_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = sanitize_import_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_import_payload(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    return value


def safe_import_error_detail(exc: Exception) -> dict[str, str]:
    message = str(sanitize_import_payload({"error": str(exc)}).get("error") or "Invalid API import payload")
    return {"code": "invalid_api_import", "message": message[:500]}


def _source_type(data: dict[str, Any]) -> str:
    explicit = data.get("source_type") or data.get("type") or data.get("import_source")
    if explicit:
        lowered = str(explicit).strip().lower().replace("-", "_")
        aliases = {
            "openapi_json": "openapi",
            "swagger_json": "swagger",
            "postman_collection": "postman",
            "postman_json": "postman",
            "curl_command": "curl",
        }
        lowered = aliases.get(lowered, lowered)
        if lowered in {"openapi", "swagger", "postman", "curl"}:
            return lowered
    if any(key in data for key in ("curl", "command")):
        return "curl"
    document = _optional_document_from_payload(data)
    if isinstance(document, dict):
        if "paths" in document:
            return "openapi"
        if "item" in document and "info" in document:
            return "postman"
    if isinstance(document, str) and document.lstrip().startswith("curl "):
        return "curl"
    return "manual"


def _optional_document_from_payload(data: dict[str, Any]) -> Any:
    for key in ("content", "schema", "document", "collection", "raw_content", "text"):
        if key in data:
            return data.get(key)
    return None


def _document_from_payload(data: dict[str, Any]) -> Any:
    document = _optional_document_from_payload(data)
    if document is None:
        document = data
    if isinstance(document, str):
        try:
            return json.loads(document)
        except json.JSONDecodeError as exc:
            raise ApiImportError("Import document must be valid JSON") from exc
    if isinstance(document, dict):
        return document
    raise ApiImportError("Import document must be a JSON object or JSON string")


def _curl_command_from_payload(data: dict[str, Any]) -> str:
    for key in ("curl", "command", "content"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ApiImportError("curl import requires a command string")


def _parse_manual_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    api_payloads = data.get("apis") if isinstance(data.get("apis"), list) else [data]
    endpoints: list[dict[str, Any]] = []
    for item in api_payloads:
        if not isinstance(item, dict):
            raise ApiImportError("apis must contain objects")
        if not (item.get("name") or item.get("method") or item.get("path")):
            raise ApiImportError("Manual API import requires name, method, or path")
        endpoints.append(
            {
                "requirement_item_id": item.get("requirement_item_id"),
                "name": item.get("name") or item.get("title"),
                "method": item.get("method") or "GET",
                "path": item.get("path") or "/",
                "headers_schema": item.get("headers_schema") or item.get("headers") or {},
                "query_schema": item.get("query_schema") or item.get("query") or item.get("params") or {},
                "body_schema": item.get("body_schema") or item.get("body") or {},
                "response_schema": item.get("response_schema") or item.get("response") or {},
                "description": item.get("description"),
            }
        )
    return endpoints


def _parse_openapi_document(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise ApiImportError("OpenAPI import requires a paths object")
    endpoints: list[dict[str, Any]] = []
    for path, path_item in document["paths"].items():
        if not isinstance(path_item, dict):
            continue
        common_parameters = path_item.get("parameters") if isinstance(path_item.get("parameters"), list) else []
        for method, operation in path_item.items():
            if str(method).lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            parameters = [*common_parameters, *(operation.get("parameters") if isinstance(operation.get("parameters"), list) else [])]
            headers_schema = _openapi_parameters(parameters, "header")
            query_schema = _openapi_parameters(parameters, "query")
            body_schema = _openapi_request_body(operation.get("requestBody"))
            response_schema = _openapi_response_schema(operation.get("responses"))
            summary = operation.get("summary") or operation.get("operationId")
            name = summary or f"{str(method).upper()} {path}"
            description = operation.get("description") or summary
            endpoints.append(
                {
                    "name": name,
                    "method": str(method).upper(),
                    "path": str(path) or "/",
                    "headers_schema": headers_schema,
                    "query_schema": query_schema,
                    "body_schema": body_schema,
                    "response_schema": response_schema,
                    "description": description,
                }
            )
    return endpoints


def _openapi_parameters(parameters: list[Any], location: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict) or parameter.get("in") != location:
            continue
        name = parameter.get("name")
        if not name:
            continue
        result[str(name)] = {
            "required": bool(parameter.get("required")),
            "schema": parameter.get("schema") or {},
            "description": parameter.get("description"),
        }
    return result


def _openapi_request_body(request_body: Any) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        return {}
    content = request_body.get("content")
    if isinstance(content, dict):
        selected = _select_media_schema(content)
        if selected is not None:
            return {"required": bool(request_body.get("required")), **selected}
    return {"required": bool(request_body.get("required")), "schema": request_body.get("schema") or {}}


def _openapi_response_schema(responses: Any) -> dict[str, Any]:
    if not isinstance(responses, dict):
        return {}
    selected_key = None
    for key in responses:
        if str(key).startswith("2"):
            selected_key = key
            break
    selected_key = selected_key or ("default" if "default" in responses else next(iter(responses), None))
    if selected_key is None or not isinstance(responses.get(selected_key), dict):
        return {}
    response = responses[selected_key]
    content = response.get("content")
    schema = _select_media_schema(content) if isinstance(content, dict) else None
    return {
        "status": _status_code_value(selected_key),
        "description": response.get("description"),
        **(schema or {}),
    }


def _select_media_schema(content: dict[str, Any]) -> dict[str, Any] | None:
    for media_type in ("application/json", "application/*+json", "multipart/form-data", "application/x-www-form-urlencoded"):
        media = content.get(media_type)
        if isinstance(media, dict):
            return {"content_type": media_type, "schema": media.get("schema") or {}}
    for media_type, media in content.items():
        if isinstance(media, dict):
            return {"content_type": media_type, "schema": media.get("schema") or {}}
    return None


def _status_code_value(value: Any) -> int | str:
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _parse_postman_collection(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("item"), list):
        raise ApiImportError("Postman import requires an item list")
    endpoints: list[dict[str, Any]] = []
    _walk_postman_items(document.get("item") or [], endpoints, [])
    return endpoints


def _walk_postman_items(items: list[Any], endpoints: list[dict[str, Any]], parents: list[str]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if isinstance(item.get("item"), list):
            _walk_postman_items(item["item"], endpoints, [*parents, name] if name else parents)
            continue
        request = item.get("request")
        if not isinstance(request, dict):
            continue
        method = str(request.get("method") or "GET").upper()
        path, query = _postman_url(request.get("url"))
        headers = _postman_headers(request.get("header"))
        body = _postman_body(request.get("body"))
        response = _postman_response(item.get("response"))
        display_name = name or f"{method} {path}"
        endpoints.append(
            {
                "name": display_name,
                "method": method,
                "path": path,
                "headers_schema": headers,
                "query_schema": query,
                "body_schema": body,
                "response_schema": response,
                "description": request.get("description") or item.get("description"),
            }
        )


def _postman_url(url_value: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(url_value, str):
        return _path_and_query_from_url(url_value)
    if not isinstance(url_value, dict):
        return "/", {}
    raw = url_value.get("raw")
    if isinstance(raw, str) and raw:
        path, query = _path_and_query_from_url(raw)
    else:
        parts = url_value.get("path")
        if isinstance(parts, list):
            path = "/" + "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))
        else:
            path = str(parts or "/")
            if not path.startswith("/"):
                path = "/" + path
        query = {}
    for item in url_value.get("query") or []:
        if isinstance(item, dict) and item.get("key"):
            query[str(item["key"])] = item.get("value", "")
    return path or "/", query


def _path_and_query_from_url(url: str) -> tuple[str, dict[str, Any]]:
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        path = parsed.path or "/"
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        return path, query
    if "?" in url:
        path, query_string = url.split("?", 1)
        return path if path.startswith("/") else f"/{path}", dict(parse_qsl(query_string, keep_blank_values=True))
    return url if url.startswith("/") else f"/{url.strip('/')}", {}


def _postman_headers(headers: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict) and item.get("key"):
                result[str(item["key"])] = item.get("value", "")
    elif isinstance(headers, dict):
        result = dict(headers)
    return result


def _postman_body(body: Any) -> Any:
    if not isinstance(body, dict):
        return {}
    mode = body.get("mode")
    if mode == "raw":
        raw = body.get("raw")
        if isinstance(raw, str):
            return _json_or_text(raw)
        return raw or {}
    if mode in {"formdata", "urlencoded"} and isinstance(body.get(mode), list):
        return {str(item.get("key")): item.get("value", "") for item in body[mode] if isinstance(item, dict) and item.get("key")}
    if mode and mode in body:
        return body.get(mode) or {}
    return body


def _postman_response(responses: Any) -> dict[str, Any]:
    if not isinstance(responses, list) or not responses:
        return {}
    response = next((item for item in responses if isinstance(item, dict)), None)
    if not response:
        return {}
    body = response.get("body")
    return {
        "status": response.get("code"),
        "name": response.get("name"),
        "body": _json_or_text(body) if isinstance(body, str) else body,
    }


def _parse_curl_command(command: str) -> dict[str, Any]:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ApiImportError("curl command could not be parsed") from exc
    if tokens and tokens[0] == "curl":
        tokens = tokens[1:]
    method: str | None = None
    headers: dict[str, str] = {}
    body_parts: list[str] = []
    url: str | None = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        next_value = tokens[index + 1] if index + 1 < len(tokens) else None
        if token in {"-X", "--request"} and next_value is not None:
            method = next_value.upper()
            index += 2
        elif token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
            index += 1
        elif token in {"-H", "--header"} and next_value is not None:
            _add_curl_header(headers, next_value)
            index += 2
        elif token in {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode"} and next_value is not None:
            body_parts.append(next_value)
            index += 2
        elif token in {"--url"} and next_value is not None:
            url = next_value
            index += 2
        elif token.startswith("http://") or token.startswith("https://"):
            url = token
            index += 1
        elif not token.startswith("-") and url is None:
            url = token
            index += 1
        else:
            index += 1
    if not url:
        raise ApiImportError("curl command requires a URL")
    path, query = _path_and_query_from_url(url)
    body_text = "&".join(body_parts) if len(body_parts) > 1 else (body_parts[0] if body_parts else None)
    body = _json_or_text(body_text) if body_text is not None else {}
    method = method or ("POST" if body_parts else "GET")
    return {
        "name": f"{method} {path}",
        "method": method,
        "path": path,
        "headers_schema": headers,
        "query_schema": query,
        "body_schema": body,
        "response_schema": {},
        "description": None,
    }


def _add_curl_header(headers: dict[str, str], value: str) -> None:
    if ":" not in value:
        return
    key, header_value = value.split(":", 1)
    key = key.strip()
    if key:
        headers[key] = header_value.strip()


def _json_or_text(value: str | None) -> Any:
    if value is None:
        return {}
    text = value.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _normalize_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    method = str(endpoint.get("method") or "GET").upper()
    path = str(endpoint.get("path") or "/").strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    normalized = {
        "requirement_item_id": endpoint.get("requirement_item_id"),
        "name": endpoint.get("name") or endpoint.get("title") or f"{method} {path}",
        "method": method,
        "path": path,
        "headers_schema": endpoint.get("headers_schema") or {},
        "query_schema": endpoint.get("query_schema") or {},
        "body_schema": endpoint.get("body_schema") or {},
        "response_schema": endpoint.get("response_schema") or {},
        "description": endpoint.get("description"),
    }
    return sanitize_import_payload(normalized)


def _case_for_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    expected_status = _expected_status(endpoint.get("response_schema"))
    return sanitize_import_payload(
        {
            "name": f"{endpoint['name']} success",
            "category": "contract",
            "request_headers": endpoint.get("headers_schema") or {},
            "request_query": endpoint.get("query_schema") or {},
            "request_body": endpoint.get("body_schema") or {},
            "content_type": _content_type(endpoint.get("body_schema")),
            "expected_status": expected_status,
            "assertions": [{"type": "status_code", "expected": expected_status}],
            "status": "ready",
        }
    )


def _expected_status(response_schema: Any) -> int:
    if isinstance(response_schema, dict):
        status = response_schema.get("status") or response_schema.get("status_code") or response_schema.get("code")
        try:
            return int(status)
        except (TypeError, ValueError):
            pass
    return 200


def _content_type(body_schema: Any) -> str:
    if isinstance(body_schema, dict) and isinstance(body_schema.get("content_type"), str):
        return body_schema["content_type"]
    return "application/json"
