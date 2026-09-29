"""Deterministic render identities shared by graph output formats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def safe_render_id(raw: str) -> str:
    """Return Mermaid/SVG-safe base identity for a raw graph ID."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(raw))
    if not cleaned:
        cleaned = "N"
    if cleaned[0].isdigit():
        cleaned = "N_" + cleaned
    return cleaned


def _allocate_identities(candidates: list[tuple[tuple[str, str], str]]) -> dict[tuple[str, str], str]:
    by_base: dict[str, list[tuple[str, str]]] = {}
    for key, base in candidates:
        by_base.setdefault(base, []).append(key)

    # Reserve every base first. This lets each collision group retain its base,
    # even when another group's numeric suffix would otherwise consume it.
    reserved_bases = set(by_base)
    allocated: dict[tuple[str, str], str] = {}
    used: set[str] = set()
    for base in sorted(by_base):
        keys = sorted(by_base[base])
        for ordinal, key in enumerate(keys, 1):
            candidate = base if ordinal == 1 else f"{base}_{ordinal}"
            while candidate in used or (candidate in reserved_bases and candidate != base):
                ordinal += 1
                candidate = f"{base}_{ordinal}"
            allocated[key] = candidate
            used.add(candidate)
    return allocated


@dataclass(frozen=True)
class RenderIdentityMap:
    """One state-wide identity map used by Mermaid, SVG, HTML, and browser JS."""

    node_ids: dict[str, str]
    factor_ids: dict[str, str]

    def node(self, raw_id: str) -> str | None:
        return self.node_ids.get(str(raw_id))

    def factor(self, raw_id: str) -> str | None:
        return self.factor_ids.get(str(raw_id))

    def node_anchor(self, raw_id: str, prefix: str = "details") -> str:
        identity = self.node(raw_id) or safe_render_id(str(raw_id))
        return f"{prefix}-{identity}"


def render_identity_map(state: dict[str, Any]) -> RenderIdentityMap:
    """Allocate stable, collision-free identities from all valid graph records.

    Sorting by namespace and raw ID makes suffixes independent of input list order.
    Node and factor identities share one allocation namespace so SVG/Mermaid IDs
    cannot collide across either record type.
    """
    candidates: list[tuple[tuple[str, str], str]] = []
    node_raw_ids: list[str] = []
    for node in state.get("nodes", []) if isinstance(state.get("nodes", []), list) else []:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        raw_id = node["id"]
        node_raw_ids.append(raw_id)
        candidates.append((("node", raw_id), safe_render_id(raw_id)))

    factor_raw_ids: list[str] = []
    for factor in state.get("factors", []) if isinstance(state.get("factors", []), list) else []:
        if not isinstance(factor, dict) or not isinstance(factor.get("id"), str):
            continue
        raw_id = factor["id"]
        factor_raw_ids.append(raw_id)
        candidates.append((("factor", raw_id), safe_render_id(f"factor:{raw_id}")))

    allocated = _allocate_identities(candidates)
    return RenderIdentityMap(
        node_ids={raw_id: allocated[("node", raw_id)] for raw_id in node_raw_ids},
        factor_ids={raw_id: allocated[("factor", raw_id)] for raw_id in factor_raw_ids},
    )


def html_anchor(raw: str, prefix: str = "details") -> str:
    """An HTML id for page parts that are not graph records, such as a section or an svg marker."""
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(raw))
    cleaned = cleaned.strip("-") or "node"
    return f"{prefix}-{cleaned}"
