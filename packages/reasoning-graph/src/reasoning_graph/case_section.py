"""The case section of the page: the case for each answer, laid out for a reader to check.

Every line is a node or an edge of the graph. Each id links to the node's card, which
the page opens as a popup.
"""

from __future__ import annotations

import html
from typing import Any

from .case import Case, CaseLink, CaseNode, CaseRival, CaseTest, WeakSpot, answer_cases
from .costs import edge_weight_label, format_belief
from .graph_view import NODE_COLORS
from .identities import RenderIdentityMap
from .models import node_render_class
from .source_links import SourceLink, source_html

WEAK_SPOT_TEXT = {
    "no_input": "rests on no premise or support",
    "single_input": "rests on a single premise or support",
    "no_quote": "has no verbatim quote",
    "test_not_run": "was not run",
}


def case_id_styles() -> str:
    """Colour each id chip like its node in the graph, from the shared palette."""
    return "".join(
        f'.case-id[data-class="{render_class}"] {{ background: {fill}; border-color: {stroke}; }}\n'
        for render_class, (fill, stroke) in NODE_COLORS.items()
    )


class _CaseMarkup:
    def __init__(self, state: dict[str, Any], identities: RenderIdentityMap, linked_sources: dict[str, SourceLink]) -> None:
        self.nodes = {str(node.get("id")): node for node in state.get("nodes", []) if isinstance(node, dict)}
        self.identities = identities
        self.linked_sources = linked_sources

    def node_link(self, node_id: str) -> str:
        render_class = node_render_class(self.nodes[node_id])
        return (
            f'<a class="case-id" data-class="{html.escape(render_class)}" '
            f'href="#{html.escape(self.identities.node_anchor(node_id))}">{html.escape(node_id)}</a>'
        )

    def node_facts(self, node: CaseNode) -> str:
        """The node's text, its belief when it is a claim, and an observation's quote."""
        belief = f' <span class="case-belief">belief {format_belief(node.belief)}</span>' if node.belief is not None and node.type != "observation" else ""
        quote = ""
        if node.quote:
            source = f" <cite>{source_html(node.source, self.linked_sources)}</cite>" if node.source else ""
            quote = f'<blockquote class="case-quote">{html.escape(node.quote)}{source}</blockquote>'
        return f'{belief} <span class="case-text">{html.escape(node.text)}</span>{quote}'

    def link_line(self, link: CaseLink, show_target: bool = False) -> str:
        # Against-it lines name the node they contradict; why-tree lines sit under it already.
        target = f"{self.node_link(link.target)} ← " if show_target else ""
        weight_label = edge_weight_label(link.relation, link.score)
        if link.group:
            weight_label = f"group {link.group} · {weight_label}"
        weight = f' <span class="case-weight">{html.escape(weight_label)}</span>' if weight_label else ""
        head = f'{target}{self.relation(link.relation)} {self.node_link(link.node.id)}{weight}'
        if link.reference:
            return f'<li class="case-line case-ref">{head} <span class="case-note">shown above</span></li>'
        reasons = self.link_list(link.reasons) if link.reasons else ""
        return f'<li class="case-line">{head}{self.node_facts(link.node)}{reasons}</li>'

    @staticmethod
    def relation(name: str) -> str:
        # data-rel lets the stylesheet colour for and against apart.
        return f'<span class="case-rel" data-rel="{html.escape(name, quote=True)}">{html.escape(name)}</span>'

    def link_list(self, links: tuple[CaseLink, ...], show_target: bool = False) -> str:
        return '<ul class="case-tree">' + "".join(self.link_line(link, show_target) for link in links) + "</ul>"

    def test_line(self, test: CaseTest) -> str:
        about = ", ".join(self.node_link(node_id) for node_id in test.about)
        if test.node.not_run:
            outcome = f'<p class="case-outcome">Not run: {html.escape(test.node.not_run)}</p>'
        elif test.results:
            outcome = '<ul class="case-tree">' + "".join(
                f'<li class="case-line">{self.relation("result")} {self.node_link(result.id)}{self.node_facts(result)}</li>'
                for result in test.results
            ) + "</ul>"
        else:
            outcome = '<p class="case-outcome">No result recorded.</p>'
        return (
            f'<li class="case-line">{self.node_link(test.node.id)} <span class="case-note">for {about}</span>'
            f' <span class="case-text">{html.escape(test.node.text)}</span>{outcome}</li>'
        )

    def rival_line(self, rival: CaseRival) -> str:
        against = self.link_list(rival.against) if rival.against else ""
        return f'<li class="case-line">{self.node_link(rival.node.id)}{self.node_facts(rival.node)}{against}</li>'

    def weak_spot_line(self, spot: WeakSpot) -> str:
        return f"<li>{self.node_link(spot.node_id)} {html.escape(WEAK_SPOT_TEXT[spot.kind])}</li>"

    def case(self, case: Case, several: bool) -> str:
        goal = f' <span class="case-note">answer to</span> {self.node_link(case.goal.id)}' if several else ""
        # (heading, count, body, what an empty part says). An empty part is not worth a
        # heading of its own, so the empty ones share one line after the rest.
        parts = (
            ("Why believe it", len(case.why), lambda: self.link_list(case.why), "Nothing supports it"),
            ("Against it", len(case.against), lambda: self.link_list(case.against, show_target=True), "Nothing against it"),
            ("Tests", len(case.tests), lambda: '<ul class="case-tree">' + "".join(map(self.test_line, case.tests)) + "</ul>", "No tests"),
            ("Rivals", len(case.rivals), lambda: '<ol class="case-tree">' + "".join(map(self.rival_line, case.rivals)) + "</ol>", "No rivals"),
            ("Weak spots", len(case.weak_spots), lambda: "<ul>" + "".join(map(self.weak_spot_line, case.weak_spots)) + "</ul>", "No weak spots"),
        )
        filled = "".join(
            f'<div class="case-part"><h3>{html.escape(title)} <span class="case-count">{count}</span></h3>{body()}</div>'
            for title, count, body, _ in parts
            if count
        )
        empty = " · ".join(html.escape(note) for _, count, _, note in parts if not count)
        empty_line = f'<p class="case-empty">{empty}</p>' if empty else ""
        return (
            f'<div class="case"><h2>The case for {self.node_link(case.answer.id)}{goal}</h2>'
            f'<p class="case-answer">{self.node_facts(case.answer)}</p>'
            f"{filled}{empty_line}</div>"
        )


def case_section_html(state: dict[str, Any], identities: RenderIdentityMap, linked_sources: dict[str, SourceLink]) -> str:
    """The case section, or nothing while no answer is claimed."""
    cases = answer_cases(state)
    if not cases:
        return ""
    markup = _CaseMarkup(state, identities, linked_sources)
    return '<section id="case-section" class="case-section">' + "".join(markup.case(case, len(cases) > 1) for case in cases) + "</section>"
