"""A correlation group is a list of edge ids plus one combined score, so correlated clues count once."""

import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost
from reasoning_graph.schema_validation import patch_schema_errors, state_schema_errors
from reasoning_graph.validation import validate_state


def edge(source, target, relation, **extra):
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": relation, **extra}


def grouped_state(relation="supports", **group):
    """Two observations bear on H1 through the same relation; F1 groups their edges."""
    return {
        "nodes": [
            {"id": "O1", "type": "observation", "text": "First log line"},
            {"id": "O2", "type": "observation", "text": "Second log line of the same request"},
            {"id": "O3", "type": "observation", "text": "Unrelated reading"},
            {"id": "H1", "type": "hypothesis", "text": "Target"},
            {"id": "H2", "type": "hypothesis", "text": "Other target"},
        ],
        "edges": [edge("O1", "H1", relation), edge("O2", "H1", relation)],
        "factors": [{"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 3, **group}],
    }


def belief(state, node_id="H1"):
    return probability_from_cost(node_effective_truth_costs(state)[node_id])


def errors_of(state):
    return validate_state(state).errors


@pytest.mark.parametrize("relation,score,expected", [
    ("supports", 3, 2 / 3),       # One ratio 2, not two: odds 1 -> 2.
    ("supports", 5, 5 / 6),
    ("contradicts", 3, 1 / 3),    # The reciprocal, once.
    ("contradicts", 4, 1 / 4),
    ("leads_to", 4, 0.7),         # Joint probability of the premises, not 0.9 * 0.9.
    ("leads_to", 2, 0.3),
])
def test_group_counts_its_edges_once_at_the_combined_score(relation, score, expected):
    state = grouped_state(relation, score=score)
    assert validate_state(state).ok, errors_of(state)
    assert belief(state) == pytest.approx(expected)

    del state["factors"]
    independent = {"supports": 0.8, "contradicts": 0.2, "leads_to": 0.81}[relation]
    assert belief(state) == pytest.approx(independent)


def test_ungrouped_edge_still_counts_beside_a_group():
    state = grouped_state("supports")
    state["edges"].append(edge("O3", "H1", "supports", score=4))
    assert validate_state(state).ok, errors_of(state)
    # Group ratio 2 and independent ratio 3 give odds 6.
    assert belief(state) == pytest.approx(6 / 7)


def test_group_takes_an_optional_note():
    state = grouped_state(note="Both lines come from one failed request.")
    assert not state_schema_errors(state)
    assert not patch_schema_errors({"factors": state["factors"]})
    assert validate_state(state).ok, errors_of(state)


def invalid_groups():
    def too_few(state):
        state["factors"][0]["edges"] = ["O1-H1"]

    def repeated_edge(state):
        state["factors"][0]["edges"] = ["O1-H1", "O1-H1"]

    def missing_edge(state):
        state["factors"][0]["edges"] = ["O1-H1", "O9-H1"]

    def mixed_relations(state):
        state["edges"][1]["type"] = "contradicts"

    def different_targets(state):
        state["edges"][1] = {**edge("O2", "H2", "supports"), "id": "O2-H1"}

    def ungroupable_relation(state):
        for item in state["edges"]:
            item["type"] = "prompts"

    def edge_in_two_groups(state):
        state["edges"].append(edge("O3", "H1", "supports"))
        state["factors"].append({"id": "F2", "edges": ["O2-H1", "O3-H1"], "score": 2})

    def grouped_edge_with_its_own_score(state):
        state["edges"][0]["score"] = 4

    def missing_score(state):
        del state["factors"][0]["score"]

    def score_off_the_scale(state):
        state["factors"][0]["score"] = 6

    return {
        "too few edges": (too_few, "at least two"),
        "repeated edge": (repeated_edge, "at least two"),
        "missing edge": (missing_edge, "references missing edge 'O9-H1'"),
        "mixed relations": (mixed_relations, "must share one type"),
        "different targets": (different_targets, "must share one target"),
        "ungroupable relation": (ungroupable_relation, "leads_to, supports, or contradicts"),
        "edge in two groups": (edge_in_two_groups, "edge O2-H1 is already grouped by F1"),
        "grouped edge with its own score": (grouped_edge_with_its_own_score, "edge O1-H1 is grouped by F1 and must not carry its own score"),
        "missing score": (missing_score, "score"),
        "score off the scale": (score_off_the_scale, "score must be an integer from 1 to 5"),
    }


@pytest.mark.parametrize("label", sorted(invalid_groups()))
def test_invalid_group_is_rejected(label):
    edit, expected = invalid_groups()[label]
    state = grouped_state()
    edit(state)
    errors = errors_of(state)
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize("field,value,replacement", [
    ("relation", "supports", "edges"),
    ("target", "H1", "edges"),
    ("inputs", ["O1", "O2"], "edges"),
    ("aggregation", {"kind": "likelihood", "if_target_true": 0.6, "if_target_false": 0.2}, "score"),
    ("reason", "One request.", "note"),
])
def test_removed_group_fields_are_rejected_and_name_the_replacement(field, value, replacement):
    state = grouped_state()
    state["factors"][0][field] = value
    assert state_schema_errors(state)
    assert patch_schema_errors({"factors": state["factors"]})
    errors = errors_of(state)
    assert any(f"{field} was removed" in error and replacement in error for error in errors), errors
