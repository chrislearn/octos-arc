"""Requirement-grounded shared contracts and cross-module diagnostics (no task names)."""
from __future__ import annotations
import hashlib
import json
import re


def requirement_index(tree) -> dict[str, str]:
    result = {}
    def visit(node):
        if not isinstance(node, dict):
            return
        if node.get("id"):
            result[str(node["id"])] = str(node.get("description") or "") + "\n" + json.dumps(node.get("scenarios", []), ensure_ascii=False)
        for child in node.get("children") or []:
            visit(child)
    visit(tree)
    return result


def official_status(case: dict, requirements: dict[str, str] | None) -> bool:
    """A model cannot grant itself an exception by labelling a number official."""
    witness = case.get("source")
    if not isinstance(witness, dict) or not requirements:
        return False
    quote = witness.get("quote")
    raw = requirements.get(str(witness.get("requirement_id")), "")
    return bool(isinstance(quote, str) and quote and quote in raw and re.search(
        r"\b(?:HTTP(?:\s+status(?:\s+code)?)?|status(?:\s+code)?)\s*(?:of\s+|[:=]\s*)?"
        + re.escape(str(case.get("status"))) + r"\b", quote, re.I))


def contract_manifest(tree, design: dict | None) -> dict:
    """Raw requirements remain authoritative; a design is a versioned proposal."""
    design = design or {}
    requirements = requirement_index(tree)
    entities = []
    for name, fields in (design.get("data_model") or {}).items():
        entities.append({"name": name, "fields": fields,
                         "identity": "unresolved", "storage": "unresolved"})
    contracts = design.get("domain_contracts") or []
    by_name = {c.get("entity"): c for c in contracts if isinstance(c, dict)}
    for entity in entities:
        entity.update(by_name.get(entity["name"], {}))
    gaps = []
    for entity in entities:
        for key in ("identity", "storage", "producers", "consumers"):
            if not entity.get(key) or entity[key] == "unresolved":
                gaps.append(f"{entity['name']}: {key} not specified")
    for contract in contracts:
        for req in contract.get("requirements", []) if isinstance(contract, dict) else []:
            if req not in requirements:
                gaps.append(f"unknown requirement reference: {req}")
    canonical = json.dumps({"requirements": requirements, "design": design}, sort_keys=True, ensure_ascii=False)
    return {"version": 1, "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "requirements": requirements, "entities": entities, "commands": design.get("commands", []),
            "routes": design.get("routes", []), "gaps": gaps, "status": "proposed_unverified"}


def source_contract_advisories(sources: dict[str, str]) -> list[dict]:
    """Find split module bindings; require runtime confirmation, never block dynamic code."""
    bindings = {}
    for path, source in sources.items():
        for match in re.finditer(r"const\s*\{([^}]+)\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)", source):
            module = match[2]
            if not module.startswith("."):
                continue
            import posixpath
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), module))
            for name in match[1].split(","):
                name = name.strip()
                if re.fullmatch(r"\w+", name):
                    bindings.setdefault(name, {}).setdefault(resolved, []).append(path)
    return [{"kind": "split_binding", "symbol": name, "providers": modules,
             "status": "suspected", "next": "trace writes through normalization to consumers and restart"}
            for name, modules in sorted(bindings.items()) if len(modules) > 1]


DOMAIN_GUIDANCE = """
SHARED BUSINESS CONTRACT: distinguish session IDs, account IDs and resource IDs; never substitute IDs by field name.
For shared entities add domain_contracts [{entity, identity, storage, producers, consumers, requirements}].
Use one authoritative store across write, normalization and read paths; verify create -> list -> detail -> mutate -> reload.
Add commands [{name, requirements, preconditions, effects, rejected_effects, state_transitions, permissions, persistence}].
All input surfaces share the same validation/command; reject whole multi-item operations or apply all, never silently clip.
Keep raw text separate from numeric/display values when required, including empty records and leading/trailing characters.
Resource selection/history is keyed by stable resource ID; failed writes retain usable UI and drafts; undo touches its own range.
Every grant/revoke and private-resource read (including legacy/subresource paths) uses the same requirement-derived policy.
Required seeds need valid references and real initial states. Refresh/restart must preserve edits and not resurrect deleted seeds.
State-version approvals must be invalidated after edits; merges preserve both sides according to the required conflict semantics.
Cross-store atomicity needs an aggregate or transactional store, not sequential single-file writes. These are contracts to verify,
not extra product features. Cite explicit HTTP exceptions using source {requirement_id, quote}; never invent an official quote.
"""
