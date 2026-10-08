"""The HTML page: the answer, its case, the graph canvas and the node details, with its browser behaviour inlined."""

from __future__ import annotations

import html
import json
from importlib.resources import files
from typing import Any

from .audit import audit_state
from .case_section import case_id_styles, case_section_html
from .costs import (
    format_belief,
    node_effective_truth_costs,
    node_priors,
    probability_from_cost,
)
from .identities import RenderIdentityMap, html_anchor, render_identity_map
from .models import BELIEF_NODE_TYPES, node_type_label
from .offline_render import offline_graph_svg
from .policy import (
    accepted_goal_ids,
    answer_candidates,
    answer_labels,
    claimed_answer,
    goal_best_candidates,
    preferred_goal_ids,
    ranked_candidates,
)
from .source_links import SourceLink, source_html
from .state import by_id


def page_asset(name: str) -> str:
    """The text of a CSS or JS file shipped beside this module; the page inlines it so it works offline."""
    return (files(__package__) / "page_assets" / name).read_text(encoding="utf-8")


def node_detail_cards(
    state: dict[str, Any],
    identities: RenderIdentityMap | None = None,
    linked_sources: dict[str, SourceLink] | None = None,
) -> str:
    linked_sources = linked_sources or {}
    node_truth_costs = node_effective_truth_costs(state)
    priors = node_priors(state)
    identities = identities or render_identity_map(state)
    labels = answer_labels(state)
    cards: list[str] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id", ""))
        raw_type = str(node.get("type", "node"))
        pill_text = node_type_label(node) if raw_type == "test" else raw_type
        if raw_id in labels:
            pill_text = f"{pill_text} · {labels[raw_id]}"
        text = html.escape(str(node.get("text") or node.get("short_text") or ""))
        source_text = source_html(str(node["source"]), linked_sources) if node.get("source") else ""
        extras: list[str] = []
        if raw_type in BELIEF_NODE_TYPES:
            extras.append(f"<span>Effective belief: {format_belief(probability_from_cost(node_truth_costs[raw_id]))}</span>")
            if priors[raw_id] is not None:
                extras.append(f"<span>Prior: {format_belief(priors[raw_id])}</span>")
        edge_notes = []
        for edge in state.get("edges", []):
            if isinstance(edge, dict) and raw_id in (edge.get("from"), edge.get("to")):
                relationship = f"{edge.get('from')} → {edge.get('to')} ({edge.get('type')})"
                note = f": {html.escape(str(edge['note']))}" if edge.get("note") else ""
                edge_notes.append(f"<li><strong>{html.escape(relationship)}</strong>{note}</li>")
        edges_html = ('<div class="edge-block"><ul>' + "".join(edge_notes) + "</ul></div>") if edge_notes else ""
        type_class = html.escape(raw_type)
        cards.append(
            f'<article class="detail-card {type_class}" data-node-type="{type_class}" id="{identities.node_anchor(raw_id)}" tabindex="0">'
            f'<header><code>{html.escape(raw_id)}</code><span class="pill">{html.escape(pill_text)}</span></header>'
            f'<p>{text}</p>'
            f'{"<p class=\"source\">Source: " + source_text + "</p>" if source_text else ""}'
            f'{"<p class=\"quote\">Quote: “" + html.escape(str(node["quote"])) + "”</p>" if node.get("quote") else ""}'
            f'{"<p class=\"note\">Not run: " + html.escape(str(node["not_run"])) + "</p>" if node.get("not_run") else ""}'
            f'{"<p class=\"note\">Note: " + html.escape(str(node["note"])) + "</p>" if node.get("note") else ""}'
            f'{"<p class=\"extras\">" + " ".join(extras) + "</p>" if extras else ""}'
            f'{edges_html}'
            '</article>'
        )
    return "".join(cards) or '<p class="empty">No node details recorded.</p>'


def candidate_focus_options(state: dict[str, Any], identities: RenderIdentityMap | None = None) -> str:
    identities = identities or render_identity_map(state)
    labels = answer_labels(state)
    options = ['<option value="">None</option>']
    for candidate in ranked_candidates(state):
        raw_cid = str(candidate["id"])
        key = html.escape(identities.node(raw_cid) or "", quote=True)
        text = html.escape(f"{raw_cid} ({labels[raw_cid]})" if raw_cid in labels else raw_cid)
        options.append(f'<option value="{key}">{text}</option>')
    return "".join(options)



def mermaid_flowchart_config(spacing: str) -> str:
    # Wider than the default 200px, so Mermaid does not wrap a claim line the label already cut.
    base = 'htmlLabels: true, useMaxWidth: false, wrappingWidth: 260'
    presets = {
        "default": base,
        "relaxed": base + ', nodeSpacing: 70, rankSpacing: 90, curve: "basis"',
        "wide": base + ', nodeSpacing: 100, rankSpacing: 130, curve: "basis"',
        "compact": base + ', nodeSpacing: 35, rankSpacing: 45, curve: "linear"',
    }
    return presets.get(spacing, base)

def graph_panel(
    title: str,
    mermaid_source: str,
    graph_id: str,
    focus_options: str = "",
    svg_graph: str | None = None,
) -> str:
    mermaid_escaped = html.escape(mermaid_source)
    section_id = html_anchor(graph_id, "section")
    focus_control = ""
    if focus_options:
        focus_control = (
            '<div class="focus-control">'
            '<span>Focus:</span>'
            f'<select data-candidate-focus-select aria-label="Focus candidate">{focus_options}</select>'
            '</div>'
        )
    graph_markup = svg_graph if svg_graph is not None else f'<pre class="mermaid">{mermaid_escaped}</pre>'
    source_details = f'<details class="graph-source"><summary>Mermaid source</summary><pre>{mermaid_escaped}</pre></details>'
    return f"""
<section id="{section_id}" class="graph-section">
  <div class="section-head">
    <h2>{html.escape(title)}</h2>
    <div class="graph-controls">
      <button type="button" data-canvas-mode="{graph_id}" aria-pressed="false">Canvas mode</button>
      <button type="button" data-reset="{graph_id}">Reset view</button>
      {focus_control}
    </div>
  </div>
  <p class="graph-hint">Click the canvas and the wheel zooms it; Esc lets go. To pan, drag in Canvas mode or hold Ctrl/⌘.</p>
  <div id="{graph_id}" class="mermaid-wrap graph-canvas graph-canvas-audit" tabindex="0" role="region" aria-label="{html.escape(title)} canvas">
    {graph_markup}
  </div>
  {source_details}
</section>
"""


def detail_filter_buttons() -> str:
    filters = [
        ("all", "All"),
        ("observation", "Observations"),
        ("constraint", "Constraints"),
        ("hypothesis", "Hypotheses"),
        ("candidate_solution", "Candidates"),
        ("test", "Tests"),
    ]
    buttons = [
        f'<button type="button" data-filter="{html.escape(value)}">{html.escape(label)}</button>'
        for value, label in filters
    ]
    return '<div class="detail-filters" aria-label="Filter node details">' + "".join(buttons) + "</div>"


def graph_edge_connections(
    state: dict[str, Any],
    identities: RenderIdentityMap | None = None,
) -> list[dict[str, str]]:
    identities = identities or render_identity_map(state)
    connections: list[dict[str, str]] = []
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("from"))
        dst = str(edge.get("to"))
        source_id = identities.node(src)
        target_id = identities.node(dst)
        if source_id is None or target_id is None:
            continue
        connections.append(
            {
                "from": source_id,
                "to": target_id,
                "label": str(edge.get("type") or edge.get("label") or "leads_to"),
            }
        )
    return connections


def candidate_focus_nodes(
    state: dict[str, Any],
    candidate: dict[str, Any],
    identities: RenderIdentityMap | None = None,
) -> list[str]:
    identities = identities or render_identity_map(state)
    raw_id = str(candidate.get("id") or "")
    node_ids: list[str] = [raw_id] if raw_id else []

    nodes_by_id = by_id(state.get("nodes", []), "node")
    # Derivation edges point premise -> conclusion; `requires` points the other way
    # (dependent -> dependency). `contradicts` and `answers` are not derivation.
    forward_derivation_edges = {"supports", "leads_to", "prompts", "tested_by", "tests"}
    premises_by_node: dict[str, list[str]] = {}
    contradictors_by_node: dict[str, list[str]] = {}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = str(edge.get("type") or edge.get("label") or "")
        source, target = str(edge.get("from")), str(edge.get("to"))
        if edge_type in forward_derivation_edges:
            premises_by_node.setdefault(target, []).append(source)
        elif edge_type == "requires":
            premises_by_node.setdefault(source, []).append(target)
        elif edge_type == "contradicts":
            contradictors_by_node.setdefault(target, []).append(source)

    # Focus is the candidate's full derivation: every transitive premise, including the
    # tests and hypotheses that produced its evidence. Rival branches stay dim because
    # they are only reachable downstream of shared premises, never upstream.
    pending = list(node_ids)
    seen_raw = set(node_ids)
    while pending:
        for premise in premises_by_node.get(pending.pop(), []):
            if premise not in seen_raw:
                seen_raw.add(premise)
                node_ids.append(premise)
                pending.append(premise)
    # Then one hop of counter-evidence, without its own chain: a ruled-out rival often has
    # no premises at all, and the evidence against it is the reason it lost.
    for node_id in list(node_ids):
        for contradictor in contradictors_by_node.get(node_id, []):
            if contradictor not in seen_raw:
                seen_raw.add(contradictor)
                node_ids.append(contradictor)
    seen: set[str] = set()
    result: list[str] = []
    for node_id in node_ids:
        if node_id not in nodes_by_id:
            continue
        mid = identities.node(node_id)
        if mid is None:
            continue
        if mid and mid not in seen:
            seen.add(mid)
            result.append(mid)
    return result


def candidate_focus_map(state: dict[str, Any], identities: RenderIdentityMap | None = None) -> dict[str, list[str]]:
    identities = identities or render_identity_map(state)
    focus: dict[str, list[str]] = {}
    for candidate in ranked_candidates(state):
        if "id" not in candidate:
            continue
        candidate_id = identities.node(str(candidate["id"]))
        if candidate_id is not None:
            focus[candidate_id] = candidate_focus_nodes(state, candidate, identities)
    return focus


def goal_policy_html(state: dict[str, Any]) -> str:
    groups = state.get("goal_groups") if isinstance(state.get("goal_groups"), list) else []
    policy = state.get("goal_policy") if isinstance(state.get("goal_policy"), dict) else {}
    if not groups and not policy:
        return ""
    accepted = ", ".join(f"<code>{html.escape(goal_id)}</code>" for goal_id in sorted(accepted_goal_ids(state))) or "all goals"
    preferred = ", ".join(f"<code>{html.escape(goal_id)}</code>" for goal_id in sorted(preferred_goal_ids(state))) or "none"
    group_items: list[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = html.escape(str(group.get("id", "")))
        goals = group.get("goals") if isinstance(group.get("goals"), list) else []
        goals_html = ", ".join(f"<code>{html.escape(str(goal_id))}</code>" for goal_id in goals)
        exclusivity = "exclusive" if group.get("exclusive") else "non-exclusive"
        group_items.append(f"<li><code>{group_id}</code>: {html.escape(exclusivity)} [{goals_html}]</li>")
    groups_html = f"<ul>{''.join(group_items)}</ul>" if group_items else '<p class="empty">No goal groups recorded.</p>'
    return f"""
  <section>
    <h2>Goal policy</h2>
    <p>Accepted goals: {accepted}. Preferred goals: {preferred}.</p>
    {groups_html}
  </section>"""


def goal_nodes(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in state.get("nodes", []) if isinstance(node, dict) and node.get("type") == "goal"]


def page_heading(state: dict[str, Any]) -> tuple[str, str]:
    """The page's plain-text title, and the header markup that names what was asked.

    A single goal is the question the page answers, so it is the heading. Several goals
    sit under the summary title, each with its id so the answer lines can name it.
    """
    summary = state.get("summary", {}) if isinstance(state.get("summary"), dict) else {}
    given_title = str(summary.get("title") or "")
    goals = goal_nodes(state)
    if len(goals) == 1:
        question = str(goals[0].get("text") or goals[0].get("id"))
        eyebrow = f'<p class="eyebrow">{html.escape(given_title)}</p>' if given_title else ""
        return question, f"{eyebrow}<h1>{html.escape(question)}</h1>"
    title = given_title or "Reasoning graph"
    goal_items = "".join(
        f'<li><code>{html.escape(str(goal.get("id")))}</code> {html.escape(str(goal.get("text") or ""))}</li>' for goal in goals
    )
    goal_list = f'<ul class="goal-list">{goal_items}</ul>' if goal_items else ""
    return title, f"<h1>{html.escape(title)}</h1>{goal_list}"


def status_badge(state: dict[str, Any], quote_errors: list[str] | None, answer_shown: bool) -> str:
    """Whether the claimed answer holds. It names the answer only when no answer line does,
    as for a claim that names no candidate in the graph."""
    # Computed here, not read from the state, so the reader never sees a stale status.
    report = audit_state(state, quote_errors)
    outcome = "fail" if not report.ok else "pass" if claimed_answer(state) else "open"
    text = report.outcome if answer_shown else report.status
    return f'<p class="status" data-outcome="{outcome}">{html.escape(text)}</p>'


def verdict(state: dict[str, Any], quote_errors: list[str] | None) -> str:
    """The answer and whether it holds, side by side."""
    answers = answer_lines(state)
    badge = status_badge(state, quote_errors, answer_shown=bool(answers))
    if not answers:
        return badge
    return f'<div class="verdict"><div class="answers">{answers}</div>{badge}</div>'


def answer_lines(state: dict[str, Any]) -> str:
    """One header line per answered goal, resolved from the graph: the candidate's id and text."""

    nodes = by_id(state.get("nodes", []), "node")
    answers = answer_candidates(state)
    lines = []
    for goal_id, answer_id in sorted(answers.items()):
        if answer_id is None:
            continue
        lead = f"Answer to {goal_id}" if len(answers) > 1 else "Answer"
        text = str(nodes[answer_id].get("text") or "")
        lines.append(f'<p class="answer"><strong>{html.escape(lead)}</strong> <code>{html.escape(answer_id)}</code> {html.escape(text)}</p>')
    return "".join(lines)


def answer_rank_notes(state: dict[str, Any]) -> str:
    """Tell the reader when the answer is not the candidate the graph ranks first.

    Only the reader is told: no gate and no command shows the agent a ranking.
    """

    truth_costs = node_effective_truth_costs(state)
    top_ranked = goal_best_candidates(state)
    notes = []
    for goal_id, answer_id in sorted(answer_candidates(state).items()):
        top_id = top_ranked.get(goal_id)
        if answer_id is None or top_id is None or not truth_costs[top_id] < truth_costs[answer_id]:
            continue
        top_belief, answer_belief = (format_belief(probability_from_cost(truth_costs[node_id])) for node_id in (top_id, answer_id))
        notes.append(
            f'<p class="answer-rank-note">Answer <code>{html.escape(answer_id)}</code> is not the top-ranked candidate for '
            f"<code>{html.escape(goal_id)}</code>: <code>{html.escape(top_id)}</code> ranks higher "
            f"(belief {top_belief} against {answer_belief}).</p>"
        )
    return "".join(notes)


def html_document(
    state: dict[str, Any],
    mermaid_source: str,
    spacing: str = "default",
    render_mode: str = "mermaid",
    quote_errors: list[str] | None = None,
    linked_sources: dict[str, SourceLink] | None = None,
) -> str:
    linked_sources = linked_sources or {}
    page_title, heading_html = page_heading(state)
    identities = render_identity_map(state)
    offline_mode = render_mode == "offline"
    audit_svg = offline_graph_svg(state, spacing, "audit-graph", identities=identities) if offline_mode else None
    focus_options = candidate_focus_options(state, identities)
    goal_policy_section = goal_policy_html(state)

    case_html = case_section_html(state, identities, linked_sources)
    case_nav = '<a href="#case-section">Case</a>' if case_html else ""
    details_html = node_detail_cards(state, identities, linked_sources)
    filters_html = detail_filter_buttons()
    page_data = {
        "graphEdgeMaps": {"audit-graph": graph_edge_connections(state, identities=identities)},
        "candidateFocusMap": candidate_focus_map(state, identities),
    }
    # "</" would close the <script> element that carries the JSON.
    page_data_json = json.dumps(page_data, ensure_ascii=False).replace("</", "<\\/")
    if offline_mode:
        bootstrap = """<script>
  setupGraphs();
</script>"""
    else:
        bootstrap = f"""<script type="module">
  // Mermaid 12 bundles the ELK layout, set below.
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@12/dist/mermaid.esm.min.mjs";
  // The graph takes the page's typeface, read from the stylesheet so it is set in one place.
  const fontFamily = getComputedStyle(document.body).fontFamily;
  // Edges, edge labels and lane titles take the page's palette, light or dark; node colours
  // come from the source. Mermaid derives shades from these, so they must be plain hex.
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const themeVariables = {{
    fontFamily,
    darkMode: matchMedia("(prefers-color-scheme: dark)").matches,
    background: token("--canvas-bg"),
    lineColor: token("--muted"),
    textColor: token("--ink"),
    titleColor: token("--ink"),
    edgeLabelBackground: token("--canvas-bg"),
    primaryColor: token("--canvas-bg"),
    // Mermaid also paints edge labels with this; nodes set their own text colour.
    primaryTextColor: token("--ink"),
    primaryBorderColor: token("--muted"),
  }};
  // ELK, not dagre, named even though it is the default: a test's result edge runs from the
  // Hypotheses lane back into Observations, and dagre then stacks the lanes and tangles every edge.
  mermaid.initialize({{ startOnLoad: false, securityLevel: "loose", theme: "base", layout: "elk", fontFamily, themeVariables, flowchart: {{ {mermaid_flowchart_config(spacing)} }} }});
  mermaid.run({{ querySelector: ".mermaid" }}).then(setupGraphs).catch((error) => {{
    console.error("Mermaid render failed", error);
    setupGraphs();
  }});
</script>"""

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page_title)}</title>
  <style>
{page_asset("page.css")}{case_id_styles()}  </style>
</head>
<body>
<nav class="floating-nav" aria-label="Graph navigation">
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="floating-nav-menu"><span aria-hidden="true">☰</span> Sections</button>
  <div id="floating-nav-menu" class="nav-menu">
    <a href="#top">Top</a>
    {case_nav}
    <a href="#section-audit-graph">Graph</a>
    <a href="#node-details-section">Details</a>
  </div>
</nav>
<main>
  <header class="hero" id="top">
    {heading_html}
    {verdict(state, quote_errors)}
    {answer_rank_notes(state)}
  </header>

  {case_html}

  {graph_panel("Full audit graph", mermaid_source, "audit-graph", focus_options, audit_svg)}

  {goal_policy_section}

  <section id="node-details-section">
    <details class="node-details">
      <summary><h2>Node details</h2></summary>
      <p class="hint">Every node of the graph. Use filters, or click an id or a graph node for its popup card.</p>
      {filters_html}
      <div class="detail-grid">{details_html}</div>
    </details>
  </section>
</main>
<dialog id="node-modal" class="node-modal" aria-labelledby="node-modal-title">
  <div class="modal-bar">
    <h2 id="node-modal-title" class="modal-title">Node details</h2>
    <button type="button" class="modal-close" data-close-modal aria-label="Close node details">×</button>
  </div>
  <div id="node-modal-content" class="modal-shell"></div>
</dialog>
<script type="application/json" id="page-data">{page_data_json}</script>
<script>
{page_asset("page.js")}
// The case, the popups and the nav work at once; the graph is set up once it is drawn.
setupPage();
</script>
{bootstrap}
</body>
</html>
"""
