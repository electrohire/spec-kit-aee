"""Catalog freshness: catalog.json must agree with extension.yml.

The catalog once published the aee extension at 1.5.2 for two weeks
after extension.yml moved on, and its command count lagged the
message-security command added later. These tests pin the three
surfaces that state the same facts (catalog.json, extension.yml,
and the runner's engine floor) to each other so the next drift
fails CI instead of shipping silently.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"
MANIFEST = ROOT / "extension.yml"
RUNNER = ROOT / "scripts" / "python" / "run_aee.py"


def _catalog_aee() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["extensions"]["aee"]


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _engine_floor_from(entries: list[dict]) -> str:
    for entry in entries:
        if entry.get("name") == "aee":
            return entry["version"]
    raise AssertionError("no aee tool requirement found")


def _runner_engine_floor() -> str:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "REQUIRED_AEE_VERSION"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("REQUIRED_AEE_VERSION not found in run_aee.py")


def test_catalog_version_matches_manifest() -> None:
    assert _catalog_aee()["version"] == _manifest()["extension"]["version"]


def test_catalog_command_count_matches_manifest() -> None:
    declared = _manifest()["provides"]["commands"]
    assert _catalog_aee()["provides"]["commands"] == len(declared)


def test_engine_floor_agrees_everywhere() -> None:
    floors = {
        _engine_floor_from(_catalog_aee()["requires"]["tools"]),
        _engine_floor_from(_manifest()["requires"]["tools"]),
        _runner_engine_floor(),
    }
    assert len(floors) == 1, f"engine floor drift: {sorted(floors)}"
