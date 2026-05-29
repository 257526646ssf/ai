from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.sql import text


class Base(DeclarativeBase):
    pass


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "aitest.sqlite3"
DATABASE_URL_ENV = "AITEST_DATABASE_URL"
DATABASE_PATH_ENV = "AITEST_DATABASE_PATH"

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_database_url() -> str:
    database_url = os.getenv(DATABASE_URL_ENV)
    if database_url:
        return database_url

    database_path = Path(os.getenv(DATABASE_PATH_ENV, str(DEFAULT_DB_PATH))).expanduser()
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    return f"sqlite:///{database_path}"


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:")


def _ensure_sqlite_parent(database_url: str) -> None:
    if not _is_sqlite_url(database_url) or database_url == "sqlite:///:memory:":
        return

    raw_path = database_url.replace("sqlite:///", "", 1)
    if raw_path:
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def get_engine(database_url: str | None = None) -> Engine:
    global _engine, _SessionLocal

    resolved_url = database_url or get_database_url()
    if _engine is not None and str(_engine.url) == resolved_url:
        return _engine

    _ensure_sqlite_parent(resolved_url)
    connect_args = {"check_same_thread": False} if _is_sqlite_url(resolved_url) else {}
    engine = create_engine(resolved_url, connect_args=connect_args, future=True)

    if _is_sqlite_url(resolved_url):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return engine


def init_db(database_url: str | None = None, drop_existing: bool = False) -> Engine:
    from aitest_platform import models  # noqa: F401

    engine = get_engine(database_url)
    if drop_existing:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_round2_columns(engine)
    return engine


def _ensure_sqlite_round2_columns(engine: Engine) -> None:
    if not _is_sqlite_url(str(engine.url)):
        return

    required_columns = {
        "api_test_lib": {
            "source_document_id": "INTEGER",
            "import_source": "VARCHAR(64)",
            "latest_sync_at": "DATETIME",
        },
        "api_endpoint": {
            "requirement_item_id": "INTEGER",
            "headers_schema": "JSON",
            "query_schema": "JSON",
            "body_schema": "JSON",
            "response_schema": "JSON",
            "description": "TEXT",
        },
        "api_test_case": {
            "requirement_item_id": "INTEGER",
            "content_type": "VARCHAR(128) NOT NULL DEFAULT 'application/json'",
            "pre_script": "TEXT",
            "post_script": "TEXT",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "api_environment": {
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
            "is_deleted": "BOOLEAN NOT NULL DEFAULT 0",
            "headers": "JSON",
            "variables": "JSON",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "api_scenario": {
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
            "data_mappings": "JSON",
        },
        "auto_project": {
            "git_repo_url": "VARCHAR(512)",
            "git_auth_ref": "VARCHAR(255)",
            "framework_files": "JSON",
            "readme": "TEXT",
        },
        "perf_plan": {
            "target_doc": "TEXT",
            "plan_schema": "JSON",
            "jmx_script": "TEXT",
            "status": "VARCHAR(32) NOT NULL DEFAULT 'draft'",
        },
        "report_template": {
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
            "template_version": "VARCHAR(32) NOT NULL DEFAULT 'v1'",
        },
        "llm_config": {
            "module_binding": "JSON",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "prompt_template": {
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
    }

    with engine.begin() as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        for table_name, columns in required_columns.items():
            if table_name not in table_names:
                continue
            existing = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            for column_name, column_sql in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def get_session() -> Session:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
