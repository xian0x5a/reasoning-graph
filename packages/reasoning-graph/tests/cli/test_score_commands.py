"""Seed and expand reject score and anchoring violations without touching state."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.cli import starter_state


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from reasoning_graph.cli import main; raise SystemExit(main())", *args],
        capture_output=True,
        text=True,
        cwd=PACKAGE_ROOT,
    )


def valid_patch() -> dict:
    return {
        "nodes": [
            {"id": "A2", "type": "assumption", "text": "Second branch", "prior": 0.5},
            {"id": "D1", "type": "derived", "text": "Conclusion"},
            {"id": "E2", "type": "evidence", "text": "Reading", "confidence": 0.9},
        ],
        "edges": [
            {"id": "A2-D1", "from": "A2", "to": "D1", "type": "leads_to",
             "reasoning": "The conclusion rests on this premise."},
            {"id": "E2-D1", "from": "E2", "to": "D1", "type": "leads_to",
             "reasoning": "The conclusion rests on this reading."},
        ],
        "frontier": [{"id": "Q2", "node": "D1", "cost_components": {"truth": "auto"}}],
    }


def patch_for(invalid_part: str) -> dict:
    patch = valid_patch()
    if invalid_part == "missing_score":
        del patch["nodes"][0]["prior"]
    elif invalid_part == "derived_local_score":
        patch["nodes"][1]["confidence"] = 0.9
    elif invalid_part == "unanchored_derived":
        patch["edges"] = [edge for edge in patch["edges"] if edge["type"] != "leads_to"]
    elif invalid_part == "derived_posterior_only":
        patch["edges"] = [edge for edge in patch["edges"] if edge["type"] != "leads_to"]
        patch["nodes"][1] = {"id": "D1", "type": "derived", "text": "Conclusion"}
    elif invalid_part == "removed_probability":
        patch["nodes"][0] = {"id": "A2", "type": "assumption", "text": "Second branch", "probability": 0.5}
    elif invalid_part == "missing_reasoning":
        del patch["edges"][0]["reasoning"]
    elif invalid_part == "long_reasoning":
        patch["edges"][0]["reasoning"] = "Sentence. " * 6
    else:  # update_score
        patch["update_nodes"] = [{"id": "G1", "set": {"prior": None}}]
    return patch


INVALID_PARTS = {
    "missing_score": "schema",
    "derived_local_score": "schema",
    "unanchored_derived": "leads_to",
    "derived_posterior_only": "leads_to",
    "removed_probability": "schema",
    "missing_reasoning": "schema",
    "long_reasoning": "schema",
    "update_score": "prior",
}


@pytest.mark.parametrize("command", ["seed", "expand"])
@pytest.mark.parametrize("invalid_part", sorted(INVALID_PARTS))
def test_invalid_patch_does_not_modify_state(tmp_path, command, invalid_part):
    state = starter_state("default")
    state["frontier"] = [{"id": "Q1", "node": "G1"}]
    state_path = tmp_path / "state.json"
    patch_path = tmp_path / "patch.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    if command == "expand":
        assert run("next", str(state_path), "--pop").returncode == 0
    original = state_path.read_bytes()

    patch_path.write_text(json.dumps(patch_for(invalid_part)), encoding="utf-8")
    args = [command, str(state_path), "--patch", str(patch_path)]
    if command == "expand":
        args += ["--item", "Q1"]
    result = run(*args)
    assert result.returncode != 0
    assert INVALID_PARTS[invalid_part] in result.stderr
    assert state_path.read_bytes() == original


@pytest.mark.parametrize("command", ["seed", "expand"])
def test_valid_patch_still_applies(tmp_path, command):
    state = starter_state("default")
    state["frontier"] = [{"id": "Q1", "node": "G1"}]
    state_path = tmp_path / "state.json"
    patch_path = tmp_path / "patch.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    if command == "expand":
        assert run("next", str(state_path), "--pop").returncode == 0

    patch_path.write_text(json.dumps(valid_patch()), encoding="utf-8")
    args = [command, str(state_path), "--patch", str(patch_path)]
    if command == "expand":
        args += ["--item", "Q1"]
    assert run(*args).returncode == 0
