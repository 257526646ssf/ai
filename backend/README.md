# AI Test Platform Backend

This backend is expected to run as a local-first FastAPI service under `backend/`.
The first-round acceptance target is a runnable `/api/v2` subset for projects, requirements, test points, test cases, executions, reports, backup, and the unified response envelope.

## Runtime Mode

- Default mode: local-first FastAPI service.
- Default database: SQLite at `backend/data/aitest.sqlite3`.
- Formal deployment can later switch to PostgreSQL, but P0 tests must run offline without real LLM, browser runner, JMeter, or external network calls.

## Install

From `D:\codex-project\新ui-前端\backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

If the machine already has `fastapi`, `sqlalchemy`, `pytest`, and `httpx`, you can run the tests directly without reinstalling dependencies.

## Configure

```powershell
Copy-Item .env.example .env
```

Real secrets must not be committed. By default `AITEST_ENABLE_REAL_LLM=false`, so LLM config tests and chat use safe offline fallback responses without network access.

To enable a local OpenAI-compatible `/v1` service, set these values only in your local environment or uncommitted `.env`:

```powershell
$env:AITEST_ENABLE_REAL_LLM = "true"
$env:AITEST_LLM_BASE_URL = "http://127.0.0.1:PORT/v1"
$env:AITEST_LLM_API_KEY = "<local-api-key>"
$env:AITEST_LLM_MODEL = "<model-name>"
```

`POST /api/v2/llm-configs/{configId}/test` calls `{base_url}/models` when real LLM mode is enabled. `POST /api/v2/chat` calls `{base_url}/chat/completions` using the selected enabled LLM config. API keys are read from environment variables only and are redacted from responses.

When `AITEST_ENABLE_REAL_LLM=true`, the main requirement chain can also call the configured OpenAI-compatible chat completions endpoint:

- `POST /api/v2/requirement-documents/{documentId}/extract-items`
- `POST /api/v2/requirement-items/{itemId}/generate-test-points`
- `POST /api/v2/requirement-items/{itemId}/generate-test-cases`

The provider must return JSON. Markdown JSON fences are accepted. Provider errors, missing config, invalid JSON, or empty structured output fall back to the deterministic local placeholder path and record fallback metadata on the `GenerationJob`.

## Run

Start the FastAPI service with Uvicorn:

```powershell
python -m uvicorn aitest_platform.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI should be available at:

```text
http://127.0.0.1:8000/docs
```

## Schema Status

`GET /api/v2/system/schema-status` checks the SQLAlchemy model metadata against the current database engine without Alembic or destructive changes. It reports missing tables, missing columns, extra table count, a metadata hash schema version, and a redacted database type. For SQLite responses include only `database_url_type: "sqlite"` and whether the configured database file exists; the full local path is not returned. Introspection failures are returned as structured `status: "error"` payloads instead of HTTP 500 responses.

## System Restore

`POST /api/v2/system/restore` defaults to safe merge mode. Send a backup `data_json` object as `data`, a full backup snapshot containing `data_json`, or table arrays such as `projects` and `api_test_libs` at the request root. Set `dry_run=true`, `preview=true`, or `mode="preview"` to return counts without writing to the database.

Merge restore upserts supported Round 9 tables by `id`, skipping records whose dependencies are missing or whose values violate database constraints. `mode="overwrite"` requires `confirm_text="RESTORE"` and is currently guarded to run the same merge logic while returning `overwrite_requested=true`; it does not clear tables. LLM config restore never restores plaintext API keys and forces `api_key_ref` to `null`.

## Test

Run all backend acceptance tests:

```powershell
python -m pytest
```

Run only contract tests:

```powershell
python -m pytest -m contract
```

## Acceptance Scope

The tests in `tests/` cover the P0 contract from `docs/orchestration/ACCEPTANCE.md`:

- FastAPI app import and TestClient bootstrapping.
- Unified response envelope with `code`, `message`, `data`, and request trace metadata.
- `GET /api/v2/projects`.
- Create `Project`, `RequirementLib`, and `RequirementDocument`.
- Requirement document placeholder chain: `parse`, `extract-items`, and item `confirm`.
- Generate `TestPoint` from a `RequirementItem`.
- Generate `TestCase` from a `RequirementItem`.
- Create single and batch `Execution` records from test cases.
- Generate a project-scoped report snapshot.
- Export a JSON backup snapshot.

If the API worker has not implemented these routes yet, the tests are expected to fail with explicit route/import/assertion messages. They are intentionally not skipped, because they are first-round acceptance gates.

## Round 2 Contract Scope

`tests/test_round2_persistence.py` adds second-round contract coverage for persisted P1 assets:

- API testing chain: project -> API test library -> imported endpoint -> generated API cases -> single and batch executions -> environment -> scenario -> schedule, with list readback checks.
- Automation chain: project -> automation project -> generated framework -> generated case files -> execution -> event stream -> download metadata.
- Performance chain: project -> performance plan -> generated plan -> generated script -> execution result -> report metadata.
- Configuration chain: report template CRUD, LLM config create/update/test/statistics, prompt template list/update/test.
- Security contract: responses must not contain the literal `sk-secret-round2` when an LLM API key is submitted.
- System discovery: operation logs and search must return Round 2 assets.

These tests are intentionally strict. If implementation is still placeholder-only or in-memory for a Round 2 module, the failing assertion identifies the missing persistence/readback contract.

## Round 6 Performance Runner

`POST /api/v2/perf-plans/{planId}/execute` keeps the deterministic placeholder result by default. To run a real JMeter plan, send `{"real": true}` or `{"mode": "real"}`; when a plan already has `jmx_script`, `{"use_jmeter": true}` also opts in. The runner uses the local `jmeter` CLI, or a payload `jmeter_path`, persists `plan.jmx`, `result.jtl`, `stdout.log`, and `stderr.log` under `backend/data/artifacts/perf/<run_id>/`, parses basic CSV/XML JTL metrics, and stores the result in `PerfResult`. Tests can override the artifact base directory with payload `artifact_root`, and `raw_data_path` points to the persisted JTL when it exists. Set `generate_html_report` or `html_report` to `true` to attempt a JMeter dashboard under the same artifact directory; report generation has its own timeout and returns structured warnings without discarding parsed JTL results. Missing JMeter, timeout, script failure, and parse failure are returned as structured result rows instead of HTTP 500. `timeout`/`timeout_s`/`timeout_seconds` defaults to 60 seconds and is clamped to 1-1800 seconds.

## Round 3 LLM Contract Scope

`tests/test_round3_llm_integration.py` adds LLM integration and security acceptance coverage:

- Disabled or unset `AITEST_ENABLE_REAL_LLM` must not call network for `/api/v2/llm-configs/{configId}/test`.
- Disabled chat must return a structured fallback response and must not echo submitted secrets.
- Enabled LLM config test uses a monkeypatched mock client, returns connected/ok, and records usage.
- Enabled chat uses a monkeypatched mock client, returns the mock model reply, and records usage.
- Error responses must not include submitted API key values, Authorization values, or token values.

Use only fake test secrets such as `sk-round3-test-secret` in tests. Real provider keys must stay in runtime environment variables only and must not be written to tests, docs, logs, or command output.

## Round 4 Main Chain LLM Contract Scope

`tests/test_round4_main_chain_llm.py` adds LLM-backed main-chain acceptance coverage:

- Disabled mode must not call network and must keep deterministic placeholder persistence for requirement extraction, test point generation, and test case generation.
- Enabled mode can consume mocked OpenAI-compatible JSON and persist RequirementItem, TestPoint, and TestCase fields.
- Bad JSON, empty structured output, or provider errors must fall back without returning 500.
- `LlmUsage` must record `requirement_extract`, `test_point_generation`, and `test_case_generation`.
- Submitted API keys, Authorization headers, token fields, and agent-style keys must not be echoed in responses, errors, logs, or job payloads.

Use only fake test secrets such as `sk-round4-test-secret` or `agt_codex_round4_fake_secret` in tests. Real provider keys must stay in local environment variables only.

## Round 5 API Runner Contract Scope

`tests/test_round5_api_runner.py` adds real API execution acceptance coverage:

- `POST /api/v2/apis/debug` uses the `httpx` runner and returns request/response snapshots plus assertion results.
- `POST /api/v2/api-test-cases/{caseId}/execute` executes a real request when an environment or base URL is available and persists `ApiExecution`.
- `POST /api/v2/api-test-cases/batch-executions` reuses the same runner for multiple cases.
- Status code assertion failures produce `failed` execution records, not HTTP 500 responses.
- Timeout/request errors produce `error` execution records with redacted error messages.
- Missing environment/base URL keeps the Round 2 placeholder fallback for compatibility.
- Submitted or returned Authorization, API key, token, cookie, secret, and password values must not be echoed in API responses or execution payloads.

## Round 6 Automation Runner Scope

`POST /api/v2/auto-projects/{autoProjectId}/execute` runs persisted `AutoCaseFile` content locally when case files exist. It writes files to a temporary workspace, uses the current Python interpreter, prefers `python -m pytest` for `tests/` or test files, and falls back to `python <file>` for non-pytest Python files. Supported payload fields are `case_file_ids`, `timeout_ms` (1s-300s, default 30s), `env`, `mode` (`auto`, `pytest`, or `python`), and optional `artifact_root` for test-only artifact directory overrides. Subprocess failures and timeouts are stored as structured `AutoExecution` records instead of HTTP 500 responses.

Runner evidence is persisted under `backend/data/artifacts/auto/<run_id>/` by default. The runner always writes a redacted `runner.log` and returns `artifacts.evidence` metadata for recognized files such as screenshots (`.png`, `.jpg`, `.jpeg`, `.webp`), traces (`.zip`), videos (`.mp4`, `.webm`), JUnit/XML (`.xml`), HTML reports (`.html`), and logs (`.log`). Missing evidence files do not fail the execution, and runner logs/artifacts redact Authorization, API key, token, cookie, secret, password, and git auth values.

## Round 7 API Import Scope

`POST /api/v2/api-test-libs/{libId}/import-documents` and `POST /api/v2/api-test-libs/{libId}/apis/import` accept manual API payloads, OpenAPI/Swagger JSON, Postman Collection JSON, and curl commands. Use `source_type`, `type`, or `import_source` with `openapi`, `swagger`, `postman`, or `curl`; document content can be passed through `content`, `schema`, `document`, `raw_content`, or `text`. Manual payloads with `{name, method, path}` or `{apis: [...]}` remain compatible. Set `generate_cases`, `create_cases`, or `create_test_cases` to `true` to create one status-code assertion `ApiTestCase` per imported endpoint. Import parsing uses Python standard library only and redacts Authorization, API key, token, cookie, secret, and password values from stored schemas and responses.
