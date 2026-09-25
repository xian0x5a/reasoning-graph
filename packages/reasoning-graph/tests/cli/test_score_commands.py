"""Seed and expand reject score and anchoring violations without touching state."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.cli import starter_state
from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from reasoning_graph.cli import main; raise SystemExit(main())", *args],
        capture_output=True,
        text=True,
        cwd=PACKAGE_ROOT,
        timeout=20,
    )


def valid_patch() -> dict:
    return {
        "nodes": [
            {"id": "A2", "type": "hypothesis", "text": "Second branch", "prior": 0.5},
            {"id": "D1", "type": "hypothesis", "text": "Conclusion"},
            {"id": "E2", "type": "observation", "text": "Reading", "prior": 0.9},
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
    elif invalid_part == "unanchored_derived":
        patch["edges"] = [edge for edge in patch["edges"] if edge["type"] != "leads_to"]
    elif invalid_part == "removed_probability":
        patch["nodes"][0] = {"id": "A2", "type": "hypothesis", "text": "Second branch", "probability": 0.5}
    elif invalid_part in {"removed_confidence", "computed_belief"}:
        field = "confidence" if invalid_part == "removed_confidence" else "belief"
        patch["nodes"][0][field] = 0.9
    elif invalid_part in {"update_confidence", "update_belief"}:
        field = invalid_part.removeprefix("update_")
        patch["update_nodes"] = [{"id": "E0", "set": {field: 0.9}}]
    elif invalid_part == "missing_reasoning":
        del patch["edges"][0]["reasoning"]
    elif invalid_part == "blank_reasoning":
        patch["edges"][0]["reasoning"] = " \n\t"
    else:  # update_score
        patch["update_nodes"] = [{"id": "G1", "set": {"prior": None}}]
    return patch


INVALID_PARTS = {
    "missing_score": "belief source",
    "unanchored_derived": "belief source",
    "removed_probability": "schema",
    "removed_confidence": "confidence",
    "computed_belief": "belief",
    "update_confidence": "confidence",
    "update_belief": "belief",
    "missing_reasoning": "schema",
    "blank_reasoning": "schema",
    "update_score": "prior",
}


@pytest.mark.parametrize("command", ["seed", "expand"])
@pytest.mark.parametrize("invalid_part", sorted(INVALID_PARTS))
def test_invalid_patch_does_not_modify_state(tmp_path, command, invalid_part):
    state = starter_state("default")
    state["nodes"].append({"id": "E0", "type": "observation", "text": "Existing observation", "prior": 0.8})
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
@pytest.mark.parametrize("score,expected", [({}, 0.45), ({"prior": 0.9}, 0.405), ({"prior": 0.9, "posterior": 0.7}, 0.7)])
def test_scored_inference_and_inherited_candidate_apply_atomically(tmp_path, command, score, expected):
    state = starter_state("default")
    state["nodes"].append({"id": "A2", "type": "hypothesis", "text": "Existing premise", "prior": 0.5})
    state["frontier"] = [{"id": "Q1", "node": "G1"}]
    state_path = tmp_path / "state.json"
    patch_path = tmp_path / "patch.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    if command == "expand":
        assert run("next", str(state_path), "--pop").returncode == 0

    patch = valid_patch()
    patch["nodes"][1].update(score)
    # Grounding must use the merged graph, not just the nodes in this patch.
    patch["nodes"] = [node for node in patch["nodes"] if node["id"] != "A2"]
    patch["nodes"].append({"id": "CS1", "type": "candidate_solution", "text": "The answer is 42", "answer_kind": "exact_answer"})
    patch["edges"].extend([
        {"id": "D1-CS1", "from": "D1", "to": "CS1", "type": "leads_to", "reasoning": "The candidate restates the conclusion."},
        {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "This supplies the requested answer."},
    ])
    patch["edges"][0]["reasoning"] = "Dr. A. Smith checked U.S. and U.K. records, e.g. Fig. 2. " * 2
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    args = [command, str(state_path), "--patch", str(patch_path)]
    if command == "expand":
        args += ["--item", "Q1"]
    result = run(*args)
    assert result.returncode == 0, result.stderr
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert probability_from_cost(node_effective_truth_costs(updated)["CS1"]) == pytest.approx(expected)
    # Persisting a patch must not store computed belief or manufacture overrides.
    expected_nodes = {node["id"]: node for node in state["nodes"] + patch["nodes"]}
    assert {node["id"]: node for node in updated["nodes"]} == expected_nodes
