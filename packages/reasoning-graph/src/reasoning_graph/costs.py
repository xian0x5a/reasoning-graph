"""Truth cost, belief, and evidence-update helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .models import BELIEF_NODE_TYPES, FACTOR_RELATIONS
from .state import by_id
from .utils import require_finite_float, require_non_negative_float


# Scores are tiers, not calibrated numbers: authored decimals claimed a precision that the
# #36 runs showed does not exist. One table per kind turns a tier into the number the
# belief math needs (issue #37).
CLAIM_SCORE_PROBABILITY = {1: 0.1, 2: 0.3, 3: 0.5, 4: 0.7, 5: 0.9}
# The ratios agents wrote most often. `contradicts` uses the reciprocal.
EVIDENCE_SCORE_RATIO = {1: 1.2, 2: 1.5, 3: 2.0, 4: 3.0, 5: 5.0}
DEFAULT_CLAIM_SCORE = {"observation": 5, "hypothesis": 3, "candidate_solution": 3}
DEFAULT_EVIDENCE_SCORE = 3
EVIDENCE_EDGE_TYPES = ("supports", "contradicts")

# Fields the 1-5 `score` replaced. `posterior` let an author overrule the graph's own
# evidence (issue #37); belief always follows the recorded inputs.
REMOVED_NODE_SCORE_FIELDS = ("prior", "confidence", "probability", "posterior")
REMOVED_EDGE_SCORE_FIELDS = ("likelihood", "likelihood_ratio")
# A group names its edges, which already carry the relation, the target, and the sources.
REMOVED_GROUP_FIELDS = {
    "relation": "list the grouped edge ids in edges",
    "target": "list the grouped edge ids in edges",
    "inputs": "list the grouped edge ids in edges",
    "aggregation": "use score, an integer from 1 to 5",
    "reason": "use note",
}


def require_score(value: Any, field: str = "score") -> int:
    # bool is an int subclass; True must not pass as score 1. JSON Schema counts 3.0 as an integer.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in CLAIM_SCORE_PROBABILITY:
        raise ValueError(f"{field} must be an integer from 1 to 5, got {value!r}")
    return int(value)


def removed_score_field_message(owner: str, field: str) -> str:
    return f"{owner}: {field} was removed; use score, an integer from 1 to 5, or omit it to take the default"


def require_probability(value: Any, field: str = "probability") -> float:
    probability = require_finite_float(value, field)
    if not 0 < probability <= 1:
        raise ValueError(f"{field} must be in (0, 1], got {probability}")
    return probability


def probability_cost(value: Any, field: str = "probability") -> float:
    return -math.log(require_probability(value, field))


def probability_from_value(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= probability <= 1:
        return probability
    return None


def evidence_ratio(score: Any, relation: str, field: str = "score") -> float:
    ratio = EVIDENCE_SCORE_RATIO[require_score(score, field)]
    return 1 / ratio if relation == "contradicts" else ratio


def likelihood_ratio_from_edge(edge: dict[str, Any]) -> float:
    """Ratio of an evidence edge: its score, or the default, through the table."""
    for field in REMOVED_EDGE_SCORE_FIELDS:
        if field in edge:
            raise ValueError(removed_score_field_message(f"edge {edge.get('id')}", field))
    return evidence_ratio(edge.get("score", DEFAULT_EVIDENCE_SCORE), str(edge.get("type")))


@dataclass(frozen=True)
class EdgeGroup:
    """Edges into one target that count once, at one combined score."""

    group_id: str
    relation: str
    target: str
    edge_ids: tuple[str, ...]
    sources: tuple[str, ...]
    score: int


def resolve_edge_groups(state: dict[str, Any]) -> tuple[list[EdgeGroup], list[str]]:
    """Resolve each `factors` record against the edges it names; return the valid groups and every error."""

    factors = state.get("factors") or []
    if not isinstance(factors, list):
        return [], ["factors must be a list when present"]
    edges = {
        edge["id"]: edge
        for edge in state.get("edges", [])
        if isinstance(edge, dict) and isinstance(edge.get("id"), str)
    }
    groups: list[EdgeGroup] = []
    errors: list[str] = []
    grouped_by: dict[str, str] = {}
    for index, factor in enumerate(factors):
        label = f"factors[{index}]"
        if not isinstance(factor, dict):
            errors.append(f"{label} must be object")
            continue
        name = factor["id"] if isinstance(factor.get("id"), str) and factor.get("id") else label
        found = [f"{label}: {field} was removed; {replacement}" for field, replacement in REMOVED_GROUP_FIELDS.items() if field in factor]

        edge_ids = factor.get("edges")
        if (
            not isinstance(edge_ids, list)
            or not all(isinstance(edge_id, str) and edge_id for edge_id in edge_ids)
            or len(set(edge_ids)) < 2
            or len(set(edge_ids)) != len(edge_ids)
        ):
            found.append(f"{label}.edges must list at least two different edge ids")
            edge_ids = []
        found.extend(f"{label}.edges references missing edge {edge_id!r}" for edge_id in edge_ids if edge_id not in edges)
        members = [edges[edge_id] for edge_id in edge_ids if edge_id in edges]
        relations = sorted({str(member.get("type")) for member in members})
        targets = sorted({str(member.get("to")) for member in members})
        if len(relations) > 1:
            found.append(f"{label}.edges must share one type, got {', '.join(relations)}")
        elif relations and relations[0] not in FACTOR_RELATIONS:
            found.append(f"{label}.edges must be leads_to, supports, or contradicts edges, got {relations[0]}")
        if len(targets) > 1:
            found.append(f"{label}.edges must share one target, got {', '.join(targets)}")
        for member in members:
            member_id = member["id"]
            if member_id in grouped_by:
                found.append(f"{label}: edge {member_id} is already grouped by {grouped_by[member_id]}")
            grouped_by.setdefault(member_id, name)
            if "score" in member:
                found.append(f"{label}: edge {member_id} is grouped by {name} and must not carry its own score; the group's score is the one number")

        if "score" not in factor:
            found.append(f"{label}.score is required: the combined score of the grouped edges, an integer from 1 to 5")
        else:
            try:
                require_score(factor["score"], f"{label}.score")
            except ValueError as exc:
                found.append(str(exc))

        errors.extend(found)
        if not found:
            groups.append(
                EdgeGroup(
                    group_id=name,
                    relation=relations[0],
                    target=targets[0],
                    edge_ids=tuple(edge_ids),
                    sources=tuple(str(member.get("from")) for member in members),
                    score=int(factor["score"]),
                )
            )
    return groups, errors


def probability_from_log_odds(log_odds: float) -> float:
    if log_odds >= 0:
        if log_odds > 745:
            return 1.0
        denominator = 1.0 + math.exp(-log_odds)
        return 1.0 / denominator
    if log_odds < -745:
        return 0.0
    odds = math.exp(log_odds)
    return odds / (1.0 + odds)


def log_odds_from_probability(probability: float) -> float:
    if probability >= 1.0:
        return math.inf
    if probability <= 0.0:
        return -math.inf
    return math.log(probability / (1.0 - probability))


def probability_from_cost(cost: float) -> float:
    if cost <= 0:
        return 1.0
    if cost > 745:
        return 0.0
    return math.exp(-cost)


def truth_cost_from_log_odds(log_odds: float) -> float:
    """Compute finite truth cost without underflowing tiny probabilities to zero."""

    try:
        log_odds = float(log_odds)
    except (TypeError, ValueError):
        raise ValueError(f"log odds must be numeric, got {log_odds!r}")
    if math.isnan(log_odds) or log_odds == -math.inf:
        raise ValueError(f"log odds must be finite or positive certainty, got {log_odds}")
    if log_odds == math.inf:
        return 0.0
    if log_odds >= 0:
        return math.log1p(math.exp(-log_odds))
    return -log_odds + math.log1p(math.exp(log_odds))


def node_belief_label(node: dict[str, Any], effective_truth_cost: float) -> str:
    """Label a claim's effective belief; objectives/actions have no truth score."""
    if node.get("type") not in BELIEF_NODE_TYPES:
        return ""
    return f"belief {probability_from_cost(effective_truth_cost):.3g}"


def node_local_truth_cost(node: dict[str, Any] | None, premise_backed: bool = False) -> float:
    """Cost of a claim's own score, or of its type default when nothing else gives it a belief.

    A premise-backed claim without a score adds no factor: a default on every derived claim
    would halve belief at each step of a chain. Goals, constraints, and tests cost nothing.
    """

    if not node:
        return 0.0
    # Direct cost consumers do not necessarily run validation first; reject removed
    # inputs rather than silently computing without them.
    for field in REMOVED_NODE_SCORE_FIELDS:
        if field in node:
            raise ValueError(removed_score_field_message(f"node {node.get('id')}", field))
    if node.get("type") not in BELIEF_NODE_TYPES:
        return 0.0
    if "score" in node:
        return probability_cost(CLAIM_SCORE_PROBABILITY[require_score(node["score"])])
    if premise_backed:
        return 0.0
    return probability_cost(CLAIM_SCORE_PROBABILITY[DEFAULT_CLAIM_SCORE[str(node["type"])]])


def assert_acyclic_premise_dependencies(premise_sources: dict[str, list[str]]) -> None:
    """Reject dependency cycles before any factor cost replacement."""

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise ValueError(f"cycle in truth dependency graph at {node_id}")
        visiting.add(node_id)
        for source_id in premise_sources.get(node_id, []):
            visit(source_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in premise_sources:
        visit(node_id)


@dataclass(frozen=True)
class EvidenceUpdate:
    """One odds-space update on a claim: an ungrouped edge or a group of edges."""

    log_likelihood_ratio: float
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class TruthInputs:
    """Validated graph inputs to belief propagation, shared by cost and grounding checks."""

    nodes: dict[str, dict[str, Any]]
    premise_sources: dict[str, list[str]]
    ungrouped_premise_sources: dict[str, list[str]]
    premise_group_costs: dict[str, list[float]]
    # Per-node updates after grouping, in edge-then-group order.
    evidence_updates: dict[str, list[EvidenceUpdate]]
    # Claims whose belief comes from a claim premise or a premise group.
    premise_backed_nodes: set[str]


def truth_inputs(state: dict[str, Any]) -> TruthInputs:
    """Collect premises and evidence updates, validating edges and groups."""

    nodes = by_id(state.get("nodes", []), "node")
    groups, group_errors = resolve_edge_groups(state)
    if group_errors:
        raise ValueError(group_errors[0])
    grouped_edge_ids = {edge_id for group in groups for edge_id in group.edge_ids}

    premise_sources: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    ungrouped_premise_sources: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    # Evidence from a non-observation source is scaled by that source's belief,
    # so it is a truth dependency just like a premise.
    truth_dependencies: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    evidence_updates: dict[str, list[EvidenceUpdate]] = {}

    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = edge.get("type") or edge.get("label")
        # Validate every evidence edge, including those the belief walk never reaches.
        if edge_type in EVIDENCE_EDGE_TYPES:
            likelihood_ratio = likelihood_ratio_from_edge(edge)
        src = edge.get("from")
        dst = edge.get("to")
        if not isinstance(src, str) or not isinstance(dst, str) or src not in nodes or dst not in nodes:
            continue
        grouped = edge.get("id") in grouped_edge_ids
        if edge_type == "leads_to":
            premise_sources[dst].append(src)
            truth_dependencies[dst].append(src)
            if not grouped:
                ungrouped_premise_sources[dst].append(src)
        elif edge_type in EVIDENCE_EDGE_TYPES:
            if nodes[src].get("type") != "observation":
                truth_dependencies[dst].append(src)
            if not grouped:
                evidence_updates.setdefault(dst, []).append(EvidenceUpdate(math.log(likelihood_ratio), (src,)))
    assert_acyclic_premise_dependencies(truth_dependencies)

    # A group is an explicit bundle of dependent edges; its score replaces theirs.
    premise_group_costs: dict[str, list[float]] = {node_id: [] for node_id in nodes}
    for group in groups:
        if group.target not in nodes or any(source not in nodes for source in group.sources):
            continue
        if group.relation == "leads_to":
            premise_group_costs[group.target].append(probability_cost(CLAIM_SCORE_PROBABILITY[group.score]))
        else:
            ratio = evidence_ratio(group.score, group.relation)
            evidence_updates.setdefault(group.target, []).append(EvidenceUpdate(math.log(ratio), group.sources))

    return TruthInputs(
        nodes=nodes,
        premise_sources=premise_sources,
        ungrouped_premise_sources=ungrouped_premise_sources,
        premise_group_costs=premise_group_costs,
        evidence_updates=evidence_updates,
        premise_backed_nodes={
            node_id
            for node_id in nodes
            if premise_group_costs[node_id]
            or any(nodes[source].get("type") in BELIEF_NODE_TYPES for source in premise_sources[node_id])
        },
    )


def evidence_grounded_node_ids(inputs: TruthInputs) -> set[str]:
    """Claims whose belief is earned from observations rather than hand-set scores.

    Observations are the base. A claim is grounded when every one of its
    `leads_to` premises is grounded, or when its evidence favors it (net
    likelihood ratio > 1) counting supporting updates only from grounded sources
    and contradicting updates from any source: unbacked support cannot lift a
    claim, but unbacked doubt still weighs. A score never grounds a
    claim. Evidence cycles between claims are rejected by `truth_inputs`.
    """

    grounded = {node_id for node_id, node in inputs.nodes.items() if node.get("type") == "observation"}

    def is_grounded_by(node_id: str) -> bool:
        premises = inputs.premise_sources.get(node_id, [])
        if premises and all(premise in grounded for premise in premises):
            return True
        net_log_likelihood_ratio = sum(
            update.log_likelihood_ratio
            for update in inputs.evidence_updates.get(node_id, [])
            if update.log_likelihood_ratio < 0 or all(source in grounded for source in update.source_ids)
        )
        return net_log_likelihood_ratio > 0

    changed = True
    while changed:
        newly_grounded = {node_id for node_id in inputs.nodes if node_id not in grounded and is_grounded_by(node_id)}
        grounded |= newly_grounded
        changed = bool(newly_grounded)
    return grounded


def node_effective_truth_costs(state: dict[str, Any]) -> dict[str, float]:
    """Compute effective node truth costs from premises and likelihood updates.

    Incoming `leads_to` edges are required premises and contribute source truth
    cost to the target's base belief. A `leads_to` group replaces its members'
    costs with the joint probability of its score.
    Incoming `supports`/`contradicts` edges update that base belief in odds
    space; a group replaces its members' updates with one at its score.
    Computed beliefs are returned as costs; `score` is never rewritten.
    """

    inputs = truth_inputs(state)
    evidence_grounded = evidence_grounded_node_ids(inputs)
    memo: dict[str, float] = {}
    visiting: set[str] = set()

    def effective_log_likelihood_ratio(update: EvidenceUpdate) -> float:
        # Observation ratios already include source reliability. A claim is only as
        # strong as its belief b: ratio r acts as 1 + b * (r - 1), treating a false
        # source as uninformative. Unbacked support is ignored; doubt always weighs.
        claim_sources = [source for source in update.source_ids if inputs.nodes[source].get("type") != "observation"]
        if not claim_sources:
            return update.log_likelihood_ratio
        if update.log_likelihood_ratio > 0 and not all(source in evidence_grounded for source in update.source_ids):
            return 0.0
        # Group sources are treated as jointly true with independent beliefs.
        source_belief = math.exp(-sum(effective_cost(source) for source in claim_sources))
        return math.log1p(source_belief * math.expm1(update.log_likelihood_ratio))

    def effective_cost(node_id: str) -> float:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            raise ValueError(f"cycle in truth dependency graph at {node_id}")
        node = inputs.nodes.get(node_id)
        if not node:
            return 0.0

        visiting.add(node_id)
        local_cost = node_local_truth_cost(node, node_id in inputs.premise_backed_nodes)
        ungrouped_source_cost = sum(effective_cost(source_id) for source_id in inputs.ungrouped_premise_sources.get(node_id, []))
        premise_cost = sum(inputs.premise_group_costs.get(node_id, [])) + ungrouped_source_cost
        base_cost = local_cost + premise_cost
        updates = inputs.evidence_updates.get(node_id, [])
        if updates:
            # Stay in log space: exp(-base_cost) can underflow for valid inherited
            # beliefs. expm1 also preserves precision near explicit certainty.
            log_odds = -base_cost - math.log(-math.expm1(-base_cost)) if base_cost > 0 else math.inf
            for update in updates:
                log_odds += effective_log_likelihood_ratio(update)
            cost = truth_cost_from_log_odds(log_odds)
        else:
            cost = base_cost
        cost = require_non_negative_float(cost, f"node {node_id} truth cost")
        visiting.remove(node_id)
        memo[node_id] = cost
        return cost

    for node_id in inputs.nodes:
        effective_cost(node_id)
    return memo


def claim_beliefs(state: dict[str, Any]) -> dict[str, float]:
    """Computed belief per claim node, rounded like ranked candidate beliefs."""
    truth_costs = node_effective_truth_costs(state)
    return {
        node["id"]: round(probability_from_cost(truth_costs[node["id"]]), 6)
        for node in state.get("nodes", [])
        if node.get("type") in BELIEF_NODE_TYPES
    }
