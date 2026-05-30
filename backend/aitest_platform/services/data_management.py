from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from aitest_platform.db.session import get_engine
from aitest_platform.models import (
    ApiExecution,
    ApiTestLib,
    BackupSnapshot,
    Defect,
    Execution,
    OperationLog,
)


BACKUP_STALE_DAYS = 7
ALLOWED_CLEANUP_MODULES = {"execution_history", "api_execution_history", "artifacts"}
SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password", "git_auth")
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|api-key|apikey|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"']+"
)
AUTH_VALUE_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;}\"']+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"\b(?:\+?86[- ]?)?1[3-9]\d{9}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


class DataManagementError(ValueError):
    pass


def backup_status(session: Session, project_id: int | None = None) -> dict[str, Any]:
    stmt = select(BackupSnapshot)
    if project_id is not None:
        stmt = stmt.where(BackupSnapshot.project_id == project_id)
    stmt = stmt.order_by(BackupSnapshot.created_at.desc(), BackupSnapshot.id.desc())
    latest = session.scalar(stmt.limit(1))
    if latest is None:
        return {
            "project_id": project_id,
            "latest": None,
            "latest_backup": None,
            "needs_backup": True,
            "reason": "no_backup_found",
            "stale_after_days": BACKUP_STALE_DAYS,
        }

    latest_payload = public_backup_snapshot(latest)
    created_at = _as_utc(latest.created_at)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds())
    age_days = age_seconds / 86400
    latest_payload["age_days"] = round(age_days, 2)
    needs_backup = age_days > BACKUP_STALE_DAYS
    return redact_payload(
        {
            "project_id": project_id,
            "latest": latest_payload,
            "latest_backup": latest_payload,
            "needs_backup": needs_backup,
            "reason": "stale_backup" if needs_backup else "fresh_backup",
            "stale_after_days": BACKUP_STALE_DAYS,
        }
    )


def public_backup_snapshot(snapshot: BackupSnapshot) -> dict[str, Any]:
    return redact_payload(
        {
            "id": snapshot.id,
            "backup_id": snapshot.id,
            "project_id": snapshot.project_id,
            "name": snapshot.name,
            "created_at": _iso(snapshot.created_at),
        }
    )


def storage_summary(session: Session) -> dict[str, Any]:
    backend_root = _backend_root()
    data_root = backend_root / "data"
    artifact_root = data_root / "artifacts"
    module_root = backend_root / "aitest_platform"

    sections = {
        "db": _db_section(session),
        "artifacts": _directory_section(artifact_root),
        "backups": _backup_section(session, data_root / "backups"),
        "modules": _directory_section(module_root, suffixes={".py"}),
    }
    total_bytes = sum(section["bytes"] for section in sections.values())
    total_count = sum(section["count"] for section in sections.values())
    return redact_payload(
        {
            "sections": sections,
            "total_bytes": total_bytes,
            "total_count": total_count,
            "human_readable": _human_size(total_bytes),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def cleanup_system(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    modules = _requested_modules(payload)
    unknown = sorted(set(modules) - ALLOWED_CLEANUP_MODULES)
    if unknown:
        raise DataManagementError(f"unsupported cleanup module: {', '.join(unknown)}")

    dry_run = _truthy(payload.get("dry_run", payload.get("dryRun", True)))
    if not dry_run and payload.get("confirm_text") != "CLEANUP":
        raise DataManagementError('confirm_text must be "CLEANUP" for cleanup execution')

    project_id = _optional_int(payload.get("project_id") if payload.get("project_id") is not None else payload.get("projectId"), "project_id")
    older_than_days = _safe_int(payload.get("older_than_days") or payload.get("olderThanDays"), default=30)
    if older_than_days < 0:
        raise DataManagementError("older_than_days must be greater than or equal to 0")
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    module_results: dict[str, Any] = {}
    total_records = 0
    total_files = 0
    total_bytes = 0

    if "execution_history" in modules:
        result = _cleanup_execution_history(session, project_id=project_id, cutoff=cutoff, dry_run=dry_run)
        module_results["execution_history"] = result
        total_records += result["record_count"]

    if "api_execution_history" in modules:
        result = _cleanup_api_execution_history(session, project_id=project_id, cutoff=cutoff, dry_run=dry_run)
        module_results["api_execution_history"] = result
        total_records += result["record_count"]

    if "artifacts" in modules:
        result = _cleanup_artifacts(payload, dry_run=dry_run)
        module_results["artifacts"] = result
        total_files += result["file_count"]
        total_bytes += result["bytes"]

    response = {
        "dry_run": dry_run,
        "mode": "dry_run" if dry_run else "execute",
        "project_id": project_id,
        "older_than_days": older_than_days,
        "modules": module_results,
        "record_count": total_records,
        "row_count": total_records,
        "file_count": total_files,
        "bytes": total_bytes,
        "size_bytes": total_bytes,
        "human_readable": _human_size(total_bytes),
    }
    if not dry_run:
        session.add(
            OperationLog(
                module="system_cleanup",
                action="cleanup",
                target_type="project",
                target_id=project_id,
                detail=redact_payload(
                    {
                        "modules": modules,
                        "record_count": total_records,
                        "file_count": total_files,
                        "bytes": total_bytes,
                    }
                ),
            )
        )
    return redact_payload(response)


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                clean[key] = "***"
            else:
                clean[key] = redact_payload(item)
        return clean
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
        text = AUTH_VALUE_RE.sub("***", text)
        text = PHONE_RE.sub("15500000000", text)
        text = CARD_RE.sub(_redact_card_like, text)

        def email_replacer(match: re.Match[str]) -> str:
            domain = match.group(1).lower()
            if domain.endswith(("example.com", "example.org", "example.net", "example.test", "invalid.test")):
                return match.group(0)
            return "user@example.com"

        return EMAIL_RE.sub(email_replacer, text)
    return value


def _cleanup_execution_history(session: Session, *, project_id: int | None, cutoff: datetime, dry_run: bool) -> dict[str, Any]:
    stmt = select(Execution).where(Execution.executed_at < cutoff)
    if project_id is not None:
        stmt = stmt.where(Execution.project_id == project_id)
    records = list(session.scalars(stmt.order_by(Execution.id)))
    record_ids = [record.id for record in records]
    if not dry_run and record_ids:
        for defect in session.scalars(select(Defect).where(Defect.execution_id.in_(record_ids))):
            defect.execution_id = None
        for record in records:
            session.delete(record)
        session.flush()
    return {
        "dry_run": dry_run,
        "record_count": len(records),
        "row_count": len(records),
        "deleted_record_count": 0 if dry_run else len(records),
        "scope": "execution_record",
    }


def _cleanup_api_execution_history(session: Session, *, project_id: int | None, cutoff: datetime, dry_run: bool) -> dict[str, Any]:
    stmt = select(ApiExecution).where(ApiExecution.executed_at < cutoff)
    if project_id is not None:
        stmt = stmt.join(ApiTestLib, ApiTestLib.id == ApiExecution.lib_id).where(ApiTestLib.project_id == project_id)
    records = list(session.scalars(stmt.order_by(ApiExecution.id)))
    if not dry_run:
        for record in records:
            session.delete(record)
        session.flush()
    return {
        "dry_run": dry_run,
        "record_count": len(records),
        "row_count": len(records),
        "deleted_record_count": 0 if dry_run else len(records),
        "scope": "api_execution",
    }


def _cleanup_artifacts(payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    root = _resolve_artifact_root(payload.get("artifact_root") or payload.get("artifactRoot"))
    paths = payload.get("paths") or payload.get("relative_paths") or payload.get("relativePaths")
    targets = _resolve_artifact_targets(root, paths)
    files = _artifact_files_for_targets(root, targets)
    total_bytes = sum(_safe_file_size(path) for path in files)

    deleted = 0
    if not dry_run:
        for path in files:
            _ensure_within_root(path, root)
            if path.exists() and (path.is_file() or path.is_symlink()):
                path.unlink()
                deleted += 1
        _remove_empty_dirs(root, targets)

    return {
        "dry_run": dry_run,
        "root": "artifact_root",
        "file_count": len(files),
        "deleted_file_count": 0 if dry_run else deleted,
        "bytes": total_bytes,
        "size_bytes": total_bytes,
        "human_readable": _human_size(total_bytes),
        "sample_files": [_relative_display(path, root) for path in files[:20]],
    }


def _resolve_artifact_targets(root: Path, paths: Any) -> list[Path]:
    if paths in (None, "", []):
        return [root]
    raw_paths = paths if isinstance(paths, list) else [paths]
    targets: list[Path] = []
    for raw in raw_paths:
        text_value = str(raw or "").strip()
        if not text_value:
            continue
        candidate = Path(text_value).expanduser()
        if any(part == ".." for part in candidate.parts):
            raise DataManagementError("artifact path must stay inside artifact_root")
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (root / candidate).resolve()
        _ensure_within_root(resolved, root)
        targets.append(resolved)
    return targets or [root]


def _artifact_files_for_targets(root: Path, targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        _ensure_within_root(target, root)
        if not target.exists():
            continue
        candidates = [target]
        if target.is_dir():
            candidates = list(target.rglob("*"))
        for candidate in candidates:
            resolved = candidate.resolve()
            _ensure_within_root(resolved, root)
            if not (candidate.is_file() or candidate.is_symlink()):
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return files


def _resolve_artifact_root(value: Any) -> Path:
    root = Path(str(value)).expanduser() if value else _backend_root() / "data" / "artifacts"
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    else:
        root = root.resolve()
    if _is_filesystem_root(root):
        raise DataManagementError("artifact root is not allowed")
    return root


def _ensure_within_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DataManagementError("artifact path must stay inside artifact_root") from exc


def _remove_empty_dirs(root: Path, targets: list[Path]) -> None:
    dirs: list[Path] = []
    for target in targets:
        if target.exists() and target.is_dir():
            dirs.extend(path for path in target.rglob("*") if path.is_dir())
            dirs.append(target)
    for directory in sorted(set(dirs), key=lambda item: len(item.parts), reverse=True):
        if directory == root:
            continue
        _ensure_within_root(directory.resolve(), root)
        try:
            directory.rmdir()
        except OSError:
            continue


def _db_section(session: Session) -> dict[str, Any]:
    engine = session.get_bind() or get_engine()
    inspector = inspect(engine)
    table_names = [name for name in inspector.get_table_names() if not name.startswith("sqlite_")]
    row_count = 0
    for table_name in table_names:
        quoted = '"' + table_name.replace('"', '""') + '"'
        try:
            row_count += int(session.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar() or 0)
        except Exception:
            continue
    size_bytes = _database_size_bytes()
    return {
        "bytes": size_bytes,
        "size_bytes": size_bytes,
        "count": row_count,
        "record_count": row_count,
        "table_count": len(table_names),
        "human_readable": _human_size(size_bytes),
    }


def _backup_section(session: Session, backup_dir: Path) -> dict[str, Any]:
    snapshots = list(session.scalars(select(BackupSnapshot)))
    record_bytes = sum(len(json.dumps(redact_payload(public_backup_snapshot(snapshot)), ensure_ascii=False).encode("utf-8")) for snapshot in snapshots)
    dir_summary = _directory_section(backup_dir)
    total_bytes = record_bytes + dir_summary["bytes"]
    count = len(snapshots) + dir_summary["count"]
    return {
        "bytes": total_bytes,
        "size_bytes": total_bytes,
        "count": count,
        "record_count": len(snapshots),
        "file_count": dir_summary["count"],
        "human_readable": _human_size(total_bytes),
    }


def _directory_section(root: Path, *, suffixes: set[str] | None = None) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    if root.exists() and root.is_dir():
        for child in root.rglob("*"):
            if not child.is_file():
                continue
            if suffixes is not None and child.suffix.lower() not in suffixes:
                continue
            file_count += 1
            total_bytes += _safe_file_size(child)
    return {
        "bytes": total_bytes,
        "size_bytes": total_bytes,
        "count": file_count,
        "file_count": file_count,
        "human_readable": _human_size(total_bytes),
    }


def _database_size_bytes() -> int:
    engine = get_engine()
    database = getattr(engine.url, "database", None)
    if not database or database == ":memory:":
        return 0
    path = Path(database)
    if not path.is_absolute():
        path = Path.cwd() / path
    return _safe_file_size(path)


def _requested_modules(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("modules")
    if raw is None:
        raw = payload.get("module")
    if raw is None:
        raw = payload.get("scope")
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    else:
        values = []
    modules = [value for value in values if value]
    if not modules:
        raise DataManagementError("cleanup module is required")
    return list(dict.fromkeys(modules))


def _optional_int(value: Any, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DataManagementError(f"{name} must be an integer") from exc


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat()


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _human_size(size_bytes: int) -> str:
    value = float(max(0, size_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size_bytes)} B"


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _is_filesystem_root(path: Path) -> bool:
    return path == path.parent


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact_card_like(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) < 13:
        return match.group(0)
    return "4000000000000002"
