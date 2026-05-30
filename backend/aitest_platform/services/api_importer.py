from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlparse

from aitest_platform.services.file_formats import detect_import_format, detect_unsupported_import_format, unsupported_import_detail
from aitest_platform.services.office_formats import ParsedDocument, parse_document_payload


HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SUPPORTED_API_IMPORT_FORMATS = {"curl", "har", "manual", "openapi", "postman", "swagger", "docx", "pdf", "xlsx", "xmind"}
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)
DOCUMENT_IMPORT_FORMATS = {"docx", "pdf", "xlsx", "xmind"}
METHOD_LINE_RE = re.compile(r"(?i)\b(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\b\s+(/[A-Za-z0-9._~!$&'()*+,;=:@%/\-{}[\]]*)")


class ApiImportError(ValueError):
    pass


class ApiImportUnsupportedFormatError(ApiImportError):
    def __init__(self, detail: dict[str, Any], *, status_code: int = 415) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(str(detail.get("message") or "Unsupported API import format"))


@dataclass(frozen=True)
class ApiImportResult:
    source: str
    endpoints: list[dict[str, Any]]
    generate_cases: bool
    test_cases: list[dict[str, Any]]


def parse_api_import_payload(payload: dict[str, Any]) -> ApiImportResult:
    data = payload if isinstance(payload, dict) else {}
    unsupported_format = detect_unsupported_import_format(data)
    if unsupported_format is not None:
        raise ApiImportUnsupportedFormatError(
            unsupported_import_detail(
                unsupported_format,
                SUPPORTED_API_IMPORT_FORMATS,
                error_code="unsupported_api_import_format",
            )
        )
    source = _source_type(data)
    generate_cases = bool(data.get("generate_cases") or data.get("create_cases") or data.get("create_test_cases"))

    if source in {"openapi", "swagger"}:
        document = _document_from_payload(data, allow_yaml=True)
        endpoints = _parse_openapi_document(document)
    elif source in DOCUMENT_IMPORT_FORMATS:
        parsed = parse_document_payload(
            data,
            source_type=source,
            filename=data.get("source_file_name") or data.get("filename") or data.get("name"),
            fallback_name=str(data.get("name") or data.get("source_file_name") or "API document"),
        )
        endpoints = _parse_document_endpoints(parsed)
        source = parsed.format
    elif source == "har":
        document = _document_from_payload(data)
        endpoints = _parse_har_document(document)
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


def safe_import_error_detail(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return sanitize_import_payload(detail)
    message = str(sanitize_import_payload({"error": str(exc)}).get("error") or "Invalid API import payload")
    return {"code": "invalid_api_import", "message": message[:500]}


def _source_type(data: dict[str, Any]) -> str:
    declared_format = detect_import_format(data)
    if declared_format in DOCUMENT_IMPORT_FORMATS:
        return declared_format
    explicit = data.get("source_type") or data.get("type") or data.get("import_source")
    if explicit:
        lowered = str(explicit).strip().lower().replace("-", "_")
        aliases = {
            "openapi_json": "openapi",
            "openapi_yaml": "openapi",
            "openapi_yml": "openapi",
            "swagger_json": "swagger",
            "swagger_yaml": "swagger",
            "swagger_yml": "swagger",
            "postman_collection": "postman",
            "postman_json": "postman",
            "curl_command": "curl",
            "har_json": "har",
        }
        lowered = aliases.get(lowered, lowered)
        if lowered in {"openapi", "swagger", "postman", "curl", "har", *DOCUMENT_IMPORT_FORMATS}:
            return lowered
    if any(key in data for key in ("curl", "command")):
        return "curl"
    document = _optional_document_from_payload(data)
    if isinstance(document, dict):
        if "paths" in document:
            return "openapi"
        if isinstance(document.get("log"), dict) and isinstance(document["log"].get("entries"), list):
            return "har"
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


def _document_from_payload(data: dict[str, Any], *, allow_yaml: bool = False) -> Any:
    document = _optional_document_from_payload(data)
    if document is None:
        document = data
    if isinstance(document, str):
        try:
            return json.loads(document)
        except json.JSONDecodeError as exc:
            if allow_yaml:
                try:
                    return _parse_yaml_document(document)
                except ApiImportError:
                    raise
                except Exception as yaml_exc:
                    raise ApiImportError("Import document must be valid JSON or supported YAML") from yaml_exc
            raise ApiImportError("Import document must be valid JSON") from exc
    if isinstance(document, dict):
        return document
    raise ApiImportError("Import document must be a JSON object or JSON string")


def _parse_document_endpoints(document: ParsedDocument) -> list[dict[str, Any]]:
    endpoints = _parse_document_tables(document.tables)
    if not endpoints:
        endpoints = _parse_document_text(document.text)
    if not endpoints and document.warnings:
        warning = "; ".join(document.warnings)
        raise ApiImportError(f"No API endpoints found in import payload. {warning}")
    return endpoints


def _parse_document_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for table in tables:
        rows = table.get("rows") if isinstance(table, dict) else None
        normalized_rows = _normalize_table_rows(rows)
        if len(normalized_rows) < 2:
            continue
        header_map = _table_header_map(normalized_rows[0])
        if "method" not in header_map or "path" not in header_map:
            continue
        for row in normalized_rows[1:]:
            method = row[header_map["method"]] if header_map["method"] < len(row) else ""
            raw_path = row[header_map["path"]] if header_map["path"] < len(row) else ""
            if not method and not raw_path:
                continue
            path, inline_query = _path_and_query_from_url(raw_path or "/")
            query_schema = _structured_cell(_table_cell(row, header_map, "query"))
            if isinstance(query_schema, dict):
                query_schema = {**inline_query, **query_schema}
            endpoint = {
                "name": _table_cell(row, header_map, "name") or _table_cell(row, header_map, "summary"),
                "method": (method or "GET").upper(),
                "path": path or "/",
                "headers_schema": _structured_cell(_table_cell(row, header_map, "headers")),
                "query_schema": query_schema if query_schema not in ("", None) else inline_query,
                "body_schema": _structured_body(_table_cell(row, header_map, "body")),
                "response_schema": _structured_response(
                    _table_cell(row, header_map, "response"),
                    _table_cell(row, header_map, "status"),
                ),
                "description": _table_cell(row, header_map, "description") or _table_cell(row, header_map, "remark"),
            }
            endpoints.append(endpoint)
    return endpoints


def _parse_document_text(text: str) -> list[dict[str, Any]]:
    stripped = (text or "").strip()
    if not stripped:
        return []
    try:
        structured = _document_from_payload({"content": stripped}, allow_yaml=True)
    except ApiImportError:
        structured = None
    if isinstance(structured, dict):
        if "paths" in structured:
            return _parse_openapi_document(structured)
        if isinstance(structured.get("log"), dict):
            return _parse_har_document(structured)
        if "item" in structured and "info" in structured:
            return _parse_postman_collection(structured)

    endpoints: list[dict[str, Any]] = []
    for line in stripped.splitlines():
        for match in METHOD_LINE_RE.finditer(line):
            method = match.group(1).upper()
            path, query = _path_and_query_from_url(match.group(2).strip())
            endpoints.append(
                {
                    "name": f"{method} {path}",
                    "method": method,
                    "path": path,
                    "headers_schema": {},
                    "query_schema": query,
                    "body_schema": {},
                    "response_schema": {},
                    "description": line.strip()[:500],
                }
            )
    if endpoints:
        return endpoints

    curl_matches = re.findall(r"curl\s+[^\n]+", stripped)
    for command in curl_matches[:20]:
        try:
            endpoints.append(_parse_curl_command(command))
        except ApiImportError:
            continue
    return endpoints


def _normalize_table_rows(rows: Any) -> list[list[str]]:
    normalized: list[list[str]] = []
    if not isinstance(rows, list):
        return normalized
    for row in rows:
        if not isinstance(row, list):
            continue
        normalized.append([str(cell or "").strip() for cell in row])
    return normalized


def _table_header_map(header_row: list[str]) -> dict[str, int]:
    aliases = {
        "name": {"name", "title", "api name", "接口名称", "名称"},
        "summary": {"summary", "概述"},
        "method": {"method", "http method", "请求方式", "方式"},
        "path": {"path", "url", "uri", "endpoint", "接口", "接口路径", "request path"},
        "headers": {"headers", "request headers", "请求头"},
        "query": {"query", "query params", "params", "请求参数", "querystring"},
        "body": {"body", "request body", "请求体", "body schema"},
        "response": {"response", "response body", "响应体", "返回体", "返回结果"},
        "status": {"status", "status code", "http status", "响应码", "返回码"},
        "description": {"description", "desc", "描述", "说明"},
        "remark": {"remark", "备注", "notes"},
    }
    result: dict[str, int] = {}
    for index, value in enumerate(header_row):
        normalized = _normalize_header_text(value)
        for key, names in aliases.items():
            if normalized in {_normalize_header_text(item) for item in names} and key not in result:
                result[key] = index
                break
    return result


def _normalize_header_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").strip().lower())


def _table_cell(row: list[str], header_map: dict[str, int], key: str) -> str:
    index = header_map.get(key)
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _structured_cell(value: str) -> Any:
    if not value:
        return {}
    parsed = _json_or_text(value)
    if isinstance(parsed, (dict, list)):
        return parsed
    pairs: dict[str, Any] = {}
    for part in re.split(r"[;\n]+", value):
        if ":" in part:
            key, item_value = part.split(":", 1)
            if key.strip():
                pairs[key.strip()] = item_value.strip()
    return pairs or value


def _structured_body(value: str) -> Any:
    if not value:
        return {}
    parsed = _structured_cell(value)
    if isinstance(parsed, dict):
        return parsed
    return {"example": parsed}


def _structured_response(value: str, status_value: str) -> dict[str, Any]:
    response: dict[str, Any] = {}
    if status_value:
        try:
            response["status"] = int(status_value)
        except ValueError:
            response["status"] = status_value
    parsed = _structured_cell(value)
    if parsed not in ({}, ""):
        response["body"] = parsed
    return response


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


def _parse_har_document(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("log"), dict):
        raise ApiImportError("HAR import requires a log object")
    entries = document["log"].get("entries")
    if not isinstance(entries, list):
        raise ApiImportError("HAR import requires log.entries")
    endpoints: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        method = str(request.get("method") or "GET").upper()
        path, query = _path_and_query_from_url(str(request.get("url") or "/"))
        for item in request.get("queryString") or []:
            if isinstance(item, dict) and item.get("name"):
                query[str(item["name"])] = item.get("value", "")
        body = _har_request_body(request.get("postData"))
        content_type = _har_mime_type(request.get("postData"))
        response_body = _har_response_body(response.get("content"))
        response_schema: dict[str, Any] = {
            "status": response.get("status"),
            "headers": _har_headers(response.get("headers")),
            "body": response_body,
        }
        if isinstance(response.get("content"), dict) and response["content"].get("mimeType"):
            response_schema["content_type"] = response["content"].get("mimeType")
        body_schema = body
        if content_type and isinstance(body_schema, dict):
            body_schema = {"content_type": content_type, **body_schema}
        endpoints.append(
            {
                "name": request.get("comment") or f"{method} {path}" or f"HAR request {index}",
                "method": method,
                "path": path,
                "headers_schema": _har_headers(request.get("headers")),
                "query_schema": query,
                "body_schema": body_schema,
                "response_schema": response_schema,
                "description": entry.get("comment"),
            }
        )
    return endpoints


def _har_headers(headers: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict) and item.get("name"):
                result[str(item["name"])] = item.get("value", "")
    elif isinstance(headers, dict):
        result = dict(headers)
    return result


def _har_request_body(post_data: Any) -> Any:
    if not isinstance(post_data, dict):
        return {}
    if isinstance(post_data.get("params"), list) and post_data["params"]:
        return {str(item.get("name")): item.get("value", "") for item in post_data["params"] if isinstance(item, dict) and item.get("name")}
    text = post_data.get("text")
    return _json_or_text(text) if isinstance(text, str) else (text or {})


def _har_response_body(content: Any) -> Any:
    if not isinstance(content, dict):
        return {}
    text = content.get("text")
    return _json_or_text(text) if isinstance(text, str) else (text or {})


def _har_mime_type(post_data: Any) -> str | None:
    if isinstance(post_data, dict) and isinstance(post_data.get("mimeType"), str):
        return post_data["mimeType"]
    return None


def _parse_yaml_document(text: str) -> dict[str, Any]:
    lines = _yaml_lines(text)
    if not lines:
        raise ApiImportError("YAML document is empty")
    value, index = _parse_yaml_node(lines, 0, lines[0][0])
    if index < len(lines):
        raise ApiImportError("Unsupported YAML structure")
    if not isinstance(value, dict):
        raise ApiImportError("YAML document must be an object")
    return value


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or raw_line.strip() in {"---", "..."}:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        result.append((indent, raw_line.strip()))
    return result


def _parse_yaml_node(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, content = lines[index]
    if current_indent < indent:
        return {}, index
    if content.startswith("- "):
        return _parse_yaml_list(lines, index, current_indent)
    return _parse_yaml_mapping(lines, index, current_indent)


def _parse_yaml_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent or content.startswith("- "):
            break
        if current_indent > indent:
            index += 1
            continue
        key, value = _split_yaml_key_value(content)
        if value is None:
            if index + 1 < len(lines) and lines[index + 1][0] > current_indent:
                child, index = _parse_yaml_node(lines, index + 1, lines[index + 1][0])
                result[key] = child
            else:
                result[key] = {}
                index += 1
        else:
            result[key] = _yaml_scalar(value)
            index += 1
    return result, index


def _parse_yaml_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent or not content.startswith("- "):
            break
        if current_indent > indent:
            index += 1
            continue
        item_text = content[2:].strip()
        if not item_text:
            if index + 1 < len(lines) and lines[index + 1][0] > current_indent:
                item, index = _parse_yaml_node(lines, index + 1, lines[index + 1][0])
            else:
                item, index = {}, index + 1
        elif ":" in item_text:
            key, value = _split_yaml_key_value(item_text)
            item = {key: _yaml_scalar(value) if value is not None else {}}
            index += 1
            if index < len(lines) and lines[index][0] > current_indent:
                extra, index = _parse_yaml_mapping(lines, index, lines[index][0])
                if isinstance(extra, dict):
                    item.update(extra)
        else:
            item = _yaml_scalar(item_text)
            index += 1
        result.append(item)
    return result, index


def _split_yaml_key_value(content: str) -> tuple[str, str | None]:
    if ":" not in content:
        raise ApiImportError("Unsupported YAML line")
    key, value = content.split(":", 1)
    key = _unquote(key.strip())
    value = value.strip()
    return key, value if value != "" else None


def _yaml_scalar(value: str | None) -> Any:
    if value is None:
        return {}
    text = value.strip()
    if text == "":
        return ""
    if text in {"{}", "[]"}:
        return {} if text == "{}" else []
    unquoted = _unquote(text)
    if unquoted != text:
        return unquoted
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


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
