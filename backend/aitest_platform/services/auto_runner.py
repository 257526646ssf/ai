from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_key",
    "api-key",
    "apikey",
    "token",
    "cookie",
    "secret",
    "password",
    "git_auth",
)
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|api-key|apikey|token|cookie|secret|password|git_auth)(\s*(?:[:=]|\s)\s*)(Bearer\s+)?[^\s,;}\"]+"
)
DEFAULT_TIMEOUT_MS = 30_000
MIN_TIMEOUT_MS = 1_000
MAX_TIMEOUT_MS = 300_000
MAX_LOG_EXCERPT_CHARS = 16_000
TEXT_ARTIFACT_SUFFIXES = {".html", ".log", ".xml"}
EVIDENCE_KIND_BY_SUFFIX = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".webp": "screenshot",
    ".zip": "trace",
    ".mp4": "video",
    ".webm": "video",
    ".xml": "junit",
    ".html": "report",
    ".log": "log",
}


@dataclass(frozen=True)
class AutoCaseFileInput:
    id: int
    file_name: str
    file_path: str
    content: str
    case_count: int = 0


def clamp_timeout_ms(value: Any = None) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_MS
    try:
        timeout_ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(MAX_TIMEOUT_MS, timeout_ms))


def sanitize_runner_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = sanitize_runner_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_runner_payload(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    return value


def run_auto_project(
    case_files: list[AutoCaseFileInput],
    *,
    framework_files: dict[str, Any] | None = None,
    timeout_ms: Any = None,
    env: dict[str, Any] | None = None,
    mode: str | None = None,
    artifact_root: Any = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    timeout = clamp_timeout_ms(timeout_ms)
    selected_mode = (mode or "auto").strip().lower() or "auto"
    if selected_mode not in {"auto", "pytest", "python"}:
        selected_mode = "auto"
    run_id = uuid.uuid4().hex
    run_artifact_dir = _prepare_run_artifact_dir(artifact_root, run_id)

    with tempfile.TemporaryDirectory(prefix="aitest-auto-runner-") as tmp:
        workdir = Path(tmp)
        written_files = _write_project_files(workdir, framework_files or {}, case_files)
        command = _build_command(workdir, written_files, selected_mode)
        if command is None:
            duration_ms = _duration_ms(started)
            summary = _summary_from_counts(case_files, passed=False, errors=1)
            message = "No runnable Python or pytest case file was found."
            artifacts = _build_artifacts(
                run_artifact_dir=run_artifact_dir,
                workdir=workdir,
                run_id=run_id,
                log_text=message,
                base={
                    "files": written_files,
                    "return_code": None,
                    "runner": {"mode": selected_mode, "command": None, "timeout_ms": timeout},
                    "error": message,
                },
            )
            return {
                "status": "error",
                "summary": summary,
                "artifacts": artifacts,
                "log_excerpt": _log_excerpt(message),
                "duration_ms": duration_ms,
            }

        run_env = os.environ.copy()
        for key, value in (env or {}).items():
            if isinstance(key, str) and value is not None:
                run_env[key] = str(value)

        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout / 1000,
                check=False,
            )
            duration_ms = _duration_ms(started)
            output = _combined_output(completed.stdout, completed.stderr)
            summary = _summary_from_output(output, completed.returncode, case_files)
            status = "completed" if completed.returncode == 0 else "failed"
            artifacts = _build_artifacts(
                run_artifact_dir=run_artifact_dir,
                workdir=workdir,
                run_id=run_id,
                log_text=output,
                base={
                    "files": written_files,
                    "return_code": completed.returncode,
                    "runner": {
                        "mode": _runner_mode(command),
                        "command": command,
                        "timeout_ms": timeout,
                        "env": dict(env or {}),
                    },
                },
            )
            return {
                "status": status,
                "summary": summary,
                "artifacts": artifacts,
                "log_excerpt": _log_excerpt(output),
                "duration_ms": duration_ms,
            }
        except subprocess.TimeoutExpired as exc:
            duration_ms = _duration_ms(started)
            output = _combined_output(_string_or_empty(exc.stdout), _string_or_empty(exc.stderr))
            summary = _summary_from_counts(case_files, passed=False, errors=1)
            message = output or f"Runner timed out after {timeout}ms."
            artifacts = _build_artifacts(
                run_artifact_dir=run_artifact_dir,
                workdir=workdir,
                run_id=run_id,
                log_text=message,
                base={
                    "files": written_files,
                    "return_code": None,
                    "runner": {
                        "mode": _runner_mode(command),
                        "command": command,
                        "timeout_ms": timeout,
                        "env": dict(env or {}),
                    },
                    "error": f"Runner timed out after {timeout}ms.",
                },
            )
            return {
                "status": "error",
                "summary": summary,
                "artifacts": artifacts,
                "log_excerpt": _log_excerpt(message),
                "duration_ms": duration_ms,
            }
        except OSError as exc:
            duration_ms = _duration_ms(started)
            summary = _summary_from_counts(case_files, passed=False, errors=1)
            message = str(exc)
            artifacts = _build_artifacts(
                run_artifact_dir=run_artifact_dir,
                workdir=workdir,
                run_id=run_id,
                log_text=message,
                base={
                    "files": written_files,
                    "return_code": None,
                    "runner": {
                        "mode": _runner_mode(command),
                        "command": command,
                        "timeout_ms": timeout,
                        "env": dict(env or {}),
                    },
                    "error": message,
                },
            )
            return {
                "status": "error",
                "summary": summary,
                "artifacts": artifacts,
                "log_excerpt": _log_excerpt(message),
                "duration_ms": duration_ms,
            }


def _write_project_files(workdir: Path, framework_files: dict[str, Any], case_files: list[AutoCaseFileInput]) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    for raw_path, raw_content in framework_files.items():
        content = raw_content if isinstance(raw_content, str) else str(raw_content)
        relative_path = _safe_relative_path(str(raw_path), fallback=Path(str(raw_path)).name or "framework_file.txt")
        _write_file(workdir, relative_path, content)
        written.append({"path": relative_path, "source": "framework"})

    for case_file in case_files:
        fallback = case_file.file_name or f"auto_case_{case_file.id}.py"
        relative_path = _safe_relative_path(case_file.file_path or fallback, fallback=fallback)
        _write_file(workdir, relative_path, case_file.content)
        written.append(
            {
                "id": case_file.id,
                "path": relative_path,
                "source": "case_file",
                "case_count": case_file.case_count,
            }
        )
    return written


def _write_file(workdir: Path, relative_path: str, content: str) -> None:
    target = (workdir / relative_path).resolve()
    if not str(target).startswith(str(workdir.resolve())):
        raise ValueError("Resolved file path escaped runner workspace.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _safe_relative_path(path: str, *, fallback: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized or Path(normalized).is_absolute():
        normalized = fallback.replace("\\", "/").lstrip("/") or "auto_case.py"
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts) if parts else "auto_case.py"


def _prepare_run_artifact_dir(artifact_root: Any, run_id: str) -> Path:
    root = Path(str(artifact_root)).expanduser() if artifact_root else _default_artifact_root()
    if not root.is_absolute():
        root = (_backend_root() / root).resolve()
    else:
        root = root.resolve()
    run_dir = (root / run_id).resolve()
    if not _is_relative_to(run_dir, root):
        raise ValueError("Resolved artifact path escaped artifact root.")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _default_artifact_root() -> Path:
    return _backend_root() / "data" / "artifacts" / "auto"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_artifacts(*, run_artifact_dir: Path, workdir: Path, run_id: str, log_text: str, base: dict[str, Any]) -> dict[str, Any]:
    clean_log = str(sanitize_runner_payload(log_text or ""))
    evidence: list[dict[str, Any]] = []
    runner_log = _write_runner_log(run_artifact_dir, clean_log)
    evidence.append(_evidence_item(kind="log", path=runner_log, root=run_artifact_dir, source="runner"))
    evidence.extend(_collect_evidence_files(workdir, run_artifact_dir))
    artifacts = {
        **base,
        "run_id": run_id,
        "artifact_dir": str(run_artifact_dir),
        "runner_log": str(runner_log),
        "evidence": evidence,
    }
    return sanitize_runner_payload(artifacts)


def _write_runner_log(run_artifact_dir: Path, clean_log: str) -> Path:
    target = (run_artifact_dir / "runner.log").resolve()
    if not _is_relative_to(target, run_artifact_dir):
        raise ValueError("Resolved runner log path escaped artifact directory.")
    target.write_text(clean_log, encoding="utf-8")
    return target


def _collect_evidence_files(workdir: Path, run_artifact_dir: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    used_targets = {run_artifact_dir / "runner.log"}
    for source_path in sorted(path for path in workdir.rglob("*") if path.is_file()):
        suffix = source_path.suffix.lower()
        kind = EVIDENCE_KIND_BY_SUFFIX.get(suffix)
        if kind is None:
            continue
        relative_source = source_path.relative_to(workdir)
        target_relative = _safe_artifact_relative_path(relative_source)
        target_path = _unique_artifact_path(run_artifact_dir, target_relative, used_targets)
        _copy_artifact_file(source_path, target_path)
        evidence.append(_evidence_item(kind=kind, path=target_path, root=run_artifact_dir, source=str(sanitize_runner_payload(relative_source.as_posix()))))
    return evidence


def _copy_artifact_file(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() in TEXT_ARTIFACT_SUFFIXES:
        text = source_path.read_text(encoding="utf-8", errors="replace")
        target_path.write_text(str(sanitize_runner_payload(text)), encoding="utf-8")
        return
    shutil.copy2(source_path, target_path)


def _safe_artifact_relative_path(relative_source: Path) -> Path:
    safe_parts = [_safe_artifact_name(part) for part in relative_source.parts if part not in {"", ".", ".."}]
    if not safe_parts:
        safe_parts = ["artifact"]
    return Path(*safe_parts)


def _safe_artifact_name(value: str) -> str:
    clean = str(sanitize_runner_payload(value)).replace("\\", "_").replace("/", "_").replace(":", "_")
    clean = re.sub(r"[^A-Za-z0-9._ -]+", "_", clean).strip(" .")
    return clean or "artifact"


def _unique_artifact_path(root: Path, relative_path: Path, used_targets: set[Path]) -> Path:
    target = (root / relative_path).resolve()
    if not _is_relative_to(target, root):
        target = (root / relative_path.name).resolve()
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    index = 1
    while target in used_targets or target.exists():
        target = (parent / f"{stem}-{index}{suffix}").resolve()
        index += 1
    if not _is_relative_to(target, root):
        raise ValueError("Resolved artifact path escaped artifact directory.")
    used_targets.add(target)
    return target


def _evidence_item(*, kind: str, path: Path, root: Path, source: str) -> dict[str, Any]:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not _is_relative_to(resolved_path, resolved_root):
        raise ValueError("Resolved evidence path escaped artifact directory.")
    relative_path = resolved_path.relative_to(resolved_root).as_posix()
    return {
        "kind": kind,
        "path": str(resolved_path),
        "relative_path": relative_path,
        "size_bytes": resolved_path.stat().st_size,
        "source": source,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _build_command(workdir: Path, files: list[dict[str, Any]], mode: str) -> list[str] | None:
    case_paths = [str(item["path"]) for item in files if item.get("source") == "case_file"]
    python_case_paths = [path for path in case_paths if path.endswith(".py")]
    pytest_targets = [path for path in python_case_paths if path.startswith("tests/") or Path(path).name.startswith("test_")]

    if mode == "python":
        target = python_case_paths[0] if python_case_paths else None
        return [sys.executable, target] if target else None

    tests_dir = workdir / "tests"
    if mode == "pytest" or pytest_targets or tests_dir.exists():
        targets = ["tests"] if tests_dir.exists() and mode != "pytest" else pytest_targets
        if not targets and tests_dir.exists():
            targets = ["tests"]
        if not targets:
            targets = python_case_paths
        return [sys.executable, "-m", "pytest", *targets] if targets else None

    target = python_case_paths[0] if python_case_paths else None
    return [sys.executable, target] if target else None


def _runner_mode(command: list[str]) -> str:
    return "pytest" if "-m" in command and "pytest" in command else "python"


def _summary_from_output(output: str, return_code: int, case_files: list[AutoCaseFileInput]) -> dict[str, int]:
    passed = _first_int(r"(\d+)\s+passed", output)
    failed = _first_int(r"(\d+)\s+failed", output)
    errors = _first_int(r"(\d+)\s+errors?", output)
    if passed is not None or failed is not None or errors is not None:
        passed_count = passed or 0
        failed_count = failed or 0
        error_count = errors or 0
        return {
            "total": passed_count + failed_count + error_count,
            "passed": passed_count,
            "failed": failed_count,
            "errors": error_count,
        }
    return _summary_from_counts(case_files, passed=return_code == 0, errors=0)


def _summary_from_counts(case_files: list[AutoCaseFileInput], *, passed: bool, errors: int) -> dict[str, int]:
    total = sum(max(0, int(item.case_count or 0)) for item in case_files) or len(case_files) or 1
    if errors:
        return {"total": total, "passed": 0, "failed": 0, "errors": errors}
    return {"total": total, "passed": total if passed else 0, "failed": 0 if passed else total, "errors": 0}


def _first_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def _combined_output(stdout: str, stderr: str) -> str:
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr or ""


def _log_excerpt(output: str) -> str:
    clean = str(sanitize_runner_payload(output or ""))
    if len(clean) <= MAX_LOG_EXCERPT_CHARS:
        return clean
    return clean[-MAX_LOG_EXCERPT_CHARS:]


def _duration_ms(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


def _string_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
