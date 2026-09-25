"""Truth/search cost and evidence-update helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .models import BELIEF_NODE_TYPES, FACTOR_RELATIONS, LEGACY_COST_COMPONENT_ALIASES, PROBE_LIKE_MARKERS, SEARCH_COST_COMPONENTS
from .state import by_id
from .utils import require_finite_float, require_non_negative_float


NEUTRAL_UPDATE_PRIOR = 0.5
DEFAULT_ESTIMATED_REMAINING_WEIGHT = 1.0
ESTIMATED_REMAINING_COST_FIELD = "estimated_remaining_cost"

# Posterior is an authored override, not a cache of computed belief. Listings
# keep the local prior visible first even when a posterior overrides it.
NODE_TRUTH_PROBABILITY_PRECEDENCE = ("posterior", "prior")
NODE_SCORE_FIELDS = ("prior", "posterior")


def require_probability(value: Any, field: str = "probability") -> float:
    probability = require_finite_float(value, field)
    if not 0 < probability <= 1:
        raise ValueError(f"{field} must be in (0, 1], got {probability}")
    return probability


def probability_cost(value: Any, field: str = "probability") -> float:
    return -math.log(require_probability(value, field))


def uncertainty_cost_from_prior(prior: Any) -> float:
    return probability_cost(prior, "prior")


def text_looks_probe_like(*values: Any) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    return any(marker in text for marker in PROBE_LIKE_MARKERS)


def item_has_explicit_effort_budget(item: dict[str, Any]) -> bool:
    components = item.get("cost_components") if isinstance(item.get("cost_components"), dict) else {}
    has_cost_component = any(
        key in components
        for key in ("effort_budget", "resource_budget", "compute_budget")
    )
    budget = item.get("budget")
    has_budget_metadata = isinstance(budget, dict) and any(
        key in budget
        for key in ("max_attempts", "max_seconds", "max_items", "max_sources", "stop_after")
    )
    return has_cost_component and has_budget_metadata


def probability_from_value(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= probability <= 1:
        return probability
    return None


def likelihood_ratio_from_value(value: Any, field: str = "likelihood_ratio") -> float:
    likelihood_ratio = require_finite_float(value, field)
    if likelihood_ratio <= 0:
        raise ValueError(f"{field} must be > 0, got {likelihood_ratio}")
    return likelihood_ratio


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
    if "likelihood" in edge and "likelihood_ratio" in edge:
        raise ValueError("edge must not set both likelihood and likelihood_ratio")
    if "likelihood" in edge:
        return likelihood_ratio_from_likelihood(edge.get("likelihood"))
    return likelihood_ratio_from_value(edge.get("likelihood_ratio"))


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


def node_has_score(node: dict[str, Any] | None) -> bool:
    return bool(node) and any(field in node for field in NODE_TRUTH_PROBABILITY_PRECEDENCE)


def node_belief_label(node: dict[str, Any], effective_truth_cost: float) -> str:
    """Label a claim's effective belief; objectives/actions have no truth score."""
    if node.get("type") not in BELIEF_NODE_TYPES:
        return ""
    return f"belief {probability_from_cost(effective_truth_cost):.3g}"


def node_local_truth_cost(node: dict[str, Any] | None, *, include_posterior: bool = True) -> float:
    """Cost of the local prior, or the explicit posterior override when enabled."""

    if not node:
        return 0.0
    # Direct cost consumers do not necessarily run schema validation first.
    # Reject obsolete/output-only inputs rather than silently changing belief.
    for field in ("confidence", "probability"):
        if field in node:
            raise ValueError(f"node {node.get('id')}: {field} is not supported; use prior for local probability")
    if "belief" in node:
        raise ValueError(f"node {node.get('id')}: belief is computed output; use posterior for an explicit override")
    fields = NODE_TRUTH_PROBABILITY_PRECEDENCE if include_posterior else ("prior",)
    for field in fields:
        if field in node:
            return probability_cost(node[field], field)
    return 0.0


def node_truth_cost(node: dict[str, Any] | None) -> float:
    """Local truth cost for a node, preserving the historical public helper.

    `prior` is the local starting-probability factor, including observation or
    inference reliability. Missing local inputs contribute no additional penalty;
    the effective-cost engine checks for a belief source.
    """

    return node_local_truth_cost(node)


def nodes_with_belief_sources(state: dict[str, Any]) -> set[str]:
    """Find claims grounded by a local score or a calibrated premise factor.

    Only leads_to propagates a starting belief. Likelihood ratios describe a
    relative update, and scoreless objectives/actions do not establish certainty.
    Reachability is independent of numerical cost, including an exact zero.
    """
    nodes = by_id(state.get("nodes", []), "node")
    grounded = {node_id for node_id, node in nodes.items() if node_has_score(node)}
    for factor in state.get("factors", []) or []:
        if not isinstance(factor, dict) or factor.get("relation") != "leads_to":
            continue
        target = factor.get("target")
        aggregation = factor.get("aggregation")
        if (
            isinstance(target, str)
            and target in nodes
            and isinstance(aggregation, dict)
            and aggregation.get("kind") == "joint_probability"
        ):
            grounded.add(target)

    dependents: dict[str, list[str]] = {}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict) or (edge.get("type") or edge.get("label")) != "leads_to":
            continue
        source, target = edge.get("from"), edge.get("to")
        if isinstance(source, str) and isinstance(target, str) and source in nodes and target in nodes:
            dependents.setdefault(source, []).append(target)

    pending = list(grounded)
    while pending:
        for target in dependents.get(pending.pop(), []):
            if target not in grounded:
                grounded.add(target)
                pending.append(target)
    return grounded


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
    belief_source_nodes: set[str]


def truth_inputs(state: dict[str, Any]) -> TruthInputs:
    """Collect premises and likelihood updates, validating edges and factors."""

    nodes = by_id(state.get("nodes", []), "node")
    premise_sources: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    likelihood_edges: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
    likelihood_source_sets: dict[tuple[str, str], set[str]] = {}

    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        # Validate every edge before posterior short-circuiting can hide malformed updates.
        if "likelihood" in edge or "likelihood_ratio" in edge:
            likelihood_ratio_from_edge(edge)
        edge_type = edge.get("type") or edge.get("label")
        src = edge.get("from")
        dst = edge.get("to")
        if not isinstance(src, str) or not isinstance(dst, str) or src not in nodes or dst not in nodes:
            continue
        if edge_type == "leads_to":
            premise_sources.setdefault(dst, []).append(src)
        elif edge_type in {"supports", "contradicts"}:
            likelihood_source_sets.setdefault((dst, str(edge_type)), set()).add(src)
            if "likelihood_ratio" in edge or "likelihood" in edge:
                likelihood_edges.setdefault(dst, []).append(edge)

    # Evidence from a non-observation source is scaled by that source's belief,
    # so it is a truth dependency just like a premise.
    truth_dependencies = {node_id: list(sources) for node_id, sources in premise_sources.items()}
    for target, edges in likelihood_edges.items():
        truth_dependencies[target] += [str(edge["from"]) for edge in edges if nodes[str(edge["from"])].get("type") != "observation"]
    assert_acyclic_premise_dependencies(truth_dependencies)
    grounded_nodes = nodes_with_belief_sources(state)

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
        belief_source_nodes=grounded_nodes,
    )


def evidence_grounded_node_ids(inputs: TruthInputs) -> set[str]:
    """Claims whose belief is earned from observations rather than hand-set scores.

    Observations are the base. A claim is grounded when every one of its
    `leads_to` premises is grounded, or when its evidence favors it (net
    likelihood ratio > 1) counting supporting updates only from grounded sources
    and contradicting updates from any source: unbacked support cannot lift a
    claim, but unbacked doubt still weighs. Priors and posteriors never ground a
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
    Incoming `supports`/`contradicts` edges with `likelihood` or
    `likelihood_ratio` update that base belief in odds space; grouped likelihood
    factors replace correlated member likelihood updates.
    Explicit node `posterior` is treated as already-calibrated and wins over
    graph-derived updates to avoid double counting. Computed beliefs are returned
    as costs; neither `prior` nor `posterior` is written back to nodes.
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
        if "posterior" in node:
            cost = node_local_truth_cost(node)
            memo[node_id] = cost
            return cost

        visiting.add(node_id)
        local_cost = node_local_truth_cost(node, include_posterior=False)
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
        if node_id not in inputs.belief_source_nodes and (node.get("type") in BELIEF_NODE_TYPES or updates):
            # Unknown claims must not become free certainty, even when the cost
            # engine is called without validation. A grounded zero stays certain.
            base_cost = probability_cost(NEUTRAL_UPDATE_PRIOR)
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


def search_policy_estimated_remaining_weight(state: dict[str, Any]) -> float:
    policy = state.get("search_policy", {})
    if policy is None:
        policy = {}
    if not isinstance(policy, dict):
        raise ValueError("search_policy must be an object when present")
    return require_non_negative_float(
        policy.get("estimated_remaining_weight", DEFAULT_ESTIMATED_REMAINING_WEIGHT),
        "search_policy.estimated_remaining_weight",
    )


def estimated_remaining_cost_for_item(item: dict[str, Any]) -> tuple[float, bool]:
    if ESTIMATED_REMAINING_COST_FIELD not in item:
        return 0.0, False
    estimated_remaining_cost = require_non_negative_float(
        item.get(ESTIMATED_REMAINING_COST_FIELD),
        f"frontier item {item.get('id')} estimated_remaining_cost",
    )
    return estimated_remaining_cost, True


def cost_components_for_item(
    item: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    node_truth_costs: dict[str, float],
) -> dict[str, float]:
    explicit = item.get("cost_components") or item.get("cost") or {}
    if explicit is None:
        explicit = {}
    if not isinstance(explicit, dict):
        raise ValueError(f"frontier item {item.get('id')} cost_components must be object")

    components: dict[str, float] = {}
    for raw_key, raw_value in explicit.items():
        key = str(raw_key)
        if key == ESTIMATED_REMAINING_COST_FIELD:
            raise ValueError(f"frontier item {item.get('id')} cost_components.{key} must be top-level")
        key = LEGACY_COST_COMPONENT_ALIASES.get(key, key)
        if key not in SEARCH_COST_COMPONENTS:
            continue
        if raw_value is None or raw_value == "auto":
            continue
        components[key] = require_non_negative_float(
            raw_value,
            f"frontier item {item.get('id')} component {raw_key}",
        )

    node_id = str(item.get("node"))
    node = nodes.get(node_id)
    if "truth" not in components:
        components["truth"] = node_truth_costs.get(node_id, node_truth_cost(node))

    for key in SEARCH_COST_COMPONENTS:
        components.setdefault(key, 0.0)
    return components


def compute_costs(state: dict[str, Any]) -> dict[str, Any]:
    nodes = by_id(state.get("nodes", []), "node")
    node_truth_costs = node_effective_truth_costs(state)
    frontier = state.get("frontier", [])
    estimated_remaining_weight = search_policy_estimated_remaining_weight(state)

    for item in frontier:
        if not isinstance(item, dict):
            continue
        if "path_cost" in item:
            raise ValueError(f"frontier item {item.get('id')} uses rejected legacy field path_cost; use search_cost/cost_components")
        if "cost_components" not in item and "cost" not in item and "step_cost" in item:
            node_id = str(item.get("node"))
            if "step_truth_cost" in item:
                truth_cost = require_non_negative_float(
                    item["step_truth_cost"],
                    f"frontier item {item.get('id')} step_truth_cost",
                )
            else:
                truth_cost = node_truth_costs.get(node_id, node_truth_cost(nodes.get(node_id)))
            truth_cost = require_non_negative_float(
                truth_cost,
                f"frontier item {item.get('id')} step_truth_cost",
            )
            legacy_search_cost = require_non_negative_float(
                item["step_cost"],
                f"frontier item {item.get('id')} step_cost",
            )
            work_cost = max(0.0, legacy_search_cost - truth_cost)
            item["cost_components"] = {
                "truth": round(truth_cost, 6),
                "verification": round(work_cost, 6),
                "effort_budget": 0.0,
                "reasoning_complexity": 0.0,
                "constraint_tension": 0.0,
            }
        else:
            # Keep the authored spec (including truth: "auto") untouched: persisting the
            # resolved number here would freeze the item's priority against later evidence.
            components = cost_components_for_item(item, nodes, node_truth_costs)
            truth_cost = components["truth"]
            work_cost = sum(value for key, value in components.items() if key != "truth")

        truth_cost = require_non_negative_float(truth_cost, f"frontier item {item.get('id')} truth cost")
        work_cost = require_non_negative_float(work_cost, f"frontier item {item.get('id')} work cost")
        base_search_cost = require_non_negative_float(
            truth_cost + work_cost,
            f"frontier item {item.get('id')} base search cost",
        )
        estimated_remaining_cost, has_estimated_remaining_cost = estimated_remaining_cost_for_item(item)
        heuristic_cost = require_non_negative_float(
            estimated_remaining_weight * estimated_remaining_cost,
            f"frontier item {item.get('id')} heuristic cost",
        )
        search_cost = require_non_negative_float(
            base_search_cost + heuristic_cost,
            f"frontier item {item.get('id')} search cost",
        )

        item["truth_cost"] = round(truth_cost, 6)
        item["work_cost"] = round(work_cost, 6)
        item["base_search_cost"] = round(base_search_cost, 6)
        if has_estimated_remaining_cost:
            item["estimated_remaining_cost"] = round(estimated_remaining_cost, 6)
            item["heuristic_cost"] = round(heuristic_cost, 6)
        else:
            item.pop("heuristic_cost", None)
        item["step_truth_cost"] = round(truth_cost, 6)
        item["step_cost"] = round(search_cost, 6)
        item["search_cost"] = round(search_cost, 6)
    return state


def sorted_frontier(state: dict[str, Any]) -> dict[str, Any]:
    compute_costs(state)
    state["frontier"] = sorted(
        state.get("frontier", []),
        key=lambda item: (float(item.get("search_cost", math.inf)), str(item.get("id", ""))),
    )
    return state


def sorted_frontier_items(state: dict[str, Any], item_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    selected = items.values() if item_ids is None else (items[item_id] for item_id in item_ids if item_id in items)
    return sorted(selected, key=lambda item: (float(item.get("search_cost", math.inf)), str(item.get("id", ""))))
