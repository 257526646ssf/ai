from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import AutoCaseFile
from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

FAKE_SECRET = "round8-fake-secret-value"
EXPECTED_AUTO_EVIDENCE_TYPES = {"screenshot", "trace", "junit", "html", "log"}
EXPECTED_PERF_EVIDENCE_TYPES = {"jmx", "jtl", "stdout", "stderr", "html_report"}


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_fake_secret(payload: Any) -> None:
    dumped = payload_text(payload)
    assert FAKE_SECRET not in dumped, dumped


def assert_inside_root(path_value: Any, root: Path) -> None:
    path = Path(str(path_value)).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    else:
        path = path.resolve()
    assert path == root.resolve() or root.resolve() in path.parents, str(path)


def collect_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            if any(part in str(key).lower() for part in ("path", "file", "url", "href", "location")):
                strings.append(str(item))
            strings.extend(collect_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(collect_strings(item))
        return strings
    return []


def evidence_items(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = artifacts.get("evidence")
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    if isinstance(evidence, dict):
        return [{"type": key, **(item if isinstance(item, dict) else {"path": item})} for key, item in evidence.items()]
    return []


def evidence_types(artifacts: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for item in evidence_items(artifacts):
        raw_type = item.get("type") or item.get("kind") or item.get("artifact_type") or item.get("name")
        if raw_type:
            types.add(str(raw_type))
    return types


def assert_evidence_paths_inside_root(artifacts: dict[str, Any], root: Path) -> None:
    paths = collect_strings(artifacts.get("evidence"))
    assert paths, artifacts
    for path in paths:
        assert_inside_root(path, root)


def create_auto_project_with_artifact_case(client, *, marker: str) -> int | str:
    project_id = create_project(client)
    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {
            "name": f"round8-auto-artifacts-{marker}",
            "type": "ui",
            "language": "python",
            "framework": "pytest",
            "config": {"runner": "pytest", "token": FAKE_SECRET},
        },
    )
    auto_project_id = object_id(auto_project, "id", "auto_project_id")
    case_content = f'''
from pathlib import Path


def test_runtime_artifacts_are_created():
    root = Path.cwd()
    (root / "screenshots").mkdir(exist_ok=True)
    (root / "traces").mkdir(exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "screenshots" / "checkout.png").write_bytes(b"\\x89PNG\\r\\n\\x1a\\nround8")
    (root / "traces" / "trace.zip").write_bytes(b"PK\\x03\\x04round8-trace")
    (root / "reports" / "junit.xml").write_text("<testsuite tests='1' failures='0' />", encoding="utf-8")
    (root / "reports" / "index.html").write_text("<html>round8 report</html>", encoding="utf-8")
    (root / "logs" / "runner.log").write_text("token={FAKE_SECRET}", encoding="utf-8")
    print("token={FAKE_SECRET}")
    assert True
'''
    with session_scope() as session:
        session.add(
            AutoCaseFile(
                auto_project_id=int(auto_project_id),
                file_name="test_round8_runtime_artifacts.py",
                file_path="tests/test_round8_runtime_artifacts.py",
                content=case_content,
                case_count=1,
                automation_dsl={"steps": [{"action": "write_artifacts"}]},
            )
        )
    return auto_project_id


def create_perf_plan(client, *, marker: str) -> int | str:
    project_id = create_project(client)
    plan = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/perf-plans",
        {
            "name": f"round8-perf-artifacts-{marker}",
            "target_doc": "Round 8 artifact persistence contract.",
            "plan_schema": {"tool": "jmeter", "use_jmeter": True, "threads": 1},
            "jmx_script": "<jmeterTestPlan><hashTree /></jmeterTestPlan>",
            "status": "scripted",
        },
    )
    return object_id(plan, "id", "plan_id")


def result_of_perf_execute(response) -> dict[str, Any]:
    data = data_of(response)
    result = data.get("result") if isinstance(data, dict) and isinstance(data.get("result"), dict) else data
    assert isinstance(result, dict), data
    return result


def install_fake_jmeter(monkeypatch: pytest.MonkeyPatch, *, stderr: str = "") -> list[list[str]]:
    monkeypatch.setattr(shutil, "which", lambda name: "jmeter" if name == "jmeter" else None)
    calls: list[list[str]] = []

    def fake_run(cmd: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd_list = [str(item) for item in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        calls.append(cmd_list)
        if "-l" in cmd_list:
            jtl_path = Path(cmd_list[cmd_list.index("-l") + 1])
            jtl_path.parent.mkdir(parents=True, exist_ok=True)
            jtl_path.write_text(
                "timeStamp,elapsed,label,responseCode,success,bytes,Latency\n"
                "1,80,GET /ok,200,true,1200,60\n"
                "2,120,GET /also-ok,200,true,1300,100\n",
                encoding="utf-8",
            )
        if "-o" in cmd_list:
            html_dir = Path(cmd_list[cmd_list.index("-o") + 1])
            html_dir.mkdir(parents=True, exist_ok=True)
            (html_dir / "index.html").write_text("<html>JMeter Round8</html>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd_list, 0 if not stderr else 1, stdout="jmeter stdout", stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_auto_runner_persists_runtime_artifact_evidence_under_requested_root(tmp_path, client):
    artifact_root = tmp_path / "auto-artifacts"
    auto_project_id = create_auto_project_with_artifact_case(client, marker="success")

    execution = post_json(
        client,
        f"{API_PREFIX}/auto-projects/{auto_project_id}/execute",
        {"artifact_root": str(artifact_root), "env": {"ROUND8_TOKEN": FAKE_SECRET}},
    )

    assert execution.get("status") == "completed", execution
    artifacts = execution.get("artifacts")
    assert isinstance(artifacts, dict), execution
    found_types = evidence_types(artifacts)
    assert len(found_types & EXPECTED_AUTO_EVIDENCE_TYPES) >= 3, artifacts
    assert_evidence_paths_inside_root(artifacts, artifact_root)
    assert_no_fake_secret(execution)


def test_perf_runner_persists_jmeter_artifacts_and_html_report(tmp_path, monkeypatch, client):
    calls = install_fake_jmeter(monkeypatch)
    artifact_root = tmp_path / "perf-artifacts"
    plan_id = create_perf_plan(client, marker="success")

    result = result_of_perf_execute(
        client.post(
            f"{API_PREFIX}/perf-plans/{plan_id}/execute",
            json={"use_jmeter": True, "generate_html_report": True, "artifact_root": str(artifact_root)},
        )
    )

    assert calls, "JMeter command must be invoked through subprocess.run"
    assert result.get("status") == "completed", result
    raw_data_path = result.get("raw_data_path")
    assert raw_data_path, result
    assert_inside_root(raw_data_path, artifact_root)
    assert Path(str(raw_data_path)).exists(), result
    artifacts = result.get("artifacts")
    assert isinstance(artifacts, dict), result
    assert EXPECTED_PERF_EVIDENCE_TYPES <= evidence_types(artifacts), artifacts
    assert_evidence_paths_inside_root(artifacts, artifact_root)
    assert_no_fake_secret(result)


@pytest.mark.parametrize(
    ("which_result", "stderr"),
    [
        (None, ""),
        ("jmeter", f"token={FAKE_SECRET} jmeter failed"),
    ],
)
def test_perf_runner_error_artifacts_do_not_leak_fake_secret(tmp_path, monkeypatch, client, which_result, stderr):
    monkeypatch.setattr(shutil, "which", lambda name: which_result if name == "jmeter" else None)
    if which_result is not None:
        install_fake_jmeter(monkeypatch, stderr=stderr)
    plan_id = create_perf_plan(client, marker="error")

    result = result_of_perf_execute(
        client.post(
            f"{API_PREFIX}/perf-plans/{plan_id}/execute",
            json={"use_jmeter": True, "artifact_root": str(tmp_path / "perf-errors")},
        )
    )

    assert result.get("status") == "error", result
    assert result.get("error_details") or result.get("artifacts"), result
    assert_no_fake_secret(result.get("error_details"))
    assert_no_fake_secret(result.get("artifacts"))
