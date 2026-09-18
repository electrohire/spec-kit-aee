"""Real-engine regression coverage for all six adapter operations."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from specify_cli.extensions import ExtensionManifest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/python/run_aee.py"


def test_manifest_uses_supported_dependency_metadata() -> None:
    manifest = ExtensionManifest(ROOT / "extension.yml")
    assert manifest.id == "aee"
    requires = manifest.data["requires"]
    assert "commands" not in requires
    tools = {tool["name"]: tool for tool in requires["tools"]}
    assert set(tools) == {"python", "aee", "spec-kit-evaluator"}
    assert all(tool["required"] for tool in tools.values())
    assert "1.0.2" in SpecifierSet(tools["aee"]["version"])
    assert "1.0.1" not in SpecifierSet(tools["aee"]["version"])
    for group in ("commands", "templates", "scripts", "config"):
        for item in manifest.data["provides"][group]:
            assert (ROOT / item.get("file", item.get("template", ""))).is_file()
    names = {command["name"] for command in manifest.commands}
    assert len(names) == 6
    assert len(manifest.hooks) == 5
    assert all(hook["command"] in names for hook in manifest.hooks.values())


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert shutil.which("aee"), "Activate the environment containing requirements/dev.txt"
    shutil.copyfile(ROOT / "templates/aee-claims.json", tmp_path / "claims.json")
    return tmp_path


def run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--project-root", str(project), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def test_unsupported_template_assessment_gate_and_ledger(project: Path) -> None:
    original = (project / "claims.json").read_bytes()
    result = run(project, "assess", "--input", "claims.json", "--phase", "after_specify")
    assert result.returncode == 1, result.stderr
    paths = json.loads(result.stdout)
    assessment = json.loads((project / paths["assessment"]).read_text())
    evaluator = json.loads((project / paths["evaluator_result"]).read_text())
    assert assessment["outcome"] in {"iterate", "clarify", "gather_evidence"}
    assert evaluator["outcome"] == assessment["outcome"]
    assert evaluator["phase"] == "after_specify"
    assert (project / "claims.json").read_bytes() == original
    gate = run(project, "gate", "--input", paths["assessment"])
    assert gate.returncode == 1, gate.stderr
    verified = run(project, "verify")
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["valid"] is True
    ledger = project / paths["ledger"]
    entry = json.loads(ledger.read_text().splitlines()[0])
    entry["actor"] = "tampered"
    ledger.write_text(json.dumps(entry) + "\n")
    invalid = run(project, "verify")
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["valid"] is False


def test_graph_and_challenge_write_real_results(project: Path) -> None:
    graph = run(project, "graph", "--input", "claims.json")
    assert graph.returncode == 0, graph.stderr
    graph_path = project / json.loads(graph.stdout)["graph"]
    assert "REQ-LATENCY-001" in graph_path.read_text()
    claims = json.loads((project / "claims.json").read_text())
    # Deliberately assert support without evidence/boundaries to exercise challenges.
    claims["claims"][0]["status"] = "supported"
    claims["claims"][0]["boundary"] = []
    (project / "claims.json").write_text(json.dumps(claims))
    challenge = run(project, "challenge", "--input", "claims.json")
    assert challenge.returncode == 1, challenge.stderr
    value = json.loads((project / json.loads(challenge.stdout)["challenge"]).read_text())
    assert value["mode"] == "challenge"
    assert value["failures"]
    assert value["recoveries"]


def test_gaps_stdout_output_and_evidence(project: Path) -> None:
    (project / "matrix.md").write_text(
        "| Test ID | Requirements | Layer | Gate |\n"
        "| T-API-001 | Returns 200 | integration | gate-1 |\n"
    )
    (project / "evidence").mkdir()
    args = ("gaps", "--matrix", "matrix.md", "--evidence", "evidence")
    printed = run(project, *args)
    assert printed.returncode == 0, printed.stderr
    assert "Open: 1 | Closed: 0" in printed.stdout
    assert not (project / "GAPS.md").exists()
    output = run(project, *args, "--output", "GAPS.md")
    assert output.returncode == 0, output.stderr
    assert "**Open:** 1" in (project / "GAPS.md").read_text()
    (project / "evidence/result.json").write_text(json.dumps({
        "results": [{"test_id": "T-API-001", "status": "pass"}]
    }))
    closed = run(project, *args, "--output", "GAPS.md")
    assert closed.returncode == 0, closed.stderr
    assert "**Open:** 0 | **Closed:** 1" in (project / "GAPS.md").read_text()


def test_no_ledger_flag(project: Path) -> None:
    result = run(project, "assess", "--input", "claims.json", "--no-ledger")
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["ledger"] is None
    assert not (project / ".specify/extensions/aee/ledger").exists()
