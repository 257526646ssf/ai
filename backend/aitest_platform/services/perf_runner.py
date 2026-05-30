from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from statistics import mean
from typing import Any

SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|api-key|apikey|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_HTML_REPORT_TIMEOUT_SECONDS = 60
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 1800
MAX_OUTPUT_CHARS = 20000
MAX_RAW_CHARS = 65536
DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "perf"


def clamp_timeout_seconds(value: Any = None) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, timeout))


def sanitize_perf_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = sanitize_perf_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_perf_payload(item) for item in value]
    if isinstance(value, str):
        return _limit_text(SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value))
    return value


def inspect_jmeter_dependency(jmeter_path: Any = None) -> dict[str, Any]:
    requested = str(jmeter_path or "jmeter").strip() or "jmeter"
    resolved = requested if _looks_like_path(requested) else shutil.which(requested)
    exists = bool(resolved and (not _looks_like_path(resolved) or Path(resolved).exists()))
    status = "ready" if exists else "jmeter_not_found"
    return sanitize_perf_payload(
        {
            "available": exists,
            "status": status,
            "requested": requested,
            "path": resolved,
            "note": "This check only resolves the CLI path and does not execute JMeter.",
        }
    )


def run_jmeter_plan(jmx_script: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload or {}
    started = time.perf_counter()
    timeout = clamp_timeout_seconds(data.get("timeout") or data.get("timeout_s") or data.get("timeout_seconds"))
    html_report_timeout = clamp_timeout_seconds(
        data.get("html_report_timeout") or data.get("html_report_timeout_s") or data.get("html_report_timeout_seconds") or DEFAULT_HTML_REPORT_TIMEOUT_SECONDS
    )
    jmeter_path = str(data.get("jmeter_path") or data.get("jmeterPath") or "jmeter").strip() or "jmeter"
    safe_payload = sanitize_perf_payload(data)
    if not jmx_script or not str(jmx_script).strip():
        return _error_result(
            "error",
            "missing_jmx_script",
            "JMX script is required for real performance execution.",
            started,
            timeout,
            jmeter_path,
            safe_payload,
        )

    run_id = _run_id(data)
    artifact_dir = _artifact_dir(data, run_id)
    plan_path = artifact_dir / "plan.jmx"
    jtl_path = artifact_dir / "result.jtl"
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(str(jmx_script), encoding="utf-8")
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
    except OSError as exc:
        return _error_result("error", "artifact_write_error", str(exc), started, timeout, jmeter_path, safe_payload)

    resolved_jmeter = jmeter_path if _looks_like_path(jmeter_path) else shutil.which(jmeter_path)
    if resolved_jmeter is None:
        return _error_result(
            "error",
            "jmeter_not_found",
            f"JMeter CLI was not found: {jmeter_path}",
            started,
            timeout,
            jmeter_path,
            safe_payload,
            artifact_dir,
        )
    if _looks_like_path(resolved_jmeter) and not Path(resolved_jmeter).exists():
        return _error_result(
            "error",
            "jmeter_not_found",
            f"JMeter CLI was not found: {jmeter_path}",
            started,
            timeout,
            jmeter_path,
            safe_payload,
            artifact_dir,
        )

    try:
        command = [resolved_jmeter, "-n", "-t", str(plan_path), "-l", str(jtl_path)]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = _duration_seconds(started)
            stdout = _limit_text(exc.stdout or "")
            stderr = _limit_text(exc.stderr or "")
            _write_text(stdout_path, stdout)
            _write_text(stderr_path, stderr)
            return {
                "status": "failed",
                "summary_data": {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "avg_ms": None,
                    "p95_ms": None,
                    "error_rate": 1.0,
                    "reason": "timeout",
                    "timeout_seconds": timeout,
                },
                "timeline_data": [],
                "error_details": [{"type": "timeout", "message": f"JMeter execution exceeded {timeout}s."}],
                "artifacts": _artifacts(jmeter_path, command, safe_payload, stdout, stderr, None, None, artifact_dir),
                "raw_data_path": _path_if_exists(jtl_path),
                "duration": duration,
            }

        stdout = _limit_text(completed.stdout)
        stderr = _limit_text(completed.stderr)
        _write_text(stdout_path, stdout)
        _write_text(stderr_path, stderr)
        jtl_text = _read_text_if_exists(jtl_path)
        metrics = parse_jtl(jtl_text) if jtl_text else None
        status = "completed" if completed.returncode == 0 else "error"
        warnings: list[dict[str, Any]] = []
        html_report_result = None
        if _wants_html_report(data) and completed.returncode == 0 and jtl_path.exists():
            html_report_result = _generate_html_report(resolved_jmeter, jtl_path, artifact_dir / "report", html_report_timeout)
            warnings.extend(html_report_result.get("warnings", []))
        if metrics is None:
            summary = {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "avg_ms": None,
                "p95_ms": None,
                "error_rate": None,
                "returncode": completed.returncode,
                "stdout_summary": _output_summary(stdout),
                "stderr_summary": _output_summary(stderr),
            }
            timeline: list[dict[str, Any]] = []
            error_details = [] if completed.returncode == 0 else [{"type": "jmeter_exit", "returncode": completed.returncode}]
        else:
            summary = {**metrics["summary"], "returncode": completed.returncode}
            timeline = metrics["timeline"]
            error_details = []
            if completed.returncode != 0:
                error_details.append({"type": "jmeter_exit", "returncode": completed.returncode})
            if metrics["failed"]:
                error_details.append({"type": "sample_failures", "failed": metrics["failed"]})
        return {
            "status": status,
            "summary_data": sanitize_perf_payload(summary),
            "timeline_data": sanitize_perf_payload(timeline),
            "error_details": sanitize_perf_payload(error_details),
            "artifacts": _artifacts(jmeter_path, command, safe_payload, stdout, stderr, jtl_text, completed.returncode, artifact_dir, warnings, html_report_result),
            "raw_data_path": _path_if_exists(jtl_path),
            "duration": _duration_seconds(started),
        }
    except OSError as exc:
        return _error_result("error", "jmeter_os_error", str(exc), started, timeout, jmeter_path, safe_payload, artifact_dir)


def parse_jtl(jtl_text: str) -> dict[str, Any] | None:
    text = (jtl_text or "").strip()
    if not text:
        return None
    samples = _parse_jtl_xml(text) if text.startswith("<") else _parse_jtl_csv(text)
    if not samples:
        return None
    elapsed = [sample["elapsed"] for sample in samples if sample.get("elapsed") is not None]
    timestamps = [sample["timestamp"] for sample in samples if sample.get("timestamp") is not None]
    total = len(samples)
    failed = sum(1 for sample in samples if not sample.get("success", False))
    passed = total - failed
    duration_seconds = _sample_duration_seconds(timestamps)
    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "avg_ms": round(mean(elapsed), 2) if elapsed else None,
        "p95_ms": _percentile(elapsed, 95),
        "max_ms": round(max(elapsed), 2) if elapsed else None,
        "error_rate": round(failed / total, 6) if total else 0,
        "tps": round(total / duration_seconds, 3) if duration_seconds else None,
    }
    return {"summary": summary, "timeline": _timeline(samples), "total": total, "failed": failed}


def _parse_jtl_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    samples: list[dict[str, Any]] = []
    for row in reader:
        elapsed = _safe_float(row.get("elapsed") or row.get("Latency") or row.get("t"))
        success = _parse_success(row.get("success") or row.get("s"))
        timestamp = _safe_float(row.get("timeStamp") or row.get("ts"))
        samples.append({"elapsed": elapsed, "success": success, "timestamp": timestamp})
    return samples


def _parse_jtl_xml(text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    samples: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag not in {"sample", "httpSample"}:
            continue
        elapsed = _safe_float(node.attrib.get("t") or node.attrib.get("elapsed"))
        success = _parse_success(node.attrib.get("s") or node.attrib.get("success"))
        timestamp = _safe_float(node.attrib.get("ts") or node.attrib.get("timeStamp"))
        samples.append({"elapsed": elapsed, "success": success, "timestamp": timestamp})
    return samples


def _timeline(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = {}
    for index, sample in enumerate(samples):
        raw_ts = sample.get("timestamp")
        second = int(raw_ts // 1000) if raw_ts is not None else index
        buckets.setdefault(second, []).append(sample)
    timeline: list[dict[str, Any]] = []
    for offset, key in enumerate(sorted(buckets)):
        bucket = buckets[key]
        elapsed = [sample["elapsed"] for sample in bucket if sample.get("elapsed") is not None]
        failed = sum(1 for sample in bucket if not sample.get("success", False))
        timeline.append(
            {
                "second": offset + 1,
                "samples": len(bucket),
                "passed": len(bucket) - failed,
                "failed": failed,
                "avg_ms": round(mean(elapsed), 2) if elapsed else None,
            }
        )
    return timeline[:1000]


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, int(round((percentile / 100) * len(sorted_values) + 0.5)) - 1))
    return round(sorted_values[index], 2)


def _sample_duration_seconds(timestamps: list[float]) -> float | None:
    if not timestamps:
        return None
    if len(timestamps) == 1:
        return 1.0
    duration_ms = max(timestamps) - min(timestamps)
    return max(1.0, duration_ms / 1000)


def _artifacts(
    jmeter_path: str,
    command: list[str],
    payload: dict[str, Any],
    stdout: str | None,
    stderr: str | None,
    jtl_text: str | None,
    returncode: int | None,
    artifact_dir: Path | None = None,
    warnings: list[dict[str, Any]] | None = None,
    html_report_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = _artifact_files(artifact_dir)
    evidence = [item for item in files if item.get("kind") in {"jmx", "jtl", "stdout", "stderr", "html_report", "html_report_index"}]
    return sanitize_perf_payload(
        {
            "tool": "jmeter",
            "jmeter_path": jmeter_path,
            "command": command,
            "returncode": returncode,
            "artifact_dir": str(artifact_dir) if artifact_dir else None,
            "files": files,
            "evidence": evidence,
            "warnings": warnings or [],
            "html_report": html_report_result,
            "stdout": _limit_text(stdout or ""),
            "stderr": _limit_text(stderr or ""),
            "raw_data": {"jtl_excerpt": _limit_text(jtl_text or "", MAX_RAW_CHARS), "jtl_truncated": bool(jtl_text and len(jtl_text) > MAX_RAW_CHARS)},
            "payload": payload,
        }
    )


def _error_result(
    status: str,
    error_type: str,
    message: str,
    started: float,
    timeout: int,
    jmeter_path: str,
    payload: dict[str, Any],
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    safe_message = str(sanitize_perf_payload(message))
    if artifact_dir is not None:
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            _write_text(artifact_dir / "stdout.log", "")
            _write_text(artifact_dir / "stderr.log", safe_message)
        except OSError:
            pass
    return {
        "status": status,
        "summary_data": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "avg_ms": None,
            "p95_ms": None,
            "error_rate": 1.0,
            "reason": error_type,
            "timeout_seconds": timeout,
        },
        "timeline_data": [],
        "error_details": [{"type": error_type, "message": safe_message}],
        "artifacts": _artifacts(jmeter_path, [jmeter_path, "-n", "-t", "plan.jmx", "-l", "result.jtl"], payload, "", safe_message, None, None, artifact_dir),
        "raw_data_path": _path_if_exists(artifact_dir / "result.jtl") if artifact_dir else None,
        "duration": _duration_seconds(started),
    }


def _read_text_if_exists(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _write_text(path: Path, text: str) -> None:
    path.write_text(str(sanitize_perf_payload(text)), encoding="utf-8", errors="replace")


def _run_id(payload: dict[str, Any]) -> str:
    value = payload.get("run_id") or payload.get("runId") or payload.get("execution_id") or payload.get("executionId")
    if value is None or not str(value).strip():
        value = f"run-{int(time.time() * 1000)}"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip(".-")
    return safe[:96] or f"run-{int(time.time() * 1000)}"


def _artifact_dir(payload: dict[str, Any], run_id: str) -> Path:
    root_value = payload.get("artifact_root") or payload.get("artifactRoot")
    root = Path(str(root_value)).expanduser() if root_value else DEFAULT_ARTIFACT_ROOT
    return root / run_id


def _wants_html_report(payload: dict[str, Any]) -> bool:
    value = payload.get("generate_html_report")
    if value is None:
        value = payload.get("generateHtmlReport")
    if value is None:
        value = payload.get("html_report")
    if value is None:
        value = payload.get("htmlReport")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _generate_html_report(jmeter_path: str, jtl_path: Path, report_dir: Path, timeout: int) -> dict[str, Any]:
    command = [jmeter_path, "-g", str(jtl_path), "-o", str(report_dir)]
    if report_dir.exists():
        try:
            shutil.rmtree(report_dir)
        except OSError as exc:
            return {
                "status": "warning",
                "path": str(report_dir),
                "command": command,
                "warnings": [{"type": "html_report_cleanup_failed", "message": str(sanitize_perf_payload(str(exc)))}],
            }
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "warning",
            "path": str(report_dir),
            "command": command,
            "warnings": [
                {
                    "type": "html_report_timeout",
                    "message": f"JMeter HTML report generation exceeded {timeout}s.",
                    "stdout": _limit_text(exc.stdout or "", 4000),
                    "stderr": _limit_text(exc.stderr or "", 4000),
                }
            ],
        }
    result = {
        "status": "completed" if completed.returncode == 0 else "warning",
        "path": str(report_dir),
        "index_path": str(report_dir / "index.html") if (report_dir / "index.html").exists() else None,
        "command": command,
        "returncode": completed.returncode,
        "stdout": _limit_text(completed.stdout or ""),
        "stderr": _limit_text(completed.stderr or ""),
        "warnings": [],
    }
    if completed.returncode != 0:
        result["warnings"] = [
            {
                "type": "html_report_exit",
                "returncode": completed.returncode,
                "stdout_summary": _output_summary(completed.stdout or ""),
                "stderr_summary": _output_summary(completed.stderr or ""),
            }
        ]
    return result


def _artifact_files(artifact_dir: Path | None) -> list[dict[str, Any]]:
    if artifact_dir is None:
        return []
    entries = [
        ("jmx", artifact_dir / "plan.jmx"),
        ("jtl", artifact_dir / "result.jtl"),
        ("stdout", artifact_dir / "stdout.log"),
        ("stderr", artifact_dir / "stderr.log"),
        ("html_report_index", artifact_dir / "report" / "index.html"),
    ]
    files = [_file_meta(kind, path) for kind, path in entries]
    report_dir = artifact_dir / "report"
    if report_dir.exists():
        files.append({"kind": "html_report", "path": str(report_dir), "size_bytes": _directory_size(report_dir)})
    return [item for item in files if item is not None]


def _file_meta(kind: str, path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        return {"kind": kind, "path": str(path), "size_bytes": path.stat().st_size}
    except OSError:
        return None


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except OSError:
        return total
    return total


def _path_if_exists(path: Path) -> str | None:
    try:
        return str(path) if path.exists() else None
    except OSError:
        return None


def _output_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _limit_text("\n".join(lines[-10:]), 4000)


def _limit_text(text: str | None, limit: int = MAX_OUTPUT_CHARS) -> str:
    value = "" if text is None else str(text)
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_success(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "success", "passed"}


def _looks_like_path(value: str) -> bool:
    return any(part in value for part in ("\\", "/", ".exe", ".bat", ".cmd"))


def _duration_seconds(started: float) -> int:
    return max(0, int(round(time.perf_counter() - started)))
