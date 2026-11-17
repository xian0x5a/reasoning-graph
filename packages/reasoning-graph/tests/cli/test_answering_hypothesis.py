"""A candidate answer is a hypothesis with an `answers` edge to a goal (ADR 0019).
`candidate_solution` is gone; `answer_kind` lives on the edge."""

import json
import re
import subprocess
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        input=stdin,
    )


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def answers(source: str, target: str = "G1", kind: str = "exact_answer") -> dict:
    return {"from": source, "to": target, "type": "answers", "answer_kind": kind}


def observation(node_id: str = "O1") -> dict:
    return {"id": node_id, "type": "observation", "text": "The log names the culprit", "source": "log", "score": 5}


def hypothesis(node_id: str, text: str = "The gardener did it") -> dict:
    return {"id": node_id, "type": "hypothesis", "text": text}


def supports(source: str, target: str) -> dict:
    return {"from": source, "to": target, "type": "supports", "score": 5}


def new_state(tmp_path: Path, name: str = "state.json") -> Path:
    state_path = tmp_path / name
    assert run_cli("init", "--goal", "Who did it?", "-o", str(state_path)).returncode == 0
    return state_path


def record(state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
    return run_cli("record", str(state_path), "--patch", "-", stdin=json.dumps(patch))


def recorded(tmp_path: Path, patch: dict) -> Path:
    state_path = new_state(tmp_path)
    result = record(state_path, patch)
    assert result.returncode == 0, output(result)
    return state_path


def claim_answer(state_path: Path, answer: str) -> None:
    # Edit the file directly so the audit, not `record`, is what judges the claim.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("summary", {})["answer"] = answer
    state_path.write_text(json.dumps(state), encoding="utf-8")


def audit_status(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout.splitlines()[0]


GROUNDED_CANDIDATE = {
    "nodes": [observation(), hypothesis("H1")],
    "edges": [supports("O1", "H1"), answers("H1")],
}


def test_hypothesis_with_answers_edge_is_accepted_and_named_by_id(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, GROUNDED_CANDIDATE | {"answer": "H1"})

    audit = run_cli("audit", str(state_path))

    assert audit.returncode == 0, output(audit)
    assert audit_status(audit) == "answer H1: checks pass"


REJECTED_PATCHES = {
    "candidate_solution node": (
        {"nodes": [{"id": "CS1", "type": "candidate_solution", "text": "The gardener did it"}], "edges": []},
        ["candidate_solution", "hypothesis", "answers"],
    ),
    "answer_kind on a node": (
        {"nodes": [hypothesis("H1") | {"answer_kind": "exact_answer"}], "edges": []},
        ["answer_kind belongs on the answers edge"],
    ),
    "answers edge without answer_kind": (
        {"nodes": [hypothesis("H1")], "edges": [{"from": "H1", "to": "G1", "type": "answers"}]},
        ["answer_kind"],
    ),
    "answer_kind on a non-answers edge": (
        {"nodes": [observation(), hypothesis("H1")], "edges": [supports("O1", "H1") | {"answer_kind": "exact_answer"}]},
        ["answer_kind", "answers"],
    ),
    "answers edge from an observation": (
        {"nodes": [observation()], "edges": [answers("O1")]},
        ["answers", "hypothesis"],
    ),
    "supports edge from a hypothesis to a goal": (
        {"nodes": [hypothesis("H1")], "edges": [{"from": "H1", "to": "G1", "type": "supports"}]},
        ["answers"],
    ),
    "answer_kind the goal does not accept": (
        {"nodes": [hypothesis("H1")], "edges": [answers("H1", kind="method_hypothesis")]},
        ["method_hypothesis"],
    ),
}


@pytest.mark.parametrize("patch, expected", REJECTED_PATCHES.values(), ids=REJECTED_PATCHES.keys())
def test_record_rejects_invalid_answering_input_and_names_the_fix(tmp_path: Path, patch: dict, expected: list[str]) -> None:
    result = record(new_state(tmp_path), patch)

    assert result.returncode != 0, result.stdout
    for fragment in expected:
        assert fragment in result.stderr, result.stderr


def test_one_hypothesis_answers_two_goals_with_a_kind_per_edge(tmp_path: Path) -> None:
    patch = {
        "nodes": [{"id": "G2", "type": "goal", "text": "How was it done?"}, hypothesis("H1")],
        "edges": [{"from": "G1", "to": "G2", "type": "requires"}, answers("H1", "G1", "exact_answer"), answers("H1", "G2", "exact_method")],
    }

    state_path = recorded(tmp_path, patch)

    kinds = {(e["to"], e["answer_kind"]) for e in json.loads(state_path.read_text(encoding="utf-8"))["edges"] if e["type"] == "answers"}
    assert kinds == {("G1", "exact_answer"), ("G2", "exact_method")}


def test_hypothesis_becomes_a_candidate_when_a_later_patch_adds_answers(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, {"nodes": [observation(), hypothesis("H1")], "edges": [supports("O1", "H1")]})
    before = json.loads(state_path.read_text(encoding="utf-8"))
    assert audit_status(run_cli("audit", str(state_path))) == "no answer claimed"

    result = record(state_path, {"edges": [answers("H1")], "answer": "H1"})

    assert result.returncode == 0, output(result)
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert [n for n in after["nodes"] if n["id"] == "H1"] == [n for n in before["nodes"] if n["id"] == "H1"]
    assert supports("O1", "H1") in after["edges"]
    assert audit_status(run_cli("audit", str(state_path))) == "answer H1: checks pass"


NAMING_CASES = {
    "text only": ("The gardener did it", "H1", "The gardener did it"),
    "partial text is not the claim": ("Thornton", "H1", "Sergeant Josiah Thornton killed Bryan"),
    "H1 is not H12": ("H1", "H12", "The gardener did it"),
}


@pytest.mark.parametrize("answer, candidate_id, candidate_text", NAMING_CASES.values(), ids=NAMING_CASES.keys())
def test_answer_must_name_a_candidate_by_whole_id(tmp_path: Path, answer: str, candidate_id: str, candidate_text: str) -> None:
    patch = {"nodes": [observation(), hypothesis(candidate_id, candidate_text)], "edges": [supports("O1", candidate_id), answers(candidate_id)]}
    state_path = recorded(tmp_path, patch)
    claim_answer(state_path, answer)

    audit = run_cli("audit", str(state_path))

    assert audit.returncode == 1, audit.stdout
    assert "checks pass" not in audit.stdout
    assert "name one by id" in audit.stderr, audit.stderr


def test_claimed_answer_fails_when_no_hypothesis_answers_the_goal(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, {"nodes": [observation(), hypothesis("H1")], "edges": [supports("O1", "H1")]})
    claim_answer(state_path, "H1")

    audit = run_cli("audit", str(state_path))

    assert audit.returncode == 1, audit.stdout
    assert "G1" in audit.stderr
    assert "unanswered" in audit.stderr


def test_index_and_page_treat_only_an_answering_hypothesis_as_a_candidate(tmp_path: Path) -> None:
    patch = {
        "nodes": [observation(), hypothesis("H1"), hypothesis("H2", "The butler did it"), hypothesis("H3", "The cook was away")],
        "edges": [supports("O1", "H1"), answers("H1"), answers("H2", kind="exact_method"), {"from": "H3", "to": "H1", "type": "supports"}],
    }
    state_path = recorded(tmp_path, patch)

    index = state_path.with_suffix(".index.md").read_text(encoding="utf-8")
    answers_lines = [line for line in index.splitlines() if "-answers" in line]
    assert any(line.startswith("- H1 ") and "exact_answer" in line for line in answers_lines), index
    assert any(line.startswith("- H2 ") and "exact_method" in line for line in answers_lines), index
    assert "candidate_solution" not in index

    page = state_path.with_suffix(".html").read_text(encoding="utf-8")
    dropdown = re.search(r"<select data-candidate-focus-select.*?</select>", page, re.S)
    assert dropdown, "page has no candidate focus dropdown"
    options = dropdown.group(0)
    assert "H1" in options and "H2" in options
    assert "H3" not in options


def edit_state(state_path: Path, change) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    change(state)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def answers_edge(state_path: Path, source: str = "H1", target: str = "G1") -> dict:
    edges = json.loads(state_path.read_text(encoding="utf-8"))["edges"]
    return next(e for e in edges if e["type"] == "answers" and e["from"] == source and e["to"] == target)


UPDATE_ANSWERS_EDGE_REJECTED = {
    "unset answer_kind": ({"id": "H1-G1", "unset": ["answer_kind"]}, ["answer_kind"]),
    "retype to supports": ({"id": "H1-G1", "set": {"type": "supports"}}, ["answers", "only edge"]),
}


@pytest.mark.parametrize("update, expected", UPDATE_ANSWERS_EDGE_REJECTED.values(), ids=UPDATE_ANSWERS_EDGE_REJECTED.keys())
def test_update_edges_cannot_leave_an_answers_edge_invalid(tmp_path: Path, update: dict, expected: list[str]) -> None:
    state_path = recorded(tmp_path, GROUNDED_CANDIDATE)

    result = record(state_path, {"update_edges": [update]})

    assert result.returncode != 0, result.stdout
    for fragment in expected:
        assert fragment in result.stderr, result.stderr


def test_update_edges_can_change_answer_kind_to_another_valid_kind(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, GROUNDED_CANDIDATE)

    result = record(state_path, {"update_edges": [{"id": "H1-G1", "set": {"answer_kind": "exact_method"}}]})

    assert result.returncode == 0, output(result)
    assert answers_edge(state_path)["answer_kind"] == "exact_method"


def test_removing_the_answers_edge_of_the_claimed_answer_fails_audit_and_drops_the_candidate(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, GROUNDED_CANDIDATE | {"answer": "H1"})
    assert audit_status(run_cli("audit", str(state_path))) == "answer H1: checks pass"

    result = record(state_path, {"remove_edges": ["H1-G1"]})
    audit = run_cli("audit", str(state_path))

    assert audit.returncode == 1, output(result) + audit.stdout
    assert "no answers edge" in audit.stderr, audit.stderr
    page = state_path.with_suffix(".html").read_text(encoding="utf-8")
    dropdown = re.search(r"<select data-candidate-focus-select.*?</select>", page, re.S)
    assert dropdown is None or "H1" not in dropdown.group(0)


def test_naming_a_hypothesis_without_an_answers_edge_says_to_add_the_edge(tmp_path: Path) -> None:
    patch = {
        "nodes": [observation(), hypothesis("H1"), hypothesis("H2", "The butler did it")],
        "edges": [supports("O1", "H1"), answers("H2")],
    }
    state_path = recorded(tmp_path, patch)
    claim_answer(state_path, "H1")

    audit = run_cli("audit", str(state_path))

    assert audit.returncode == 1, audit.stdout
    assert "has no answers edge" in audit.stderr, audit.stderr
    assert "name one by id" not in audit.stderr, audit.stderr


def test_page_and_mermaid_give_an_answering_hypothesis_the_candidate_role(tmp_path: Path) -> None:
    patch = {
        "nodes": [observation(), hypothesis("H1"), hypothesis("H2", "The butler did it")],
        "edges": [supports("O1", "H1"), answers("H1")],
    }
    state_path = recorded(tmp_path, patch)

    page = state_path.with_suffix(".html").read_text(encoding="utf-8")
    card = lambda node_id: re.search(rf'<article class="detail-card[^"]*" data-node-type="([^"]+)" id="[^"]*{node_id}"', page)
    assert card("H1") and card("H1").group(1) == "candidate", "H1 detail card is not a candidate"
    assert card("H2") and card("H2").group(1) == "hypothesis", "H2 detail card is not a hypothesis"

    mermaid = run_cli("mermaid", str(state_path))
    assert mermaid.returncode == 0, output(mermaid)
    assert "class H1 candidate;" in mermaid.stdout
    assert "class H2 hypothesis;" in mermaid.stdout
    assert "class H2 candidate;" not in mermaid.stdout


BLOCKER_GOAL = {"id": "G2", "type": "goal", "text": "Identify blocker proving no valid solution exists"}


def two_goal_patch(kind_for_g1: str, kind_for_g2: str) -> dict:
    return {"nodes": [BLOCKER_GOAL, hypothesis("H1")], "edges": [answers("H1", "G1", kind_for_g1), answers("H1", "G2", kind_for_g2)]}


def test_answer_kind_is_checked_against_each_edges_own_goal(tmp_path: Path) -> None:
    accepted = record(new_state(tmp_path, "matching.json"), two_goal_patch("exact_answer", "blocker"))
    swapped = record(new_state(tmp_path, "swapped.json"), two_goal_patch("blocker", "exact_answer"))

    assert accepted.returncode == 0, output(accepted)
    assert swapped.returncode != 0, swapped.stdout
    assert "H1-G1" in swapped.stderr, swapped.stderr


def test_hypothesis_answering_only_an_unaccepted_goal_is_rejected(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, {"nodes": [{"id": "G2", "type": "goal", "text": "How was it done?"}, hypothesis("H1")], "edges": [answers("H1", "G2", "exact_method")]})
    edit_state(state_path, lambda state: state.update(goal_policy={"accepted_goals": ["G1"]}))

    refreshed = run_cli("refresh", str(state_path))

    assert refreshed.returncode != 0, refreshed.stdout
    assert "goal_policy.accepted_goals" in refreshed.stderr, refreshed.stderr


def test_candidate_with_only_a_supports_edge_is_listed_open_in_the_index(tmp_path: Path) -> None:
    state_path = recorded(tmp_path, GROUNDED_CANDIDATE)

    index = state_path.with_suffix(".index.md").read_text(encoding="utf-8")

    open_section = index.split("## Open", 1)[1].split("\n## ", 1)[0]
    assert "- H1 hypothesis" in open_section, index


def state_with_removed_candidate_type(tmp_path: Path) -> Path:
    state_path = new_state(tmp_path)
    edit_state(state_path, lambda state: state["nodes"].append({"id": "CS1", "type": "candidate_solution", "text": "The gardener did it"}))
    return state_path


def test_mermaid_names_the_replacement_for_a_removed_candidate_type(tmp_path: Path) -> None:
    result = run_cli("mermaid", str(state_with_removed_candidate_type(tmp_path)))

    assert result.returncode != 0, result.stdout
    assert "candidate_solution" in result.stderr and "answers" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr


MALFORMED_RECORDS = {
    "list as answer_kind": (
        {"nodes": [hypothesis("H1")], "edges": [{"from": "H1", "to": "G1", "type": "answers", "answer_kind": ["exact_answer"]}]},
        ["answer_kind"],
        ["Traceback", "unhashable"],
    ),
    "removed type with answers and premise_of edges": (
        {
            "nodes": [observation(), {"id": "CS1", "type": "candidate_solution", "text": "The gardener did it"}],
            "edges": [{"from": "O1", "to": "CS1", "type": "premise_of"}, answers("CS1")],
        },
        ["candidate_solution"],
        ["answers must connect hypothesis -> goal"],
    ),
}


@pytest.mark.parametrize("patch, expected, absent", MALFORMED_RECORDS.values(), ids=MALFORMED_RECORDS.keys())
def test_record_reports_malformed_input_cleanly(tmp_path: Path, patch: dict, expected: list[str], absent: list[str]) -> None:
    result = record(new_state(tmp_path), patch)

    assert result.returncode != 0, result.stdout
    for fragment in expected:
        assert fragment in result.stderr, result.stderr
    for fragment in absent:
        assert fragment not in result.stderr, result.stderr


def test_unresolved_outcome_warning_follows_the_answers_edge(tmp_path: Path) -> None:
    text = "Not solved: the key is missing"
    with_edge = record(new_state(tmp_path, "with_edge.json"), {"nodes": [hypothesis("H1", text)], "edges": [answers("H1")]})
    without_edge = record(new_state(tmp_path, "without_edge.json"), {"nodes": [hypothesis("H1", text)], "edges": []})

    assert with_edge.returncode == 0 and without_edge.returncode == 0, output(with_edge) + output(without_edge)
    assert "unresolved outcome" in output(with_edge)
    assert "unresolved outcome" not in output(without_edge)
