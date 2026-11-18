"""Reasoning graph schema and policy validation."""

from __future__ import annotations

from typing import Any

from .costs import (
    EVIDENCE_EDGE_TYPES,
    REMOVED_EDGE_SCORE_FIELDS,
    REMOVED_EDGE_TYPES,
    REMOVED_NODE_SCORE_FIELDS,
    REMOVED_NODE_TYPES,
    RULED_OUT_EDGE_TYPE,
    RemovedInputError,
    ScoredDeductionError,
    assert_acyclic_premise_dependencies,
    node_effective_truth_costs,
    removed_score_field_message,
    require_score,
    resolve_edge_groups,
)
from .models import ANSWER_KINDS, BELIEF_NODE_TYPES, EDGE_TYPES, EPISTEMIC_GOAL_MARKERS, NODE_TYPES, RESULT_NODE_TYPES, ValidationResult
from .policy import accepted_goal_ids, candidate_goal_targets, goal_accepts_answer_kind, goal_ids, goal_requirements
from .schema_validation import state_schema_errors, state_type_errors
from .state import edge_id


# Sections that held a second copy of the graph for the reader. No agent wrote one in 42
# benchmark states, and the rendered view derives all of it from the graph.
REMOVED_GRAPH_COPIES = ("report", "presentation", "view")

# Top-level sections the schema rejects, each with what replaced it: the schema says neither.
REMOVED_SECTIONS = {
    "premise_groups": "premise_groups is not supported; use factors, which group premise_of edges by id",
    "solutions": "solutions was removed: a candidate is a hypothesis with an answers edge to its goal, "
    "and summary.answer names the answer; delete the field",
    # It configured the stop gate, which went with the stop certificate.
    "stop_policy": "stop_policy was removed: nothing gates a stop; audit checks the answer summary.answer claims; delete the field",
    **{
        section: f"{section} was removed: the state is the graph; the answer is summary.answer, a reason is a note on the node or edge, "
        "a next check is a test node; delete the field"
        for section in REMOVED_GRAPH_COPIES
    },
    # The trace was verified to guard the stop certificate; nothing else read it.
    "events": "events was removed: the state keeps no trace; the list order of nodes and edges is the order of the work; delete the field",
}


def authored_field_errors(nodes: list[Any], edges: list[Any]) -> list[str]:
    """Reject removed fields, and scores off the scale or on objects that take none.

    `record` runs this on a patch's additions too, so a removed field names its replacement
    there instead of failing with the schema's generic message. It also runs on a state of the
    wrong shape, so a type that is not a string reads as no type rather than raise on lookup.
    """
    errors: list[str] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        owner = f"node {node.get('id') or index}"
        node_type = _string_or_none(node.get("type"))
        if node_type in REMOVED_NODE_TYPES:
            errors.append(f"{owner}: {REMOVED_NODE_TYPES[node_type]}")
        if "answer_kind" in node:
            # A kind says how a claim answers one goal, and one claim may answer two (ADR 0019).
            errors.append(f"{owner}: answer_kind belongs on the answers edge; move it onto the edge from this hypothesis to its goal")
        if isinstance(node.get("id"), str) and "-" in node["id"]:
            # `O1-H1` has to read as one edge, from O1 to H1.
            errors.append(f"node id {node['id']!r} contains a hyphen; an edge is named from-to, so a node id takes none")
        errors.extend(removed_score_field_message(owner, field) for field in REMOVED_NODE_SCORE_FIELDS if field in node)
        if "belief" in node:
            errors.append(f"{owner}: belief was removed from the state; it is computed when the graph is rendered; delete the field")
        if "score" not in node:
            continue
        if node_type not in BELIEF_NODE_TYPES:
            errors.append(f"{owner}: score is only valid on observation and hypothesis nodes")
            continue
        try:
            require_score(node["score"])
        except ValueError as exc:
            errors.append(f"{owner}: {exc}")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        owner = f"edge {edge_id(edge)}"
        edge_type = _string_or_none(edge.get("type"))
        if edge_type in REMOVED_EDGE_TYPES:
            errors.append(f"{owner}: {REMOVED_EDGE_TYPES[edge_type]}")
        if "id" in edge:
            # Agents wrote from-to as the id in 225 of 245 edges, the same thing twice.
            errors.append(f"{owner}: id was removed; an edge is identified by its ends, as from-to; delete the field")
        errors.extend(removed_score_field_message(owner, field) for field in REMOVED_EDGE_SCORE_FIELDS if field in edge)
        if "label" in edge:
            errors.append(f"{owner}: label was removed; name the relation in type instead; delete the field")
        if "reasoning" in edge:
            # `reasoning` was 45% of edge bytes and mostly restated the two node texts.
            errors.append(f"{owner}: reasoning was removed; use the optional note, or leave the link unexplained when the two texts make it obvious")
        errors.extend(answer_kind_errors(edge))
        if "score" not in edge:
            continue
        if edge_type not in EVIDENCE_EDGE_TYPES:
            errors.append(f"{owner}: score is only valid on supports/contradicts edges")
            continue
        try:
            require_score(edge["score"])
        except ValueError as exc:
            errors.append(f"{owner}: {exc}")
    return errors


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def answer_kind_errors(edge: dict[str, Any]) -> list[str]:
    """An answers edge carries an answer_kind, and no other edge does (ADR 0019)."""
    owner = f"edge {edge_id(edge)}"
    if edge.get("type") != "answers":
        return [f"{owner}: answer_kind is only valid on answers edges; it says how a hypothesis answers a goal"] if "answer_kind" in edge else []
    # A list or object kind would make the set lookup raise instead of report.
    if not isinstance(edge.get("answer_kind"), str) or edge["answer_kind"] not in ANSWER_KINDS:
        return [f"{owner}: answers edge answer_kind must be one of {sorted(ANSWER_KINDS)}, got {edge.get('answer_kind')!r}"]
    return []


EXCLUSIVE_SET_MEMBER_TYPES = {"hypothesis"}
# Observations are recorded as seen, so only a claim can rest on premises.
PREMISE_TARGET_TYPES = {"hypothesis"}


def premise_endpoint_hint(src_type: str | None, dst_type: str | None) -> str:
    """Name the edge a misused premise_of was probably meant to be."""
    if src_type == "test":
        return "; a test's result is an observation, linked by yields"
    if dst_type == "test":
        return "; link what calls for a test to it by prompts"
    if dst_type == "observation":
        return "; a conclusion drawn from observations is a hypothesis"
    return ""


def exclusive_set_errors(exclusive_sets: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]]) -> list[str]:
    """Each set names at least two different existing claims; ids are unique.

    Like a factor naming a removed edge, a set naming a removed node fails rather than
    shrinking silently: the patch that removes a member must replace or remove the set.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, exclusive_set in enumerate(exclusive_sets):
        label = f"exclusive_sets[{i}]"
        set_id = exclusive_set.get("id")
        if not set_id:
            errors.append(f"{label} missing string id")
        elif set_id in seen_ids:
            errors.append(f"duplicate exclusive set id {set_id}")
        else:
            seen_ids.add(set_id)
        members = exclusive_set.get("members")
        if not members or len(set(members)) < 2 or len(set(members)) != len(members):
            errors.append(f"{label}.members must list at least two different node ids")
            continue
        for member in members:
            member_type = nodes_by_id.get(member, {}).get("type")
            if member_type is None:
                errors.append(f"{label}.members references missing node {member!r}")
            elif member_type not in EXCLUSIVE_SET_MEMBER_TYPES:
                errors.append(f"{label}.members: {member} is a {member_type}; only hypothesis claims can be exclusive")
    return errors


UNRESOLVED_OUTCOME_MARKERS = (
    "not solved",
    "not established",
    "cannot establish",
    "insufficient evidence",
    "missing dependency",
    "undetermined",
    "not recoverable",
)


def answers_edge_errors(
    edge: dict[str, Any],
    src_type: str | None,
    dst_type: str | None,
    goals_by_id: dict[Any, dict[str, Any]],
    accepted_goals: set[str],
) -> list[str]:
    """An answers edge runs hypothesis -> goal, with an answer_kind the goal accepts.

    A missing or unknown kind is already named by answer_kind_errors.
    """
    owner = f"edge {edge_id(edge)}"
    errors: list[str] = []
    if src_type != "hypothesis" or dst_type != "goal":
        errors.append(f"{owner}: answers must connect hypothesis -> goal; it is {src_type} -> {dst_type}")
    answer_kind = edge.get("answer_kind")
    goal_id = edge.get("to")
    goal = goals_by_id.get(goal_id)
    if isinstance(answer_kind, str) and answer_kind in ANSWER_KINDS and goal is not None and goal_id in accepted_goals and not goal_accepts_answer_kind(goal, str(answer_kind)):
        errors.append(f"{owner}: answer_kind {answer_kind!r} does not answer accepted goal {goal_id!r}: {goal.get('text')!r}")
    return errors


def validate_state(state: Any) -> ValidationResult:
    if not isinstance(state, dict):
        return ValidationResult(errors=["schema $: state must be an object"], warnings=[])
    nodes, edges = state.get("nodes", []), state.get("edges", [])
    # Listed with the schema's errors: the schema rejects these too, but does not say what replaced them.
    errors = (
        state_schema_errors(state)
        + authored_field_errors(nodes if isinstance(nodes, list) else [], edges if isinstance(edges, list) else [])
        + [message for section, message in REMOVED_SECTIONS.items() if section in state]
    )
    if state_type_errors(state):
        # The graph rules find nodes and edges by id in lists of objects; on a value of another
        # JSON type they would raise instead of report. The schema errors above name it.
        return ValidationResult(errors=errors, warnings=[])
    graph = graph_rule_result(state)
    return ValidationResult(errors=errors + graph.errors, warnings=graph.warnings)


def graph_rule_result(state: dict[str, Any]) -> ValidationResult:
    """The rules the schema cannot state: ids, references, endpoint types, goal policy, and the belief math.

    Every value has its JSON type here (`state_type_errors` is empty), so the sections are lists
    of objects and every id is a string; a required field may still be missing.
    """
    errors: list[str] = []
    warnings: list[str] = []
    nodes_raw = state.get("nodes", [])
    edges_raw = state.get("edges", [])

    node_ids: set[str] = set()
    for i, node in enumerate(nodes_raw):
        node_id = node.get("id")
        node_type = node.get("type")
        if not node_id:
            errors.append(f"nodes[{i}] missing string id")
        elif node_id in node_ids:
            errors.append(f"duplicate node id {node_id}")
        else:
            node_ids.add(node_id)
        # A removed type is already named with its replacement by authored_field_errors.
        if node_type not in NODE_TYPES and node_type not in REMOVED_NODE_TYPES:
            errors.append(f"node {node_id or i} invalid type {node_type!r}")
        if "not_run" in node:
            if node_type != "test":
                errors.append(f"node {node_id or i} not_run is only valid on test nodes")
            elif not node["not_run"].strip():
                errors.append(f"node {node_id or i} not_run must be a non-empty reason")
        if node.get("exhausted") is True and not str(node.get("exhaustion_reason") or "").strip():
            warnings.append(f"node {node_id or i} exhausted=true should include exhaustion_reason")
    nodes_by_id = {str(node.get("id")): node for node in nodes_raw if isinstance(node.get("id"), str)}
    goals = goal_ids(state)
    seen_goal_groups: set[str] = set()
    for i, group in enumerate(state.get("goal_groups", [])):
        group_id = group.get("id")
        if not group_id:
            errors.append(f"goal_groups[{i}] missing string id")
        elif group_id in seen_goal_groups:
            errors.append(f"duplicate goal group id {group_id}")
        else:
            seen_goal_groups.add(group_id)
        group_goals = group.get("goals")
        if not group_goals:
            errors.append(f"goal_groups[{i}].goals must be a non-empty list")
        else:
            for j, goal_id in enumerate(group_goals):
                if goal_id not in goals:
                    errors.append(f"goal_groups[{i}].goals[{j}] references missing goal {goal_id!r}")
    errors.extend(exclusive_set_errors(state.get("exclusive_sets", []), nodes_by_id))
    goal_policy = state.get("goal_policy", {})
    for key in ("accepted_goals", "preferred_goals", "optional_goals"):
        if key in goal_policy:
            values = goal_policy[key]
            if not values:
                errors.append(f"goal_policy.{key} must be a non-empty list when present")
                continue
            for i, goal_id in enumerate(values):
                if goal_id not in goals:
                    errors.append(f"goal_policy.{key}[{i}] references missing goal {goal_id!r}")
    accepted_goals = accepted_goal_ids(state)
    goals_by_id = {node.get("id"): node for node in nodes_raw if node.get("type") == "goal"}
    seen_edge_ids: set[str] = set()
    for i, edge in enumerate(edges_raw):
        if edge_id(edge) in seen_edge_ids:
            errors.append(f"edge {edge_id(edge)} exists more than once: one edge per ordered pair; change it with update_edges")
        seen_edge_ids.add(edge_id(edge))
        src = edge.get("from")
        dst = edge.get("to")
        edge_type = edge.get("type")
        if src not in node_ids:
            errors.append(f"edge {i} references missing from node {src!r}")
        if dst not in node_ids:
            errors.append(f"edge {i} references missing to node {dst!r}")
        # A removed type is already named with its replacement by authored_field_errors.
        if edge_type not in EDGE_TYPES and edge_type not in REMOVED_EDGE_TYPES:
            errors.append(f"edge {i} invalid type {edge_type!r}")
        ignored_legacy_fields = sorted(field for field in ("hard", "mode", "strength") if field in edge)
        if ignored_legacy_fields:
            warnings.append(
                f"edge {i} uses ignored legacy field(s) {', '.join(ignored_legacy_fields)}; use score on supports/contradicts edges"
            )
        src_type = nodes_by_id.get(src, {}).get("type")
        dst_type = nodes_by_id.get(dst, {}).get("type")
        # A removed node type is already named with its replacement; endpoint rules on it would
        # only suggest other fixes, such as retyping the edge.
        if src_type in REMOVED_NODE_TYPES or dst_type in REMOVED_NODE_TYPES:
            continue
        if edge_type == "answers":
            errors.extend(answers_edge_errors(edge, src_type, dst_type, goals_by_id, accepted_goals))
        if edge_type == "yields" and "not_run" in nodes_by_id.get(src, {}):
            errors.append(f"edge {i} gives not_run test {src} a result observation {dst}; a check that ran is not not_run")
        # Only something seen may rule a claim out: an inference that vetoed another claim
        # would turn one mistaken conclusion into an unrecoverable one.
        if edge_type == RULED_OUT_EDGE_TYPE and (src_type != "observation" or dst_type != "hypothesis"):
            errors.append(f"edge {i} rules_out must connect observation -> hypothesis; {src} -> {dst} is {src_type} -> {dst_type}")
        if edge_type == "premise_of" and (src_type not in BELIEF_NODE_TYPES or dst_type not in PREMISE_TARGET_TYPES):
            errors.append(
                f"edge {i} premise_of must connect an observation or hypothesis to a hypothesis; "
                f"{src} -> {dst} is {src_type} -> {dst_type}{premise_endpoint_hint(src_type, dst_type)}"
            )
        if edge_type == "yields" and (src_type != "test" or dst_type not in RESULT_NODE_TYPES):
            errors.append(f"edge {i} yields must connect a test to the observation of its result; {src} -> {dst} is {src_type} -> {dst_type}")
        if src_type == "goal" and dst_type == "goal" and edge_type != "requires":
            errors.append(f"edge {i} goal -> goal must use requires; {src} -> {dst} uses {edge_type!r}")
        if src_type == "hypothesis" and dst_type == "goal" and edge_type != "answers":
            errors.append(f"edge {edge_id(edge)} uses {edge_type!r} from hypothesis to goal; answers is the only edge from a hypothesis to a goal")
        if src_type == "constraint" and dst_type == "goal" and edge_type == "requires":
            errors.append(
                f"edge {i} has constraint {src} requires goal {dst}; reverse direction to goal requires constraint"
            )

    seen_factor_ids: set[str] = set()
    for i, factor in enumerate(state.get("factors", [])):
        factor_id = factor.get("id")
        if not factor_id:
            errors.append(f"factors[{i}] missing string id")
        elif factor_id in seen_factor_ids:
            errors.append(f"duplicate factor id {factor_id}")
        else:
            seen_factor_ids.add(factor_id)
    errors.extend(resolve_edge_groups(state)[1])

    for candidate_id, goal_targets in sorted(candidate_goal_targets(state).items()):
        candidate_text = str(nodes_by_id.get(candidate_id, {}).get("text") or "").lower()
        answers_non_epistemic_goal = any(
            not any(marker in str(goals_by_id.get(goal_id, {}).get("text") or "").lower() for marker in EPISTEMIC_GOAL_MARKERS)
            for goal_id in goal_targets
        )
        if answers_non_epistemic_goal and any(marker in candidate_text for marker in UNRESOLVED_OUTCOME_MARKERS):
            warnings.append(
                f"hypothesis {candidate_id} answers a goal but looks like an unresolved outcome, not an answer; keep it as a blocker "
                "without an answers edge and claim no answer, unless the goal is explicitly epistemic"
            )
        if not goal_targets & accepted_goals:
            errors.append(
                f"hypothesis {candidate_id} answers only {', '.join(sorted(goal_targets))}, outside goal_policy.accepted_goals; "
                "accept the goal by listing it there or by a requires edge from an accepted goal, or point the answers edge at an accepted goal"
            )

    try:
        assert_acyclic_premise_dependencies({goal_id: sorted(subs) for goal_id, subs in goal_requirements(state).items()})
    except ValueError as exc:
        errors.append(f"goal requires {exc}")

    try:
        # Computed only to catch inputs the belief math rejects, such as an evidence cycle.
        node_effective_truth_costs(state)
    except ScoredDeductionError as exc:
        errors.append(str(exc))
    except RemovedInputError:
        pass  # authored_field_errors already named the replacement
    except Exception as exc:  # validation should report instead of throwing
        errors.append(f"belief computation failed: {exc}")

    return ValidationResult(errors=errors, warnings=warnings)
