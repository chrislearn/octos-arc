"""Non-blocking generation policy and first-level requirement phase contracts.

These helpers deliberately do not inspect test pass rates when deciding which
requirement may be implemented. A test is evidence about a product, not a
dependency of writing its source.
"""
from __future__ import annotations

import hashlib
import json

from requirement_order import dependency_graph, flatten_atomic


LOW_SIGNAL = (
    "navigation clicks", "not reachable within", "search depth", "could not reach",
    "locator resolved to", "timed out waiting for", "timeout exceeded",
)


def classify_observation(message: str, *, source: str = "derived", reliable: bool = False,
                         core: bool = False, minor: bool = False) -> tuple[str, str]:
    """Return (impact, confidence); a generated assertion alone never proves F0/F1."""
    lower = message.lower()
    if source == "runtime":
        if any(marker in lower for marker in ("spec failed to load", "test load", "browser closed",
                                             "worker was killed", "time budget exhausted", "provider unavailable",
                                             "playwright produced no report", "playwright could not start",
                                             "unreadable playwright report", "playwright run exceeded")):
            return "I", "measurement_unavailable"
        return "F0", "observed_runtime"  # acceptance reports runtime only after build/start fails
    if source == "infrastructure" or any(marker in lower for marker in
       ("browser closed", "worker was killed", "econnrefused", "provider unavailable")):
        return "I", "measurement_unavailable"
    if source == "derived" and (not reliable or any(marker in lower for marker in LOW_SIGNAL)):
        return "T", "unverified_test"
    if source in {"official", "api_reproduced", "derived"} and reliable and core and (
            ("403" in lower and "200" in lower and any(word in lower for word in
              ("unauthorized", "forbidden", "permission", "access")))
            or any(marker in lower for marker in ("cross-user access confirmed", "unauthorized deletion confirmed"))):
        return "F0", "observed_security"
    return ("F2" if minor and not core else "F1"), ("observed_behavior" if reliable else "unverified_test")


def first_level_phases(tree: dict, design: dict | None = None) -> dict:
    """Extract category coordination contracts without a new model request.

    Leaves have exactly one top-level owner. Cross-category cycles remain edges
    for interface planning; they are never scheduling gates.
    """
    leaves = flatten_atomic(tree)
    known = {str(node.get("id")) for node in leaves}
    children = [child for child in tree.get("children") or [] if isinstance(child, dict)]
    if not children:
        children = [tree]
    categories = []
    ownership = {}
    for child in children:
        leaf_ids = [str(node.get("id")) for node in flatten_atomic(child) if str(node.get("id")) in known]
        if not leaf_ids:
            continue
        phase_id = str(child.get("id") or "root")
        for leaf_id in leaf_ids:
            if leaf_id in ownership:
                raise ValueError(f"atomic requirement {leaf_id} belongs to two phases")
            ownership[leaf_id] = phase_id
        categories.append({"id": phase_id, "name": str(child.get("name") or child.get("description") or phase_id),
                           "leaves": leaf_ids, "artifacts": [], "cross_dependencies": []})
    if set(ownership) != known:
        raise ValueError("phase contracts omit atomic requirements")
    by_phase = {phase["id"]: phase for phase in categories}
    graph = dependency_graph(tree)
    for leaf_id, deps in graph.items():
        phase = by_phase[ownership[leaf_id]]
        for dep in deps:
            if ownership.get(dep) != phase["id"]:
                edge = {"leaf": leaf_id, "requires": dep, "phase": ownership.get(dep)}
                if edge not in phase["cross_dependencies"]:
                    phase["cross_dependencies"].append(edge)
    warnings = []
    artifact_owners = {}
    if isinstance(design, dict):
        for kind in ("routes", "pages", "modules", "contracts"):
            for artifact in design.get(kind) or []:
                if not isinstance(artifact, dict):
                    continue
                refs = [str(item) for item in artifact.get("requirements") or []]
                owning_phases = [phase["id"] for phase in categories if set(refs) & set(phase["leaves"])]
                if not owning_phases:
                    continue
                key = (kind, str(artifact.get("method") or ""), str(artifact.get("path") or ""))
                if not key[2]:
                    key = (kind, key[1], str(artifact.get("purpose") or ""))
                requested_owner = str(artifact.get("owner") or "")
                owner = (ownership.get(requested_owner) or requested_owner) if requested_owner else owning_phases[0]
                if owner not in by_phase:
                    warnings.append(f"unknown owner {owner} for {kind} {key[2]}")
                    owner = owning_phases[0]
                if key in artifact_owners and artifact_owners[key] != owner:
                    warnings.append(f"conflicting owner for {kind} {key[2]}: {artifact_owners[key]} vs {owner}")
                    owner = artifact_owners[key]
                artifact_owners[key] = owner
                for phase in categories:
                    if set(refs) & set(phase["leaves"]):
                        # Keep only bounded, auditable ownership fields, not a
                        # duplicate copy of the whole application design.
                        phase["artifacts"].append({"kind": kind, "path": str(artifact.get("path") or "")[:160],
                                                   "method": str(artifact.get("method") or "")[:16],
                                                   "purpose": str(artifact.get("purpose") or "")[:200],
                                                   "owner": owner,
                                                   "requirements": sorted(set(refs) & set(phase["leaves"]))})
    source = json.dumps({"tree": tree, "design": design}, sort_keys=True, ensure_ascii=False)
    return {"version": 1, "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "phases": categories, "leaf_phase": ownership, "warnings": warnings}


def phase_context(plan: dict | None, leaf_ids: list[str], limit: int = 3500) -> str:
    if not isinstance(plan, dict):
        return ""
    wanted = {plan.get("leaf_phase", {}).get(str(leaf_id)) for leaf_id in leaf_ids}
    lines = ["FIRST-LEVEL PHASE CONTRACT: coordinate shared state and interfaces; do not wait for test passes."]
    for phase in plan.get("phases") or []:
        if phase.get("id") not in wanted:
            continue
        lines.append(f"{phase['id']} {phase['name']}: leaves {', '.join(phase['leaves'])}.")
        for item in phase.get("artifacts", [])[:10]:
            lines.append(f"  {item['kind']} {item['method']} {item['path']} (owner {item['owner']}): {item['purpose']}")
        for edge in phase.get("cross_dependencies", [])[:12]:
            lines.append(f"  {edge['leaf']} uses {edge['requires']} from {edge['phase']}; agree interface before use.")
    return "\n".join(lines)[:limit] + "\n"
