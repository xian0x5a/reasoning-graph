"""Graph labels show effective belief without turning computed values into inputs."""

from copy import deepcopy
import html
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.render import html_document, node_detail_cards, to_mermaid
from reasoning_graph.validation import validate_state


RENDERERS = ("mermaid", "grouped-mermaid", "offline")


def report_state(*, support=False, posterior=None):
    state = {
        "nodes": [
            {"id": "E1", "type": "observation", "text": "Observed premise", "prior": 0.8},
            {"id": "E2", "type": "observation", "text": "Independent signal", "prior": 0.9},
            {"id": "D1", "type": "hypothesis", "text": "Conclusion", "prior": 0.9},
            {"id": "CS1", "type": "candidate_solution", "text": "The answer is 42", "answer_kind": "exact_answer"},
            {"id": "G1", "type": "goal", "text": "Find the answer"},
            {"id": "C1", "type": "constraint", "text": "Use the observed data"},
            {"id": "T1", "type": "test", "text": "Check the premise"},
        ],
        "edges": [
            {"id": "E1-D1", "from": "E1", "to": "D1", "type": "leads_to", "reasoning": "This observation is required for the conclusion."},
            {"id": "D1-CS1", "from": "D1", "to": "CS1", "type": "leads_to", "reasoning": "The candidate restates the conclusion."},
            {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "This supplies the requested answer."},
        ],
        "frontier": [],
        "report": {"candidates": [{"id": "CS1", "name": "Answer", "belief": 0.123}]},
        "presentation": {"include_nodes": ["D1", "CS1", "G1"]},
    }
    if support:
        state["edges"].append({
            "id": "E2-D1", "from": "E2", "to": "D1", "type": "supports", "likelihood_ratio": 2,
            "reasoning": "The signal is twice as likely when the conclusion is true.",
        })
    if posterior is not None:
        state["nodes"][2]["posterior"] = posterior
    assert validate_state(state).ok
    return state


def graph_labels(state, renderer, include_nodes=None):
    if renderer == "offline":
        svg = ET.fromstring(offline_graph_svg(state, include_nodes))
        ns = {"svg": "http://www.w3.org/2000/svg"}
        return {
            node.attrib["data-node-id"]: "\n".join(
                line.text or "" for line in node.findall(".//svg:tspan", ns)
            )
            for node in svg.findall(".//svg:g[@class='node']", ns)
        }
    source = to_mermaid(state, include_nodes, group_by_type=renderer == "grouped-mermaid")
    return {
        node_id: html.unescape(label.replace("<br/>", "\n"))
        for node_id, label in re.findall(r'^\s+(\w+)\["(.*?)"\]', source, re.MULTILINE)
    }


def detail_card(document, node_id):
    match = re.search(rf'<article\b[^>]*id="details-{node_id}">(.*?)</article>', document, re.DOTALL)
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("filtered", [False, True])
@pytest.mark.parametrize("support,posterior,expected", [
    (False, None, "0.72"),
    (True, None, "0.837"),  # 0.72 base and LR 2 give 36/43.
    (True, 0.65, "0.65"),
])
def test_graph_labels_use_full_graph_belief(renderer, filtered, support, posterior, expected):
    state = report_state(support=support, posterior=posterior)
    original = deepcopy(state)
    selected = {"D1", "CS1", "G1", "C1", "T1"} if filtered else None
    labels = graph_labels(state, renderer, selected)
    assert labels["D1"] == f"D1\nhypothesis\nbelief {expected}"
    assert labels["CS1"] == f"CS1\ncandidate\nbelief {expected}"
    for node_id, node_type in (("G1", "goal"), ("C1", "constraint"), ("T1", "test")):
        assert labels[node_id] == f"{node_id}\n{node_type}"
    if filtered:
        assert set(labels) == selected
    else:
        assert labels["E1"] == "E1\nobservation\nbelief 0.8"
    assert state == original


@pytest.mark.parametrize("renderer", RENDERERS)
def test_filtered_graph_uses_calibrated_factor_and_refreshes_inputs(renderer):
    state = report_state()
    state["edges"].append({
        "id": "E2-D1", "from": "E2", "to": "D1", "type": "leads_to",
        "reasoning": "Both observations are needed and their uncertainty overlaps.",
    })
    state["factors"] = [{
        "id": "F1", "relation": "leads_to", "target": "D1", "inputs": ["E1", "E2"],
        "aggregation": {"kind": "joint_probability", "probability": 0.5},
    }]
    assert validate_state(state).ok
    assert graph_labels(state, renderer, {"CS1"})["CS1"] == "CS1\ncandidate\nbelief 0.45"
    state["factors"][0]["aggregation"]["probability"] = 1.0
    state["nodes"][2]["prior"] = 1.0
    assert graph_labels(state, renderer, {"CS1"})["CS1"] == "CS1\ncandidate\nbelief 1"
    assert all("belief" not in node and "posterior" not in node for node in state["nodes"])


@pytest.mark.parametrize("posterior,expected", [(None, "0.837209"), (0.65, "0.65")])
def test_details_separate_effective_belief_from_authored_inputs(posterior, expected):
    state = report_state(support=True, posterior=posterior)
    original = deepcopy(state)
    cards = node_detail_cards(state)
    derived = detail_card(cards, "D1")
    assert f"Effective belief: {expected}" in derived
    assert "Local prior: 0.9" in derived
    if posterior is None:
        assert "Posterior override" not in derived
    else:
        assert "Posterior override: 0.65" in derived
    candidate = detail_card(cards, "CS1")
    assert f"Effective belief: {expected}" in candidate
    assert "Local prior" not in candidate
    assert "Posterior override" not in candidate
    for node_id in ("G1", "C1", "T1"):
        assert "Effective belief" not in detail_card(cards, node_id)
    assert state == original


@pytest.mark.parametrize("render_mode", ["mermaid", "offline"])
def test_html_report_keeps_labels_details_and_candidate_table_consistent(render_mode):
    state = report_state(support=True, posterior=0.65)
    original_nodes = deepcopy(state["nodes"])
    document = html_document(state, to_mermaid(state), render_mode=render_mode)
    assert "belief 0.65" in document
    assert "Effective belief: 0.65" in detail_card(document, "CS1")
    assert "<td>0.65</td>" in document  # Candidate table overrides stale report metadata.
    assert "Local prior: 0.9" in detail_card(document, "D1")
    assert "Posterior override: 0.65" in detail_card(document, "D1")
    assert state["nodes"] == original_nodes

    # Rendering cannot pin belief: removing the override resumes live calculation.
    del state["nodes"][2]["posterior"]
    document = html_document(state, to_mermaid(state), render_mode=render_mode)
    assert "belief 0.837" in document
    assert "Effective belief: 0.837209" in detail_card(document, "CS1")
    assert "<td>0.837209</td>" in document
    assert "Posterior override" not in detail_card(document, "D1")
    assert all("belief" not in node and "posterior" not in node for node in state["nodes"])
