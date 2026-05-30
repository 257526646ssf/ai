from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]

from sqlalchemy.engine.url import URL, make_url

from aitest_platform.db.session import DATABASE_PATH_ENV, DATABASE_URL_ENV, get_database_url


CAPABILITY_STATUSES = {"supported", "deferred", "unsupported"}
EXTERNAL_DEPENDENCIES: dict[str, str] = {
    "psycopg": "psycopg",
    "celery": "celery",
    "redis": "redis",
    "boto3": "boto3",
    "minio": "minio",
    "cryptography": "cryptography",
    "alembic": "alembic",
}
POSTGRES_DIALECTS = {"postgresql", "postgres"}


def get_infra_status() -> dict[str, Any]:
    database = database_url_summary()
    dependencies = dependency_probe()
    capabilities = capability_matrix(database, dependencies)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "database_url": database,
        "capabilities": capabilities,
        "matrix": _group_capabilities(capabilities),
        "dependencies": dependencies,
        "migration_readiness": migration_readiness(dependencies),
        "external_connection_test_performed": False,
    }


def database_url_summary(database_url: str | None = None) -> dict[str, Any]:
    raw_url = database_url or get_database_url()
    source = _database_url_source(database_url)
    try:
        url = make_url(raw_url)
    except Exception:
        scheme = _raw_scheme(raw_url)
        return {
            "source": source,
            "scheme": scheme,
            "driver": None,
            "drivername": None,
            "dialect": scheme,
            "status": "deferred",
            "classification": "invalid_redacted",
            "safe_descriptor": "<invalid-database-url-redacted>",
            "is_sqlite": False,
            "is_external_service": True,
            "experimental": True,
            "connection_test_performed": False,
            "raw_value_exposed": False,
            "path_disclosed": False,
            "host_disclosed": False,
            "credentials_disclosed": False,
            "credential_present": _looks_like_credential_url(raw_url),
            "notes": ["Database URL could not be parsed; raw value was not returned."],
        }

    dialect, driver = _split_driver(url)
    is_sqlite = dialect == "sqlite"
    status = "supported" if is_sqlite else "deferred"
    return {
        "source": source,
        "scheme": dialect,
        "driver": driver,
        "drivername": url.drivername,
        "dialect": dialect,
        "status": status,
        "classification": "local_sqlite" if is_sqlite else "experimental/deferred",
        "safe_descriptor": _safe_descriptor(url, dialect, driver),
        "mode": _database_mode(url, dialect),
        "is_sqlite": is_sqlite,
        "is_external_service": not is_sqlite,
        "experimental": not is_sqlite,
        "connection_test_performed": False,
        "raw_value_exposed": False,
        "path_disclosed": False,
        "host_disclosed": False,
        "credentials_disclosed": False,
        "credential_present": bool(url.username or url.password) or _has_sensitive_query_key(url),
        "host_present": bool(url.host),
        "port_present": _port_present(url),
        "database_name_present": bool(url.database and not is_sqlite),
        "query_keys": _safe_query_keys(url),
        "redacted_query_key_count": len(url.query) - len(_safe_query_keys(url)),
        "notes": _database_notes(dialect),
    }


def dependency_probe() -> dict[str, dict[str, Any]]:
    pyproject = _project_dependencies()
    dependencies: dict[str, dict[str, Any]] = {}
    for name, module in EXTERNAL_DEPENDENCIES.items():
        available = importlib.util.find_spec(module) is not None
        declared_runtime = name in pyproject["runtime"]
        declared_optional = name in pyproject["optional"]
        enabled = False
        dependencies[name] = {
            "module": module,
            "available": available,
            "enabled": enabled,
            "import_performed": False,
            "probe": "importlib.util.find_spec",
            "declared_in_runtime_dependencies": declared_runtime,
            "declared_in_optional_dependencies": declared_optional,
            "declared_in_project": declared_runtime or declared_optional,
            "status": "not_enabled" if available else "not_installed",
            "decision": "not_installed_or_not_enabled",
        }
    return dependencies


def capability_matrix(database: dict[str, Any], dependencies: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    current_scheme = str(database.get("scheme") or "")
    current_driver = database.get("driver")
    postgres_selected = current_scheme in POSTGRES_DIALECTS
    return {
        "database/sqlite": _capability(
            "supported",
            enabled=current_scheme == "sqlite",
            requires_external_service=False,
            detail="SQLite is the current local-first persistence target.",
        ),
        "database/postgresql": _capability(
            "deferred",
            enabled=postgres_selected,
            experimental=postgres_selected,
            requires_external_service=True,
            dependencies=["psycopg"],
            detail="PostgreSQL is visible as a production option but is not enabled or connection-tested in R31.",
            driver=current_driver if postgres_selected else None,
        ),
        "vector/pgvector": _capability(
            "deferred",
            enabled=False,
            requires_external_service=True,
            dependencies=["psycopg"],
            detail="pgvector requires a PostgreSQL rollout and schema migration plan.",
        ),
        "migration/alembic": _capability(
            "deferred",
            enabled=False,
            dependencies=["alembic"],
            detail="Current schema readiness uses metadata introspection; Alembic migrations are not enabled.",
        ),
        "queue/local_jobs": _capability(
            "supported",
            enabled=True,
            requires_external_service=False,
            detail="Local synchronous/database-backed job records are supported for the current deployment shape.",
        ),
        "queue/celery_redis": _capability(
            "deferred",
            enabled=False,
            requires_external_service=True,
            dependencies=["celery", "redis"],
            detail="Celery with Redis is not configured and no broker connection is attempted.",
        ),
        "object_storage/local_artifacts": _capability(
            "supported",
            enabled=True,
            requires_external_service=False,
            detail="Local artifact directories are the supported storage target.",
        ),
        "object_storage/s3_minio": _capability(
            "deferred",
            enabled=False,
            requires_external_service=True,
            dependencies=["boto3", "minio"],
            detail="S3/MinIO support is deferred and no bucket/client probe is attempted.",
        ),
        "secrets/env_refs": _capability(
            "supported",
            enabled=True,
            requires_external_service=False,
            detail="Configuration may reference secrets through environment variables; values are not exposed.",
        ),
        "secrets/encrypted_store": _capability(
            "unsupported",
            enabled=False,
            dependencies=["cryptography"],
            detail="Encrypted secret storage is not implemented in this local-first backend.",
        ),
    }


def migration_readiness(dependencies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_status_available": True,
        "backup_restore_available": True,
        "rollback_strategy": "Use existing backup/restore snapshots before schema-affecting changes; Alembic rollback is deferred.",
        "requires_approval": True,
        "alembic_enabled": bool(dependencies.get("alembic", {}).get("enabled")),
        "connection_test_performed": False,
    }


def _capability(status: str, **extra: Any) -> dict[str, Any]:
    if status not in CAPABILITY_STATUSES:
        raise ValueError(f"unsupported capability status: {status}")
    return {
        "status": status,
        "supported": status == "supported",
        "deferred": status == "deferred",
        "unsupported": status == "unsupported",
        **extra,
    }


def _group_capabilities(capabilities: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    grouped = {"supported": [], "deferred": [], "unsupported": []}
    for name, details in capabilities.items():
        grouped[str(details["status"])].append(name)
    return {key: sorted(value) for key, value in grouped.items()}


def _database_url_source(explicit_url: str | None) -> str:
    if explicit_url is not None:
        return "explicit"
    import os

    if os.getenv(DATABASE_URL_ENV):
        return DATABASE_URL_ENV
    if os.getenv(DATABASE_PATH_ENV):
        return DATABASE_PATH_ENV
    return "default"


def _split_driver(url: URL) -> tuple[str, str]:
    if "+" not in url.drivername:
        return url.drivername, "default"
    dialect, driver = url.drivername.split("+", 1)
    return dialect, driver


def _safe_descriptor(url: URL, dialect: str, driver: str) -> str:
    drivername = url.drivername
    if dialect == "sqlite":
        if url.database == ":memory:":
            return "sqlite:///:memory:"
        return "sqlite:///<redacted-file>"
    if driver == "default":
        return f"{drivername}://<redacted>"
    return f"{drivername}://<redacted>"


def _database_mode(url: URL, dialect: str) -> str:
    if dialect != "sqlite":
        return "external_service"
    if url.database == ":memory:":
        return "memory"
    return "local_file"


def _database_notes(dialect: str) -> list[str]:
    if dialect == "sqlite":
        return ["SQLite URL path is redacted; no external connection test is performed."]
    if dialect in POSTGRES_DIALECTS:
        return ["Non-SQLite database URLs are treated as experimental/deferred and are not connection-tested."]
    return ["Database dialect is not part of the R31 supported runtime matrix and is not connection-tested."]


def _port_present(url: URL) -> bool:
    try:
        return url.port is not None
    except ValueError:
        return True


def _safe_query_keys(url: URL) -> list[str]:
    return sorted(str(key) for key in url.query if not _is_sensitive_key(key))


def _has_sensitive_query_key(url: URL) -> bool:
    return any(_is_sensitive_key(key) for key in url.query)


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(marker in lowered for marker in ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "password", "secret"))


def _raw_scheme(raw_url: str) -> str:
    if ":" not in raw_url:
        return "unknown"
    return raw_url.split(":", 1)[0].split("+", 1)[0].lower() or "unknown"


def _looks_like_credential_url(raw_url: str) -> bool:
    head = raw_url.split("?", 1)[0]
    return "@" in head and (":" in head.split("@", 1)[0])


def _project_dependencies() -> dict[str, set[str]]:
    if tomllib is None:
        return {"runtime": set(), "optional": set()}

    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError:
        return {"runtime": set(), "optional": set()}

    project = data.get("project", {})
    runtime = {_dependency_name(item) for item in project.get("dependencies", []) if isinstance(item, str)}
    optional: set[str] = set()
    optional_groups = project.get("optional-dependencies", {})
    if isinstance(optional_groups, dict):
        for values in optional_groups.values():
            if isinstance(values, list):
                optional.update(_dependency_name(item) for item in values if isinstance(item, str))
    return {"runtime": runtime, "optional": optional}


def _dependency_name(requirement: str) -> str:
    name = []
    for char in requirement.strip():
        if char.isalnum() or char in {"_", "-", "."}:
            name.append(char.lower().replace("_", "-"))
            continue
        break
    return "".join(name)
