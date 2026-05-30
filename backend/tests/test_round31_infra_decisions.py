from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import API_PREFIX, data_of


pytestmark = pytest.mark.contract

REQUIRED_CAPABILITIES = {
    "database/sqlite",
    "database/postgresql",
    "vector/pgvector",
    "migration/alembic",
    "queue/local_jobs",
    "queue/celery_redis",
    "object_storage/local_artifacts",
    "object_storage/s3_minio",
    "secrets/env_refs",
    "secrets/encrypted_store",
}
DEFERRED_CAPABILITIES = {
    "database/postgresql",
    "vector/pgvector",
    "migration/alembic",
    "queue/celery_redis",
    "object_storage/s3_minio",
}
R31_EXTERNAL_DEPENDENCIES = {"psycopg", "celery", "redis", "boto3", "minio", "cryptography", "alembic"}


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def test_infra_status_exposes_machine_readable_capability_matrix(client):
    status = data_of(client.get(f"{API_PREFIX}/system/infra-status"))

    assert status["status"] == "ok", status
    assert status["external_connection_test_performed"] is False, status

    capabilities = status["capabilities"]
    assert REQUIRED_CAPABILITIES <= set(capabilities), capabilities
    assert set(status["matrix"]) == {"supported", "deferred", "unsupported"}, status["matrix"]

    for name, capability in capabilities.items():
        assert capability["status"] in {"supported", "deferred", "unsupported"}, capability
        assert capability["supported"] is (capability["status"] == "supported"), capability
        assert name in status["matrix"][capability["status"]], (name, capability, status["matrix"])

    assert capabilities["database/sqlite"]["status"] == "supported", capabilities["database/sqlite"]
    assert capabilities["queue/local_jobs"]["status"] == "supported", capabilities["queue/local_jobs"]
    assert capabilities["object_storage/local_artifacts"]["status"] == "supported", capabilities["object_storage/local_artifacts"]
    assert capabilities["secrets/env_refs"]["status"] == "supported", capabilities["secrets/env_refs"]
    assert capabilities["secrets/encrypted_store"]["status"] == "unsupported", capabilities["secrets/encrypted_store"]


def test_infra_status_does_not_mark_deferred_capabilities_as_supported(client):
    status = data_of(client.get(f"{API_PREFIX}/system/infra-status"))
    capabilities = status["capabilities"]

    for name in DEFERRED_CAPABILITIES:
        assert capabilities[name]["status"] == "deferred", capabilities[name]
        assert capabilities[name]["supported"] is False, capabilities[name]
        assert name not in status["matrix"]["supported"], status["matrix"]


def test_infra_status_redacts_non_sqlite_url_and_does_not_connect(client, monkeypatch):
    monkeypatch.setenv(
        "AITEST_DATABASE_URL",
        "postgresql+psycopg://round31_user:round31_secret@r31-db.internal:5432/r31_db?sslmode=require",
    )

    status = data_of(client.get(f"{API_PREFIX}/system/infra-status"))
    database_url = status["database_url"]

    assert database_url["scheme"] == "postgresql", database_url
    assert database_url["driver"] == "psycopg", database_url
    assert database_url["status"] == "deferred", database_url
    assert database_url["classification"] == "experimental/deferred", database_url
    assert database_url["connection_test_performed"] is False, database_url
    assert database_url["credential_present"] is True, database_url
    assert database_url["host_present"] is True, database_url
    assert database_url["host_disclosed"] is False, database_url
    assert database_url["credentials_disclosed"] is False, database_url
    assert status["capabilities"]["database/postgresql"]["enabled"] is True, status["capabilities"]["database/postgresql"]
    assert status["capabilities"]["database/postgresql"]["supported"] is False, status["capabilities"]["database/postgresql"]

    dumped = payload_text(status)
    for forbidden in ("round31_user", "round31_secret", "r31-db.internal", "r31_db"):
        assert forbidden not in dumped, dumped


def test_infra_status_does_not_leak_sqlite_absolute_paths(client, monkeypatch, tmp_path):
    sqlite_path = tmp_path / "secret-dir" / "round31.sqlite3"
    monkeypatch.setenv("AITEST_DATABASE_URL", f"sqlite:///{sqlite_path}")

    status = data_of(client.get(f"{API_PREFIX}/system/infra-status"))
    database_url = status["database_url"]
    dumped = payload_text(status)

    assert database_url["scheme"] == "sqlite", database_url
    assert database_url["status"] == "supported", database_url
    assert database_url["safe_descriptor"] == "sqlite:///<redacted-file>", database_url
    assert database_url["path_disclosed"] is False, database_url
    assert str(sqlite_path) not in dumped, dumped
    assert str(tmp_path) not in dumped, dumped
    assert "secret-dir" not in dumped, dumped
    assert not re.search(r"[A-Za-z]:\\\\", dumped), dumped


def test_infra_status_dependency_probe_is_passive_and_no_production_dependencies_added(client):
    status = data_of(client.get(f"{API_PREFIX}/system/infra-status"))
    dependencies = status["dependencies"]

    assert R31_EXTERNAL_DEPENDENCIES <= set(dependencies), dependencies
    for name in R31_EXTERNAL_DEPENDENCIES:
        probe = dependencies[name]
        assert probe["probe"] == "importlib.util.find_spec", probe
        assert probe["import_performed"] is False, probe
        assert probe["enabled"] is False, probe
        assert probe["decision"] == "not_installed_or_not_enabled", probe

    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in R31_EXTERNAL_DEPENDENCIES:
        assert dependency not in pyproject, dependency


def test_infra_status_migration_readiness_requires_approval(client):
    status = data_of(client.get(f"{API_PREFIX}/system/infra-status"))
    readiness = status["migration_readiness"]

    assert readiness["schema_status_available"] is True, readiness
    assert readiness["backup_restore_available"] is True, readiness
    assert readiness["requires_approval"] is True, readiness
    assert readiness["alembic_enabled"] is False, readiness
