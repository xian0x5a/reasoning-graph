"""Goals an accepted goal `requires` count as accepted (issue #10)."""

import json
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def goal(node_id: str, text: str) -> dict:
    return {"id": node_id, "type": "goal", "text": text}


def hypothesis(node_id: str, text: str = "A claim") -> dict:
    return {"id": node_id, "type": "hypothesis", "text": text}


def requires(parent: str, child: str) -> dict:
    return {"from": parent, "to": child, "type": "requires"}


def answers(source: str, target: str, kind: str = "exact_answer") -> dict:
    return {"from": source, "to": target, "type": "answers", "answer_kind": kind}


def grounded(node_id: str) -> tuple[dict, dict]:
    """An observation that supports the hypothesis, so the grounding check passes."""
    observation = {"id": f"O{node_id}", "type": "observation", "text": "Seen in the log", "source": "log", "score": 5}
    return observation, {"from": observation["id"], "to": node_id, "type": "supports", "score": 5}


def write_state(tmp_path: Path, state: dict) -> Path:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


MANOR_GOALS = [goal("G1", "Find the URL path into the manor"), goal("G2", "Find the next URL path under /TwoSigns/")]
MANOR_POLICY = {"accepted_goals": ["G1"]}


def issue_10_state(**extra: object) -> dict:
    return {
        "summary": {"answer": ""},
        "goal_policy": MANOR_POLICY,
        "nodes": [*MANOR_GOALS, hypothesis("H1", "The next path is /TwoSigns/door")],
        "edges": [requires("G1", "G2"), answers("H1", "G2")],
    } | extra


def test_hypothesis_may_answer_a_goal_required_by_an_accepted_goal(tmp_path: Path) -> None:
    state_path = write_state(tmp_path, issue_10_state())

    refreshed = run_cli("refresh", str(state_path))
    audited = run_cli("audit", str(state_path))

    assert refreshed.returncode == 0, refreshed.stderr
    assert audited.returncode == 0, audited.stdout + audited.stderr
    assert audited.stdout.splitlines()[0].startswith("no answer claimed"), audited.stdout
    # G1 itself still has no answers edge.
    assert any("G1" in line for line in audited.stdout.splitlines() if "needs" in line), audited.stdout


def test_answer_naming_candidates_for_parent_and_required_goal_passes_audit(tmp_path: Path) -> None:
    obs1, support1 = grounded("H1")
    obs2, support2 = grounded("H2")
    state = {
        "summary": {"answer": "H1, H2"},
        "goal_policy": MANOR_POLICY,
        "nodes": [*MANOR_GOALS, obs1, obs2, hypothesis("H1", "The next path is /TwoSigns/door"), hypothesis("H2", "The manor path is /TwoSigns/door/hall")],
        "edges": [requires("G1", "G2"), support1, support2, answers("H1", "G2"), answers("H2", "G1")],
    }
    state_path = write_state(tmp_path, state)

    result = run_cli("audit", str(state_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[0] == "answer H1, H2: checks pass", result.stdout


def test_acceptance_reaches_goals_required_transitively(tmp_path: Path) -> None:
    state = issue_10_state(
        nodes=[*MANOR_GOALS, goal("G3", "Find the first URL path under /"), hypothesis("H1")],
        edges=[requires("G1", "G2"), requires("G2", "G3"), answers("H1", "G3")],
    )
    state_path = write_state(tmp_path, state)

    result = run_cli("refresh", str(state_path))

    assert result.returncode == 0, result.stderr


def test_answer_to_a_goal_outside_the_accepted_closure_is_rejected_naming_the_goal(tmp_path: Path) -> None:
    state = issue_10_state(
        nodes=[*MANOR_GOALS, goal("G9", "Find the gardener's name"), hypothesis("H1")],
        edges=[requires("G1", "G2"), answers("H1", "G9")],
    )
    state_path = write_state(tmp_path, state)

    result = run_cli("refresh", str(state_path))

    assert result.returncode == 1, result.stdout
    assert "H1" in result.stderr
    assert "G9" in result.stderr
    assert "accepted_goals" in result.stderr


def test_answer_kind_is_checked_against_a_required_sub_goal(tmp_path: Path) -> None:
    state = issue_10_state(
        nodes=[goal("G1", "Find the URL path into the manor"), goal("G2", "Recover the exact plaintext"), hypothesis("H1")],
        edges=[requires("G1", "G2"), answers("H1", "G2", "method_hypothesis")],
    )
    state_path = write_state(tmp_path, state)

    result = run_cli("refresh", str(state_path))

    assert result.returncode == 1, result.stdout
    assert "does not answer accepted goal" in result.stderr
    assert "G2" in result.stderr
