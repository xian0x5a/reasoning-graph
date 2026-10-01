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

from reasoning_graph.costs import format_belief
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document, node_detail_cards
from reasoning_graph.validation import validate_state


RENDERERS = ("mermaid", "offline")



def decode_mermaid_entities(label: str) -> str:
    """Read a label's text as Mermaid shows it: `#lt;` and `#35;` are its entity codes for
    `&lt;` and `&#35;`, so any literal tag is the renderer's own markup."""
    entities = re.sub(r"#([a-z]+);", r"&\1;", re.sub(r"#(\d+);", r"&#\1;", label))
    return html.unescape(re.sub(r"<[^>]+>", "", entities.replace("<br/>", "\n")))


def report_state(*, support=False):
    state = {
        "nodes": [
            {"id": "E1", "type": "observation", "text": "Observed premise", "score": 4},
            {"id": "E2", "type": "observation", "text": "Independent signal", "score": 5},
            {"id": "D1", "type": "hypothesis", "text": "Conclusion", "score": 5},
            {"id": "CS1", "type": "candidate_solution", "text": "The answer is 42", "answer_kind": "exact_answer"},
            {"id": "G1", "type": "goal", "text": "Find the answer"},
            {"id": "C1", "type": "constraint", "text": "Use the observed data"},
            {"id": "T1", "type": "test", "text": "Check the premise"},
        ],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to"},
            {"from": "D1", "to": "CS1", "type": "leads_to"},
            {"from": "CS1", "to": "G1", "type": "answers"},
        ],
    }
    if support:
        state["edges"].append({
            "from": "E2", "to": "D1", "type": "supports", "score": 3,
            })
    assert validate_state(state).ok
    return state


def graph_labels(state, renderer):
    if renderer == "offline":
        svg = ET.fromstring(offline_graph_svg(state))
        ns = {"svg": "http://www.w3.org/2000/svg"}
        return {
            node.attrib["data-node-id"]: "\n".join(
                line.text or "" for line in node.findall(".//svg:tspan", ns)
            )
            for node in svg.findall(".//svg:g[@class='node']", ns)
        }
    source = to_mermaid(state)
    return {
        node_id: decode_mermaid_entities(label)
        for node_id, label in re.findall(r'^\s+(\w+)\["(.*?)"\]', source, re.MULTILINE)
    }


def detail_card(document, node_id):
    match = re.search(rf'<article\b[^>]*id="details-{node_id}"[^>]*>(.*?)</article>', document, re.DOTALL)
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("support,expected", [
    (False, "63%"),
    (True, "77%"),  # 0.63 base and ratio 2 give 126/163.
])
def test_graph_labels_carry_the_computed_belief(renderer, support, expected):
    state = report_state(support=support)
    original = deepcopy(state)
    labels = graph_labels(state, renderer)
    assert labels["D1"] == f"D1\nConclusion\nbelief {expected}"
    assert labels["CS1"] == f"CS1\nThe answer is 42\nbelief {expected}"
    assert labels["G1"] == "G1\nFind the answer\ngoal"
    assert labels["C1"] == "C1\nUse the observed data\nconstraint"
    assert labels["T1"] == "T1\nCheck the premise\ntest"
    assert labels["E1"] == "E1\nObserved premise\nbelief 70%"
    assert state == original


@pytest.mark.parametrize("renderer", RENDERERS)
def test_graph_uses_the_premise_group_and_refreshes_inputs(renderer):
    state = report_state()
    state["edges"].append({
        "from": "E2", "to": "D1", "type": "leads_to",
        })
    state["factors"] = [{"id": "F1", "edges": ["E1-D1", "E2-D1"], "score": 3}]
    assert validate_state(state).ok
    assert graph_labels(state, renderer)["CS1"] == "CS1\nThe answer is 42\nbelief 45%"
    state["factors"][0]["score"] = 5
    del state["nodes"][2]["score"]
    assert graph_labels(state, renderer)["CS1"] == "CS1\nThe answer is 42\nbelief 90%"
    assert all("belief" not in node for node in state["nodes"])


def test_details_separate_effective_belief_from_authored_inputs():
    state = report_state(support=True)
    original = deepcopy(state)
    cards = node_detail_cards(state)
    derived = detail_card(cards, "D1")
    assert "Effective belief: 77%" in derived
    assert "Score: 5" in derived
    candidate = detail_card(cards, "CS1")
    assert "Effective belief: 77%" in candidate
    assert "Score" not in candidate
    for node_id in ("G1", "C1", "T1"):
        assert "Effective belief" not in detail_card(cards, node_id)
    assert state == original


@pytest.mark.parametrize("render_mode", ["mermaid", "offline"])
def test_html_report_keeps_labels_and_details_consistent(render_mode):
    state = report_state(support=True)
    original_nodes = deepcopy(state["nodes"])
    document = html_document(state, to_mermaid(state), render_mode=render_mode)
    assert "belief 77%" in document
    assert "Effective belief: 77%" in detail_card(document, "CS1")
    assert "Score: 5" in detail_card(document, "D1")
    assert state["nodes"] == original_nodes


def ranked_state(answer):
    """CS1 ranks above CS2; the summary names `answer`."""
    state = {
        "summary": {"title": "Who did it?", "answer": answer},
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Who did it?"},
            {"id": "O1", "type": "observation", "text": "The gardener signed in at nine"},
            {"id": "O2", "type": "observation", "text": "The butler had the key"},
            {"id": "CS1", "type": "candidate_solution", "text": "The gardener", "answer_kind": "exact_answer"},
            {"id": "CS2", "type": "candidate_solution", "text": "The butler", "answer_kind": "exact_answer"},
        ],
        "edges": [
            {"from": "O1", "to": "CS1", "type": "leads_to"},
            {"from": "O2", "to": "CS2", "type": "supports"},
            {"from": "CS1", "to": "G1", "type": "answers"},
            {"from": "CS2", "to": "G1", "type": "answers"},
        ],
    }
    assert validate_state(state).ok
    return state


@pytest.mark.parametrize("render_mode", ["mermaid", "offline"])
def test_html_marks_an_answer_that_is_not_the_top_ranked_candidate(render_mode):
    state = ranked_state("The butler did it.")
    document = html_document(state, to_mermaid(state), render_mode=render_mode)
    assert 'class="answer-rank-note"' in document
    assert "Answer <code>CS2</code> is not the top-ranked candidate for <code>G1</code>" in document
    assert "<code>CS1</code> ranks higher" in document


@pytest.mark.parametrize("answer", ["The gardener did it.", ""])
def test_html_leaves_a_top_ranked_or_unnamed_answer_unmarked(answer):
    state = ranked_state(answer)
    document = html_document(state, to_mermaid(state))
    assert 'class="answer-rank-note"' not in document


@pytest.mark.parametrize("render_mode", ["mermaid", "offline"])
def test_html_header_names_the_answer_by_id_and_text(render_mode):
    state = ranked_state("CS2")
    document = html_document(state, to_mermaid(state), render_mode=render_mode)
    assert '<p class="answer"><strong>Answer:</strong> CS2, The butler</p>' in document
    assert "Candidate ranking" not in document
    assert "<th>Rank</th>" not in document


def test_html_header_has_no_answer_line_while_none_is_claimed():
    state = ranked_state("")
    document = html_document(state, to_mermaid(state))
    assert '<p class="answer">' not in document
    assert '<span class="status-label">Status</span> no answer claimed' in document


@pytest.mark.parametrize("renderer", RENDERERS)
def test_graph_labels_shorten_the_claim_and_keep_its_characters(renderer):
    state = report_state()
    state["nodes"][2]["text"] = "Tom & <Jerry> left through the kitchen door before the clock struck nine that night"
    state["nodes"][3]["short_text"] = "Tom did it"
    state["nodes"][0]["text"] = 'Roger\'s "#1" dish'

    labels = graph_labels(state, renderer)

    # Two lines at most, cut on a word, so a long claim cannot blow up its node.
    assert labels["D1"] == "D1\nTom & <Jerry> left through\nthe kitchen door before…\nbelief 63%"
    assert labels["CS1"] == "CS1\nTom did it\nbelief 63%"
    assert labels["E1"] == 'E1\nRoger\'s "#1" dish\nbelief 70%'


@pytest.mark.parametrize("renderer", RENDERERS)
def test_graph_labels_the_answer_and_no_rival(renderer):
    labels = graph_labels(ranked_state("The butler did it."), renderer)
    assert labels["CS2"].split("\n")[:2] == ["CS2 · ANSWER", "The butler"]
    assert labels["CS1"].split("\n")[:2] == ["CS1", "The gardener"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_graph_labels_no_answer_while_none_is_claimed(renderer):
    labels = graph_labels(ranked_state(""), renderer)
    assert not any("ANSWER" in label for label in labels.values())


def two_goal_state():
    state = ranked_state("CS1 and CS3")
    state["nodes"] += [
        {"id": "G2", "type": "goal", "text": "With what?"},
        {"id": "O3", "type": "observation", "text": "The rope was cut"},
        {"id": "CS3", "type": "candidate_solution", "text": "The shears", "answer_kind": "exact_answer"},
    ]
    state["edges"] += [
        {"from": "O3", "to": "CS3", "type": "leads_to"},
        {"from": "CS3", "to": "G2", "type": "answers"},
    ]
    assert validate_state(state).ok
    return state


@pytest.mark.parametrize("renderer", RENDERERS)
def test_answer_label_names_the_goal_when_there_are_several(renderer):
    state = two_goal_state()
    labels = graph_labels(state, renderer)
    assert labels["CS1"].split("\n")[0] == "CS1 · ANSWER to G1"
    assert labels["CS3"].split("\n")[0] == "CS3 · ANSWER to G2"
    document = html_document(state, to_mermaid(state))
    assert '<p class="answer"><strong>Answer to G1:</strong> CS1, The gardener</p>' in document
    assert '<p class="answer"><strong>Answer to G2:</strong> CS3, The shears</p>' in document


def test_focus_option_and_detail_card_say_which_candidate_is_the_answer():
    state = ranked_state("CS2")
    document = html_document(state, to_mermaid(state))
    assert '<option value="CS2">CS2 (ANSWER)</option>' in document
    assert '<option value="CS1">CS1</option>' in document
    assert "ANSWER" in detail_card(document, "CS2")
    assert "ANSWER" not in detail_card(document, "CS1")


def test_mermaid_styles_only_the_groups_it_draws():
    # A style line for a subgraph that is not drawn makes Mermaid draw a node of that name.
    source = to_mermaid(ranked_state(""))
    assert "style cluster_candidates" in source
    for absent in ("cluster_hypotheses", "cluster_factors", "cluster_other"):
        assert absent not in source


@pytest.mark.parametrize("probability,shown", [
    (0.741, "74%"),
    (0.5, "50%"),
    (0.996, ">99%"),  # never "100%": no belief is certain
    (0.004, "<1%"),  # never "0%": no belief is ruled out
])
def test_belief_is_shown_as_a_whole_percent(probability, shown):
    assert format_belief(probability) == shown


def test_mermaid_labels_use_its_own_entity_codes():
    state = report_state()
    state["nodes"][0]["text"] = """Roger's & "Tom's" <#1>"""

    labels = re.findall(r'^\s+\w+\["(.*?)"\]', to_mermaid(state), re.MULTILINE)

    # Mermaid reads "#...;" as its own entity code, so an HTML entity such as &#x27;
    # reached the page as "&&x27;". Its own codes are all a label may carry.
    assert labels and not any("&" in label for label in labels)


def test_mermaid_node_labels_lead_with_the_id_in_bold():
    state = report_state()

    labels = re.findall(r'^\s+\w+\["(.*?)"\]', to_mermaid(state), re.MULTILINE)

    assert labels
    for label in labels:
        first_line = label.split("<br/>")[0]
        assert re.fullmatch(r"<b>[^<]+</b>", first_line), label
