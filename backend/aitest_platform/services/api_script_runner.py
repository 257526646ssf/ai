from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any


MAX_SCRIPT_STEPS = 20
MAX_OUTPUT_CHARS = 4096
COMMAND_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$")
DANGEROUS_PATTERN = re.compile(
    r"(?i)\b(import|open|eval|exec|subprocess|socket|http|file|env|os|sys|pathlib|shutil|globals|locals|compile|__import__)\b"
)
ALLOWED_COMMANDS = {"set_header", "set_body", "assert_json_path", "set_variable"}
SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)


@dataclass
class ScriptExecutionResult:
    status: str = "passed"
    steps: list[dict[str, Any]] = field(default_factory=list)
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = "error" if self.errors else ("failed" if any(not item.get("passed") for item in self.assertion_results) else self.status)
        return _limit_output(
            _sanitize(
                {
                    "status": status,
                    "steps": self.steps,
                    "assertion_results": self.assertion_results,
                    "errors": self.errors,
                    "variables": self.variables,
                }
            )
        )


def run_api_script(
    script: Any,
    *,
    phase: str,
    request: dict[str, Any],
    response: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = ScriptExecutionResult(variables=dict(variables or {}))
    if script in (None, "", [], {}):
        return result.to_dict()
    source_text = script if isinstance(script, str) else json.dumps(script, ensure_ascii=False)
    if DANGEROUS_PATTERN.search(source_text):
        result.errors.append({"code": "dangerous_keyword", "message": "script contains a blocked keyword"})
        return result.to_dict()
    try:
        steps = _parse_script_steps(script)
    except ValueError as exc:
        result.errors.append({"code": "invalid_script", "message": str(exc)[:500]})
        return result.to_dict()
    if len(steps) > MAX_SCRIPT_STEPS:
        result.errors.append({"code": "too_many_steps", "message": f"script step count must be <= {MAX_SCRIPT_STEPS}"})
        return result.to_dict()
    for index, step in enumerate(steps, start=1):
        command = str(step.get("command") or step.get("action") or "").strip()
        args = step.get("args") if isinstance(step.get("args"), list) else []
        if command not in ALLOWED_COMMANDS:
            result.errors.append({"code": "unsupported_command", "step": index, "command": command})
            break
        try:
            if "raw_args" in step:
                args = _parse_args(str(step["raw_args"]), result.variables)
            _execute_step(command, args, phase, request, response, result)
            result.steps.append({"index": index, "command": command, "status": "passed"})
        except ValueError as exc:
            result.errors.append({"code": "script_step_failed", "step": index, "command": command, "message": str(exc)[:500]})
            break
    return result.to_dict()


def _parse_script_steps(script: Any) -> list[dict[str, Any]]:
    if isinstance(script, str):
        return [_parse_command_line(line) for line in _script_lines(script)]
    if isinstance(script, list):
        return [_normalize_step(item) for item in script]
    if isinstance(script, dict):
        if isinstance(script.get("steps"), list):
            return [_normalize_step(item) for item in script["steps"]]
        return [_normalize_step(script)]
    raise ValueError("script must be a string, list, or object")


def _script_lines(script: str) -> list[str]:
    lines: list[str] = []
    for raw_line in script.replace(";", "\n").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _parse_command_line(line: str) -> dict[str, Any]:
    match = COMMAND_PATTERN.match(line)
    if not match:
        raise ValueError(f"unsupported script syntax: {line[:80]}")
    command, raw_args = match.group(1), match.group(2).strip()
    if command not in ALLOWED_COMMANDS:
        raise ValueError(f"unsupported command: {command}")
    return {"command": command, "args": [], "raw_args": raw_args}


def _parse_args(raw_args: str, variables: dict[str, Any] | None = None) -> list[Any]:
    if not raw_args:
        return []
    try:
        parsed = json.loads(f"[{raw_args}]")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        pass
    try:
        parsed_ast = ast.parse(f"({raw_args},)", mode="eval")
        parsed = _eval_safe_ast(parsed_ast.body, variables or {})
    except (ValueError, SyntaxError) as exc:
        raise ValueError("script arguments must be JSON/Python literals") from exc
    return list(parsed if isinstance(parsed, tuple) else (parsed,))


def _normalize_step(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("script steps must be objects")
    command = item.get("command") or item.get("action") or item.get("op")
    args = item.get("args")
    if command is None and len(item) == 1:
        command, args = next(iter(item.items()))
    if args is None:
        args = _args_from_named_fields(str(command or ""), item)
    if not isinstance(args, list):
        args = [args]
    return {"command": str(command or ""), "args": args}


def _args_from_named_fields(command: str, item: dict[str, Any]) -> list[Any]:
    if command == "set_header":
        return [item.get("name") or item.get("key"), item.get("value")]
    if command == "set_body":
        return [item.get("name") or item.get("key"), item.get("value")]
    if command == "assert_json_path":
        return [item.get("path") or item.get("json_path"), item.get("expected", item.get("value"))]
    if command == "set_variable":
        return [item.get("name") or item.get("key"), item.get("value") or item.get("path") or item.get("json_path")]
    return []


def _execute_step(
    command: str,
    args: list[Any],
    phase: str,
    request: dict[str, Any],
    response: dict[str, Any] | None,
    result: ScriptExecutionResult,
) -> None:
    if command == "set_header":
        if phase != "pre":
            raise ValueError("set_header is only allowed in pre_script")
        name, value = _two_args(args, "set_header")
        headers = request.setdefault("headers", {})
        if not isinstance(headers, dict):
            raise ValueError("request headers must be an object")
        headers[str(name)] = value
        return
    if command == "set_body":
        if phase != "pre":
            raise ValueError("set_body is only allowed in pre_script")
        if len(args) == 1 and isinstance(args[0], dict):
            request["body"] = args[0]
            return
        name, value = _two_args(args, "set_body")
        body = request.get("body")
        if body is None or not isinstance(body, dict):
            body = {}
            request["body"] = body
        body[str(name)] = value
        return
    if command == "assert_json_path":
        if phase != "post":
            raise ValueError("assert_json_path is only allowed in post_script")
        path, expected = _two_args(args, "assert_json_path")
        actual = _json_path_get(_response_body(response), str(path))
        passed = actual == expected
        result.assertion_results.append(
            _sanitize({"type": "json_path_equals", "path": path, "expected": expected, "actual": actual, "passed": passed})
        )
        return
    if command == "set_variable":
        name, value = _two_args(args, "set_variable")
        resolved = _json_path_get(_response_body(response), str(value)) if phase == "post" and isinstance(value, str) and value.startswith("$.") else value
        if resolved is None:
            raise ValueError(f"variable source not found: {value}")
        result.variables[str(name)] = resolved
        return
    raise ValueError(f"unsupported command: {command}")


def _eval_safe_ast(node: ast.AST, variables: dict[str, Any]) -> Any:
    if isinstance(node, ast.Tuple):
        return tuple(_eval_safe_ast(item, variables) for item in node.elts)
    if isinstance(node, ast.List):
        return [_eval_safe_ast(item, variables) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _eval_safe_ast(key, variables): _eval_safe_ast(value, variables)
            for key, value in zip(node.keys, node.values)
            if key is not None
        }
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _eval_safe_ast(node.operand, variables)
        if isinstance(operand, (int, float)):
            return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "variables":
        key = _eval_safe_ast(node.slice, variables)
        return variables.get(str(key))
    if isinstance(node, ast.Name):
        if node.id == "variables":
            return variables
        aliases = {"true": True, "false": False, "null": None}
        if node.id in aliases:
            return aliases[node.id]
    raise ValueError("script arguments must be safe literals or variables['name'] references")


def _two_args(args: list[Any], command: str) -> tuple[Any, Any]:
    if len(args) < 2:
        raise ValueError(f"{command} requires two arguments")
    return args[0], args[1]


def _response_body(response: dict[str, Any] | None) -> Any:
    if not isinstance(response, dict):
        return None
    return response.get("body")


def _json_path_get(value: Any, path: str) -> Any:
    if not path:
        return value
    parts = path[2:].split(".") if path.startswith("$.") else path.strip(".").split(".")
    current = value
    for part in parts:
        if part == "":
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    return value


def _limit_output(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= MAX_OUTPUT_CHARS:
        return value
    return {
        "status": value.get("status", "error"),
        "errors": [{"code": "output_truncated", "message": "script output exceeded limit"}],
        "steps": value.get("steps", [])[:MAX_SCRIPT_STEPS],
        "assertion_results": value.get("assertion_results", [])[:MAX_SCRIPT_STEPS],
        "variables": {},
    }
