"""Endpoints of `premise_of` and `yields`, and the removal of `leads_to` (ADR 0017)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost  # noqa: E402

NODES = [
    {"id": "G1", "type": "goal", "text": "Who did it?"},
    {"id": "K1", "type": "constraint", "text": "Only one culprit"},
    {"id": "T1", "type": "test", "text": "Check the log"},
    {"id": "T2", "type": "test", "text": "Check the gate"},
    {"id": "O1", "type": "observation", "text": "The log shows the gardener"},
    {"id": "O2", "type": "observation", "text": "The gate was unlocked"},
    {"id": "H1", "type": "hypothesis", "text": "The gardener did it"},
    {"id": "H2", "type": "hypothesis", "text": "The butler did it"},
    {"id": "C1", "type": "hypothesis", "text": "Gardener"},
    {"id": "C2", "type": "hypothesis", "text": "Butler"},
]
# Every candidate answers the goal, so the only findings are about the edge under test.
ANSWERS = [{"from": "C1", "to": "G1", "type": "answers", "answer_kind": "exact_answer"}, {"from": "C2", "to": "G1", "type": "answers", "answer_kind": "exact_answer"}]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def edge(source: str, target: str, edge_type: str) -> dict:
    return {"from": source, "to": target, "type": edge_type}


def write_state(tmp_path: Path, edges: list[dict] | None = None, **node_overrides: dict) -> Path:
    nodes = [{**node, **node_overrides.get(node["id"], {})} for node in NODES]
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"summary": {"answer": ""}, "nodes": nodes, "edges": ANSWERS + (edges or [])}), encoding="utf-8")
    return state_path


def record(state_path: Path, edges: list[dict]) -> subprocess.CompletedProcess[str]:
    patch_path = state_path.with_name("patch.json")
    patch_path.write_text(json.dumps({"edges": edges}), encoding="utf-8")
    return run_cli("record", str(state_path), "--patch", str(patch_path))


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_leads_to_is_rejected_everywhere_and_names_both_replacements(tmp_path):
    patch_result = record(write_state(tmp_path), [edge("T1", "O1", "leads_to")])
    hand_edited = write_state(tmp_path, [edge("T1", "O1", "leads_to")])
    # mermaid renders without validating, so it must fail on its own rather than drop the edge.
    results = [patch_result, *(run_cli(command, str(hand_edited)) for command in ("refresh", "audit", "mermaid"))]
    for result in results:
        assert result.returncode != 0, output(result)
        assert "leads_to" in output(result)
        assert "premise_of" in output(result)
        assert "yields" in output(result)


@pytest.mark.parametrize("target", ["H2", "C2"])
@pytest.mark.parametrize("source", ["O1", "H1", "C1"])
def test_premise_of_accepts_observation_or_claim_into_a_claim(tmp_path, source, target):
    result = record(write_state(tmp_path), [edge(source, target, "premise_of")])
    assert result.returncode == 0, output(result)


PREMISE_OF_REJECTIONS = [
    # (source, target, edge named in the hint, or None when the contract names none)
    ("T1", "H1", "yields"),
    ("T1", "C1", "yields"),
    ("T1", "T2", "yields"),
    ("T1", "O1", "yields"),
    ("O1", "T1", "prompts"),
    ("H1", "T1", "prompts"),
    ("C1", "T1", "prompts"),
    ("O1", "O2", "hypothesis"),
    ("H1", "O2", "hypothesis"),
    ("C1", "O2", "hypothesis"),
    ("G1", "H1", None),
    ("K1", "H1", None),
    ("G1", "C1", None),
    ("K1", "C1", None),
]


@pytest.mark.parametrize("source,target,hint", PREMISE_OF_REJECTIONS)
def test_premise_of_rejects_other_endpoints_and_names_the_edge_meant(tmp_path, source, target, hint):
    result = record(write_state(tmp_path), [edge(source, target, "premise_of")])
    assert result.returncode != 0, output(result)
    assert "premise_of" in output(result)
    if hint:
        assert hint in output(result).split("premise_of must connect", 1)[1]


def test_yields_accepts_a_test_into_the_observation_of_its_result(tmp_path):
    result = record(write_state(tmp_path), [edge("T1", "O1", "yields")])
    assert result.returncode == 0, output(result)


@pytest.mark.parametrize("source,target", [("T1", "H1"), ("T1", "C1"), ("O1", "O2"), ("H1", "O1")])
def test_yields_rejects_anything_but_test_to_observation(tmp_path, source, target):
    result = record(write_state(tmp_path), [edge(source, target, "yields")])
    assert result.returncode != 0, output(result)
    assert "yields" in output(result)


def test_yields_from_a_not_run_test_is_rejected(tmp_path):
    state_path = write_state(tmp_path, T1={"not_run": "log was rotated away"})
    result = record(state_path, [edge("T1", "O1", "yields")])
    assert result.returncode != 0, output(result)
    assert "not_run" in output(result)


def test_yields_moves_no_belief_of_the_result_observation():
    def belief(edges: list[dict], score: int | None) -> float:
        observation = {"id": "O1", "type": "observation", "text": "Result", **({"score": score} if score else {})}
        state = {"nodes": [{"id": "T1", "type": "test", "text": "Run"}, observation], "edges": edges}
        return probability_from_cost(node_effective_truth_costs(state)["O1"])

    for score, expected in [(None, 0.9), (2, 0.3)]:
        assert belief([], score) == pytest.approx(expected)
        assert belief([edge("T1", "O1", "yields")], score) == pytest.approx(expected)


def test_audit_counts_a_yields_result_as_a_recorded_result(tmp_path):
    missing = "without a recorded result observation"
    without_result = run_cli("audit", str(write_state(tmp_path)))
    assert missing in output(without_result)

    with_result = run_cli("audit", str(write_state(tmp_path, [edge("T1", "O1", "yields"), edge("T2", "O2", "yields")])))
    assert missing not in output(with_result)
