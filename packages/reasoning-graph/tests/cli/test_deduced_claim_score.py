"""A claim deduced from premises (`premise_of` edges) carries no score of its own."""

import json
import re
import subprocess
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
PERCENT = re.compile(r"\d\s*%|<1%")
DECIMAL = re.compile(r"\d\.\d")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def base_state() -> dict:
    """A valid graph: no node is deduced, H1 is a scored hypothesis."""
    return {
        "summary": {"answer": ""},
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Who did it?"},
            {"id": "K1", "type": "constraint", "text": "Only one culprit"},
            {"id": "T1", "type": "test", "text": "Check the log"},
            {"id": "O1", "type": "observation", "text": "The log shows the gardener"},
            {"id": "O2", "type": "observation", "text": "The gate was unlocked"},
            {"id": "H1", "type": "hypothesis", "text": "The gardener did it", "score": 4},
            {"id": "H2", "type": "hypothesis", "text": "The butler did it"},
        ],
        "edges": [],
    }


def write_state(tmp_path: Path, state: dict) -> Path:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


def record(state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
    patch_path = state_path.with_name("patch.json")
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    return run_cli("record", str(state_path), "--patch", str(patch_path))


def assert_actionable_error_without_belief(
    result: subprocess.CompletedProcess[str], node_id: str, *, must_fail: bool = True
) -> None:
    output = result.stdout + result.stderr
    if must_fail:
        assert result.returncode != 0, output
    assert node_id in output
    assert "unset" in output
    assert "supports" in output
    assert not PERCENT.search(output), output
    assert not DECIMAL.search(output), output


PREMISE_OF_H1 = {"from": "O1", "to": "H1", "type": "premise_of"}

REJECTED_PATCHES = {
    "premise_of into an existing scored hypothesis": ("H1", {"edges": [PREMISE_OF_H1]}),
    "scored candidate with a premise_of from a hypothesis": (
        "C1",
        {
            "nodes": [
                {"id": "C1", "type": "hypothesis", "text": "Gardener", "score": 3}
            ],
            "edges": [
                {"from": "H2", "to": "C1", "type": "premise_of"},
                {"from": "C1", "to": "G1", "type": "answers", "answer_kind": "exact_answer"},
            ],
        },
    ),
    "premise_of factor group into a scored hypothesis": (
        "H1",
        {
            "edges": [PREMISE_OF_H1, {"from": "O2", "to": "H1", "type": "premise_of"}],
            "factors": [{"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 4, "note": "one reading"}],
        },
    ),
}


@pytest.mark.parametrize("node_id, patch", REJECTED_PATCHES.values(), ids=REJECTED_PATCHES.keys())
def test_record_rejects_a_patch_that_leaves_a_deduced_node_scored(tmp_path: Path, node_id: str, patch: dict) -> None:
    state_path = write_state(tmp_path, base_state())
    before = state_path.read_text(encoding="utf-8")

    result = record(state_path, patch)

    assert_actionable_error_without_belief(result, node_id)
    assert state_path.read_text(encoding="utf-8") == before


def test_record_rejects_setting_a_score_on_an_already_deduced_hypothesis(tmp_path: Path) -> None:
    state = base_state()
    state["nodes"] = [{k: v for k, v in n.items() if k != "score"} for n in state["nodes"]]
    state["edges"] = [PREMISE_OF_H1]
    state_path = write_state(tmp_path, state)
    before = state_path.read_text(encoding="utf-8")

    result = record(state_path, {"update_nodes": [{"id": "H1", "set": {"score": 3}}]})

    assert_actionable_error_without_belief(result, "H1")
    assert state_path.read_text(encoding="utf-8") == before


def test_record_accepts_the_premise_of_when_the_same_patch_unsets_the_score(tmp_path: Path) -> None:
    state_path = write_state(tmp_path, base_state())

    result = record(state_path, {"edges": [PREMISE_OF_H1], "update_nodes": [{"id": "H1", "unset": ["score"]}]})

    assert result.returncode == 0, result.stdout + result.stderr
    h1 = next(n for n in json.loads(state_path.read_text(encoding="utf-8"))["nodes"] if n["id"] == "H1")
    assert "score" not in h1


def hand_edited_deduced_state() -> dict:
    state = base_state()
    state["edges"] = [PREMISE_OF_H1]  # H1 keeps its score: a hand edit that skipped record
    return state


def test_refresh_fails_on_a_hand_edited_deduced_scored_node(tmp_path: Path) -> None:
    state_path = write_state(tmp_path, hand_edited_deduced_state())

    assert_actionable_error_without_belief(run_cli("refresh", str(state_path)), "H1")


def test_audit_reports_a_hand_edited_deduced_scored_node(tmp_path: Path) -> None:
    state_path = write_state(tmp_path, hand_edited_deduced_state())

    # audit is read-only and may exit 0 while listing problems, so check its report, not its exit code.
    assert_actionable_error_without_belief(run_cli("audit", str(state_path)), "H1", must_fail=False)


def accepted_states() -> dict[str, dict]:
    scored_test_result = base_state()
    scored_test_result["nodes"][3]["score"] = 4
    scored_test_result["edges"] = [{"from": "T1", "to": "O1", "type": "yields"}]

    evidence_edges = base_state()
    evidence_edges["edges"] = [
        {"from": "O1", "to": "H1", "type": "supports"},
        {"from": "O2", "to": "H1", "type": "contradicts"},
    ]

    scored_group_on_unscored_target = base_state()
    del scored_group_on_unscored_target["nodes"][5]["score"]
    scored_group_on_unscored_target["edges"] = [
        {"from": "O1", "to": "H1", "type": "premise_of"},
        {"from": "O2", "to": "H1", "type": "premise_of"},
    ]
    scored_group_on_unscored_target["factors"] = [
        {"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 4, "note": "one reading"}
    ]

    return {
        "scored observation that is a test result": scored_test_result,
        "supports and contradicts into a scored hypothesis": evidence_edges,
        "scored premise_of group on an unscored target": scored_group_on_unscored_target,
    }


ACCEPTED_STATES = accepted_states()


@pytest.mark.parametrize("state", ACCEPTED_STATES.values(), ids=ACCEPTED_STATES.keys())
def test_refresh_accepts_scores_that_are_not_on_a_deduced_claim(tmp_path: Path, state: dict) -> None:
    state_path = write_state(tmp_path, state)

    result = run_cli("refresh", str(state_path))

    assert result.returncode == 0, result.stdout + result.stderr
