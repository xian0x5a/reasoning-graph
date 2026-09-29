"""Record rejects score and anchoring violations without touching state."""

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
            {"id": "A2", "type": "hypothesis", "text": "Second branch", "score": 3},
            {"id": "D1", "type": "hypothesis", "text": "Conclusion"},
            {"id": "E2", "type": "observation", "text": "Reading", "score": 5},
        ],
        "edges": [
            {"id": "A2-D1", "from": "A2", "to": "D1", "type": "leads_to"},
            {"id": "E2-D1", "from": "E2", "to": "D1", "type": "leads_to"},
        ],
        "reason": "Derive the conclusion",
    }


def patch_for(invalid_part: str) -> dict:
    patch = valid_patch()
    if invalid_part.startswith("removed_") and invalid_part != "removed_edge_reasoning":
        patch["nodes"][0][invalid_part.removeprefix("removed_")] = 0.9
    elif invalid_part == "computed_belief":
        patch["nodes"][0]["belief"] = 0.9
    elif invalid_part.startswith("update_"):
        patch["update_nodes"] = [{"id": "E0", "set": {invalid_part.removeprefix("update_"): 0.9}}]
    elif invalid_part == "removed-edge-likelihood_ratio":
        patch["edges"].append({"id": "E2-A2", "from": "E2", "to": "A2", "type": "supports", "likelihood_ratio": 2})
    elif invalid_part == "score_off_the_scale":
        patch["nodes"][0]["score"] = 6
    elif invalid_part == "score_on_a_premise_edge":
        patch["edges"][0]["score"] = 3
    elif invalid_part == "score_on_a_goal":
        patch["update_nodes"] = [{"id": "G1", "set": {"score": 3}}]
    else:  # removed_edge_reasoning
        patch["edges"][0]["reasoning"] = "The conclusion rests on this premise."
    return patch


INVALID_PARTS = {
    "removed_prior": "prior was removed; use score",
    "removed_probability": "probability was removed; use score",
    "removed_confidence": "confidence was removed; use score",
    "removed_posterior": "posterior was removed; use score",
    "removed-edge-likelihood_ratio": "likelihood_ratio was removed; use score",
    "computed_belief": "belief",
    "update_prior": "prior was removed; use score",
    "update_posterior": "posterior was removed; use score",
    "update_belief": "belief",
    "score_off_the_scale": "score must be an integer from 1 to 5",
    "score_on_a_premise_edge": "score is only valid on supports/contradicts edges",
    "score_on_a_goal": "score is only valid on observation, hypothesis, and candidate_solution nodes",
    "removed_edge_reasoning": "reasoning was removed; use the optional note",
}


@pytest.mark.parametrize("invalid_part", sorted(INVALID_PARTS))
def test_invalid_patch_does_not_modify_state(tmp_path, invalid_part):
    state = starter_state("default")
    state["nodes"].append({"id": "E0", "type": "observation", "text": "Existing observation", "score": 4})
    state_path = tmp_path / "state.json"
    patch_path = tmp_path / "patch.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    original = state_path.read_bytes()

    patch_path.write_text(json.dumps(patch_for(invalid_part)), encoding="utf-8")
    result = run("record", str(state_path), "--patch", str(patch_path))
    assert result.returncode != 0
    assert INVALID_PARTS[invalid_part] in result.stderr
    assert state_path.read_bytes() == original


@pytest.mark.parametrize("score,expected", [({}, 0.45), ({"score": 5}, 0.405)])
def test_scored_inference_and_inherited_candidate_apply_atomically(tmp_path, score, expected):
    state = starter_state("default")
    state["nodes"].append({"id": "A2", "type": "hypothesis", "text": "Existing premise", "score": 3})
    state_path = tmp_path / "state.json"
    patch_path = tmp_path / "patch.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")


    patch = valid_patch()
    patch["nodes"][1].update(score)
    # Grounding must use the merged graph, not just the nodes in this patch.
    patch["nodes"] = [node for node in patch["nodes"] if node["id"] != "A2"]
    patch["nodes"].append({"id": "CS1", "type": "candidate_solution", "text": "The answer is 42", "answer_kind": "exact_answer"})
    patch["edges"].extend([
        {"id": "D1-CS1", "from": "D1", "to": "CS1", "type": "leads_to"},
        {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers"},
    ])
    patch["edges"][0]["note"] = "Dr. A. Smith checked U.S. and U.K. records, e.g. Fig. 2."
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    result = run("record", str(state_path), "--patch", str(patch_path))
    assert result.returncode == 0, result.stderr
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert probability_from_cost(node_effective_truth_costs(updated)["CS1"]) == pytest.approx(expected)
    stored_nodes = {node["id"]: node for node in updated["nodes"]}
    assert stored_nodes["CS1"]["belief"] == pytest.approx(expected)
    # Persisting a patch stores computed belief but must not manufacture overrides.
    expected_nodes = {node["id"]: node for node in state["nodes"] + patch["nodes"]}
    assert {node_id: {k: v for k, v in node.items() if k != "belief"} for node_id, node in stored_nodes.items()} == expected_nodes
