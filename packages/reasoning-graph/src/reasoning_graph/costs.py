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


def likelihood_probability_from_value(value: Any, field: str) -> float:
    return require_probability(value, field)


def likelihood_ratio_from_likelihood(likelihood: Any, field: str = "likelihood") -> float:
    if not isinstance(likelihood, dict):
        raise ValueError(f"{field} must be an object")
    if_target_true = likelihood_probability_from_value(
        likelihood.get("if_target_true"), f"{field}.if_target_true"
    )
    if_target_false = likelihood_probability_from_value(
        likelihood.get("if_target_false"), f"{field}.if_target_false"
    )
    likelihood_ratio = if_target_true / if_target_false
    if not math.isfinite(likelihood_ratio):
        raise ValueError(f"{field} ratio must be finite, got {likelihood_ratio}")
    return likelihood_ratio


def likelihood_ratio_from_edge(edge: dict[str, Any]) -> float:
    """Ratio of an evidence edge: its score, or the default, through the table."""
    for field in REMOVED_EDGE_SCORE_FIELDS:
        if field in edge:
            raise ValueError(removed_score_field_message(f"edge {edge.get('id')}", field))
    ratio = EVIDENCE_SCORE_RATIO[require_score(edge.get("score", DEFAULT_EVIDENCE_SCORE))]
    return 1 / ratio if edge.get("type") == "contradicts" else ratio


def factor_label(source: str, index: int) -> str:
    return f"{source}[{index}]"


def iter_numeric_factor_specs(state: dict[str, Any]) -> Iterable[tuple[str, int, dict[str, Any]]]:
    factors = state.get("factors", [])
    if factors is None:
        factors = []
    if not isinstance(factors, list):
        raise ValueError("factors must be a list when present")
    for index, factor in enumerate(factors):
        if not isinstance(factor, dict):
            raise ValueError(f"factors[{index}] must be object")
        if "effective_truth_cost" in factor:
            raise ValueError(f"factors[{index}] must not set effective_truth_cost; it is computed from aggregation")
        if "likelihood_ratio" in factor:
            raise ValueError(
                f"factors[{index}] must not set likelihood_ratio directly; use aggregation.if_target_true and aggregation.if_target_false"
            )
        aggregation = factor.get("aggregation")
        if isinstance(aggregation, dict) and "likelihood_ratio" in aggregation:
            raise ValueError(
                f"factors[{index}].aggregation must not set likelihood_ratio directly; use if_target_true and if_target_false"
            )
        yield "factors", index, factor

def joint_probability_cost_from_factor(factor: dict[str, Any], label: str) -> float:
    aggregation = factor.get("aggregation")
    if not isinstance(aggregation, dict):
        raise ValueError(f"{label}.aggregation must be an object")
    if aggregation.get("kind") != "joint_probability":
        raise ValueError(f"{label}.aggregation.kind must be 'joint_probability' for leads_to factors")
    if "probability" not in aggregation:
        raise ValueError(f"{label}.aggregation.probability missing")
    return probability_cost(aggregation.get("probability"), f"{label}.aggregation.probability")


def likelihood_ratio_from_factor(factor: dict[str, Any], label: str) -> float:
    aggregation = factor.get("aggregation")
    if not isinstance(aggregation, dict):
        raise ValueError(f"{label}.aggregation must be an object")
    if aggregation.get("kind") != "likelihood":
        raise ValueError(f"{label}.aggregation.kind must be 'likelihood' for supports/contradicts factors")
    return likelihood_ratio_from_likelihood(aggregation, f"{label}.aggregation")


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
    """One odds-space update on a claim: an ungrouped edge or a likelihood factor."""

    log_likelihood_ratio: float
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class TruthInputs:
    """Validated graph inputs to belief propagation, shared by cost and grounding checks."""

    nodes: dict[str, dict[str, Any]]
    premise_sources: dict[str, list[str]]
    premise_group_costs: dict[str, list[float]]
    grouped_premise_sources: dict[str, set[str]]
    # Per-node updates after factor grouping, in edge-then-factor order.
    evidence_updates: dict[str, list[EvidenceUpdate]]
    # Claims whose belief comes from a claim premise or a calibrated premise factor.
    premise_backed_nodes: set[str]


def truth_inputs(state: dict[str, Any]) -> TruthInputs:
    """Collect premises and likelihood updates, validating edges and factors."""

    nodes = by_id(state.get("nodes", []), "node")
    premise_sources: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    likelihood_edges: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
    likelihood_source_sets: dict[tuple[str, str], set[str]] = {}

    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = edge.get("type") or edge.get("label")
        # Validate every evidence edge, including those the belief walk never reaches.
        if edge_type in EVIDENCE_EDGE_TYPES:
            likelihood_ratio_from_edge(edge)
        src = edge.get("from")
        dst = edge.get("to")
        if not isinstance(src, str) or not isinstance(dst, str) or src not in nodes or dst not in nodes:
            continue
        if edge_type == "leads_to":
            premise_sources.setdefault(dst, []).append(src)
        elif edge_type in EVIDENCE_EDGE_TYPES:
            likelihood_source_sets.setdefault((dst, str(edge_type)), set()).add(src)
            likelihood_edges.setdefault(dst, []).append(edge)

    # Evidence from a non-observation source is scaled by that source's belief,
    # so it is a truth dependency just like a premise.
    truth_dependencies = {node_id: list(sources) for node_id, sources in premise_sources.items()}
    for target, edges in likelihood_edges.items():
        truth_dependencies[target] += [str(edge["from"]) for edge in edges if nodes[str(edge["from"])].get("type") != "observation"]
    assert_acyclic_premise_dependencies(truth_dependencies)

    premise_group_costs: dict[str, list[float]] = {node_id: [] for node_id in nodes}
    grouped_premise_sources: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    grouped_likelihood_sources: dict[tuple[str, str], set[str]] = {}
    factor_updates: dict[str, list[EvidenceUpdate]] = {node_id: [] for node_id in nodes}
    premise_source_sets = {node_id: set(sources) for node_id, sources in premise_sources.items()}
    for source, index, factor in iter_numeric_factor_specs(state):
        label = factor_label(source, index)
        relation = factor.get("relation")
        if relation not in FACTOR_RELATIONS:
            raise ValueError(f"{label}.relation must be one of {sorted(FACTOR_RELATIONS)}, got {relation!r}")
        target = factor.get("target")
        if not isinstance(target, str) or target not in nodes:
            raise ValueError(f"{label}.target references missing node {target!r}")
        inputs = factor.get("inputs")
        input_label = "inputs"
        if not isinstance(inputs, list) or len(inputs) < 2:
            raise ValueError(f"{label}.{input_label} must be a list of at least two node ids")
        input_ids: list[str] = []
        for input_index, input_id in enumerate(inputs):
            if not isinstance(input_id, str) or not input_id:
                raise ValueError(f"{label}.{input_label}[{input_index}] must be a non-empty string")
            if input_id not in nodes:
                raise ValueError(f"{label}.{input_label}[{input_index}] references missing node {input_id!r}")
            if input_id == target:
                raise ValueError(f"{label} must not include target {target!r} as an input")
            if relation == "leads_to" and input_id not in premise_source_sets.get(target, set()):
                raise ValueError(f"{label} input {input_id!r} must have a leads_to edge to target {target!r}")
            if relation in {"supports", "contradicts"} and input_id not in likelihood_source_sets.get((target, relation), set()):
                raise ValueError(f"{label} input {input_id!r} must have a {relation} edge to target {target!r}")
            input_ids.append(input_id)
        if len(set(input_ids)) != len(input_ids):
            raise ValueError(f"{label}.{input_label} must not contain duplicates")

        if relation == "leads_to":
            overlap = grouped_premise_sources[target].intersection(input_ids)
            if overlap:
                joined = ", ".join(sorted(overlap))
                raise ValueError(f"leads_to factors for target {target!r} overlap on input(s) {joined}")
            premise_group_costs[target].append(joint_probability_cost_from_factor(factor, label))
            grouped_premise_sources[target].update(input_ids)
            continue

        grouped_key = (target, relation)
        grouped_for_relation = grouped_likelihood_sources.setdefault(grouped_key, set())
        overlap = grouped_for_relation.intersection(input_ids)
        if overlap:
            joined = ", ".join(sorted(overlap))
            raise ValueError(f"{relation} factors for target {target!r} overlap on input(s) {joined}")
        likelihood_ratio = likelihood_ratio_from_factor(factor, label)
        if relation == "supports" and likelihood_ratio <= 1:
            raise ValueError(f"{label} supports likelihood ratio must be > 1")
        if relation == "contradicts" and likelihood_ratio >= 1:
            raise ValueError(f"{label} contradicts likelihood ratio must be in (0, 1)")
        factor_updates[target].append(EvidenceUpdate(math.log(likelihood_ratio), tuple(input_ids)))
        grouped_for_relation.update(input_ids)

    evidence_updates: dict[str, list[EvidenceUpdate]] = {}
    for node_id in nodes:
        ungrouped_likelihood_edges = [
            edge
            for edge in likelihood_edges.get(node_id, [])
            if str(edge.get("from"))
            not in grouped_likelihood_sources.get((node_id, str(edge.get("type") or edge.get("label"))), set())
        ]
        # Factors are explicit non-independent bundles; their calibrated
        # likelihood replaces grouped member updates.
        updates = [EvidenceUpdate(math.log(likelihood_ratio_from_edge(edge)), (str(edge["from"]),)) for edge in ungrouped_likelihood_edges]
        updates += factor_updates.get(node_id, [])
        if updates:
            evidence_updates[node_id] = updates

    return TruthInputs(
        nodes=nodes,
        premise_sources=premise_sources,
        premise_group_costs=premise_group_costs,
        grouped_premise_sources=grouped_premise_sources,
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
    cost to the target's base belief. Top-level `leads_to` factors replace
    grouped member costs with a calibrated joint_probability.
    Incoming `supports`/`contradicts` edges update that base belief in odds
    space; grouped likelihood factors replace correlated member updates.
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
        # Factor inputs are treated as jointly true with independent beliefs.
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
        grouped_sources = inputs.grouped_premise_sources.get(node_id, set())
        ungrouped_source_cost = sum(
            effective_cost(source_id)
            for source_id in inputs.premise_sources.get(node_id, [])
            if source_id not in grouped_sources
        )
        # Factors are explicit non-independent bundles; their calibrated
        # aggregation replaces grouped member costs.
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
