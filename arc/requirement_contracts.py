"""Deterministic verification contracts for runs without acceptance specs.

These contracts are a lossless projection of the requirement scenarios, not
model-authored tests.  They give every generation path the same GIVEN/WHEN/THEN
checklist and make the weaker verification basis explicit when ARC-Bench does
not mount Playwright specs.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Mapping


CONTRACT_VERSION = 2
_QUOTED = re.compile(r"[\u201c\u201d]\s*([^\u201c\u201d\n]+?)\s*[\u201c\u201d]|\"([^\"\n]+?)\"|`([^`\n]+?)`")
_ROLE_BEFORE = re.compile(
    r"\b(button|link|textbox|input|checkbox|radio|combobox|dialog|menu|tab|heading|select)s?\b"
    r"[^.,;:\n\u201c\u201d\"]{0,35}(?:\b(?:named|labeled|labelled)\b\s*)?$",
    re.IGNORECASE,
)
_ROLE_AFTER = re.compile(
    r"^\s*(button|link|textbox|input|checkbox|radio|combobox|dialog|menu|tab|heading|select)s?\b",
    re.IGNORECASE,
)
_MESSAGE_CONTEXT = re.compile(
    r"\b(?:message|error|displays?|displayed|shows?|shown|visible\s+text(?:\s+value)?)\b"
    r"[^.!?;:\n\u201c\u201d\"]{0,60}$",
    re.IGNORECASE,
)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
_INITIAL_DATA_CONTEXT = re.compile(
    r"\b(?:the\s+system\s+(?:contains|has|includes)|system\s+(?:contains|has|includes)|"
    r"pre[- ]?(?:loaded|populated)|seeded|seed\s+data|"
    r"seed\s+(?:records?|items?|accounts?|users?|projects?|repositories|entries|fixtures?)|"
    r"has\s+been\s+initialized|"
    r"existing\s+[^.!?\n]{0,80}\b(?:named|titled)|"
    r"with\s+(?:valid\s+)?initial\s+(?:content|description|metadata|tags?|value|data)|"
    r"default\s+(?:label|record|account|category|tag|template|option|value|data))\b|"
    r"(?:系统(?:包含|已有)|预置|种子数据|初始数据|默认(?:标签|记录|账户|分类|选项|值)|已有[^。！？\n]{0,80}(?:名为|标题为))",
    re.IGNORECASE,
)
_SCENARIO_INPUT_CONTEXT = re.compile(
    r"\bfor\s+(?:a\s+)?(?:successful|failed|invalid)?\s*"
    r"(?:create|update|change|edit|submit|search|login|attempt|request)\b|"
    r"\b(?:the\s+)?(?:user|tester|they)\s+(?:enter(?:ed|s|ing)?|input(?:ted|s|ting)|"
    r"provide(?:d|s|ing)?|submit(?:ted|s|ting)?|select(?:ed|s|ing)?|choose|chosen|"
    r"type(?:d|s|ing)?)\b|"
    r"\b(?:values?|fields?|credentials?|text|names?)\s+(?:are\s+|is\s+)?"
    r"(?:entered|input|provided|submitted|selected|chosen|typed)\b|"
    r"(?:用于|供)[^。！？\n]{0,40}(?:创建|更新|修改|提交|搜索|登录|尝试)|"
    r"(?:输入|填写|提供|提交|选择)(?:值|内容|数据)?",
    re.IGNORECASE,
)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = re.sub(r"\s+", " ", str(value)).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _node_text(node: Mapping) -> str:
    parts = [str(node.get("name") or ""), str(node.get("description") or "")]
    for scenario in node.get("scenarios") or []:
        parts.append(str(scenario.get("name") or ""))
        parts.extend(str(step.get("content") or "") for step in scenario.get("steps") or []
                     if isinstance(step, Mapping))
    return "\n".join(parts)


def _quoted_terms(text: str) -> list[str]:
    return _unique(next(value for value in match.groups() if value is not None)
                   for match in _QUOTED.finditer(text))


def _reference_images(text: str) -> list[str]:
    paths = []
    for match in _MARKDOWN_IMAGE.finditer(text):
        value = match.group(1).strip()
        if value.startswith("<") and value.endswith(">"):
            value = value[1:-1].strip()
        # Markdown permits an optional quoted title after the URL. Requirement
        # assets use relative paths; keep remote references too, but never infer
        # that merely naming one means its pixels were inspected.
        value = re.sub(r'''\s+["'][^"']*["']\s*$''', "", value).strip()
        if value:
            paths.append(value)
    return _unique(paths)


def _ui_bindings(text: str) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _QUOTED.finditer(text):
        name = next(value for value in match.groups() if value is not None).strip()
        # Accept only a role directly adjacent to the quote, on either side:
        # "button named X", "button X", or "X link".  A loose look-behind
        # misclassifies the next quoted error in list-heavy requirements.
        prefix = text[max(0, match.start() - 80):match.start()]
        suffix = text[match.end():match.end() + 32]
        role_match = _ROLE_BEFORE.search(prefix) or _ROLE_AFTER.search(suffix)
        if not role_match:
            continue
        role = role_match.group(1).lower()
        role = {"input": "textbox", "select": "combobox"}.get(role, role)
        key = (role, name)
        if key not in seen:
            seen.add(key)
            bindings.append({"role": role, "name": name})
    return bindings


def _exact_messages(text: str) -> list[str]:
    messages: list[str] = []
    ui_names = {item["name"] for item in _ui_bindings(text)}
    list_until = -1
    for match in _QUOTED.finditer(text):
        value = next(value for value in match.groups() if value is not None).strip()
        context = text[max(0, match.start() - 100):match.start()]
        begins_list = bool(_MESSAGE_CONTEXT.search(context))
        if begins_list:
            ending = re.search(r"[.!?;\n]", text[match.end():])
            list_until = match.end() + (ending.start() if ending else len(text))
        if value not in ui_names and (begins_list or match.start() <= list_until):
            messages.append(value)
    return _unique(messages)


def _dimensions(text: str) -> list[str]:
    low = text.lower()
    checks = []
    if any(word in low for word in ("refresh", "reload", "reopen", "persist", "restart")):
        checks.append("persistence/reload")
    if any(word in low for word in ("invalid", "reject", "error", "must not", "does not", "failure")):
        checks.append("negative path/no mutation")
    if any(word in low for word in ("permission", "authorized", "owner", "signed-in", "session")):
        checks.append("authorization/session isolation")
    if "atomic" in low:
        checks.append("atomic state transition")
    if any(word in low for word in ("accessible", "labeled", "labelled", "role", "keyboard")):
        checks.append("accessible role/name")
    return checks


def _sentences(text: str) -> list[str]:
    """Split prose only at sentence boundaries; keep every selected clause verbatim."""
    return _unique(re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", str(text or "")))


def _required_initial_data(node: Mapping) -> list[str]:
    """Explicit fresh-store prerequisites, without treating every GIVEN as seed.

    A scenario precondition such as "the user is on the home page" is still
    preserved in `cases.given`, but it is not data the application may invent.
    Only wording that explicitly declares existing/default/seeded system state
    is promoted into this additional, reviewable constraint.
    """
    candidates = _sentences(str(node.get("description") or ""))
    for scenario in node.get("scenarios") or []:
        phase = ""
        for step in scenario.get("steps") or []:
            if not isinstance(step, Mapping):
                continue
            keyword = str(step.get("keyword") or "").strip().upper()
            if keyword in {"GIVEN", "WHEN", "THEN"}:
                phase = keyword
            elif keyword not in {"AND", "BUT"}:
                phase = ""
            if phase == "GIVEN":
                candidates.extend(_sentences(str(step.get("content") or "")))
    return _unique(value for value in candidates
                   if _INITIAL_DATA_CONTEXT.search(value) and not _SCENARIO_INPUT_CONTEXT.search(value))


def compile_contract(node: Mapping) -> dict:
    """Compile one ATOMIC YAML node without adding inferred behaviour."""
    text = _node_text(node)
    cases = []
    for scenario in node.get("scenarios") or []:
        phases: dict[str, list[str]] = {"given": [], "when": [], "then": [], "other": []}
        current = "other"
        for step in scenario.get("steps") or []:
            if not isinstance(step, Mapping):
                continue
            keyword = str(step.get("keyword") or "").strip().upper()
            if keyword in {"GIVEN", "WHEN", "THEN"}:
                current = keyword.lower()
            elif keyword not in {"AND", "BUT"}:
                current = "other"
            content = re.sub(r"\s+", " ", str(step.get("content") or "")).strip()
            if content:
                phases[current].append(content)
        cases.append({"name": str(scenario.get("name") or "scenario"), **phases})
    payload = {
        "id": str(node.get("id") or ""),
        "name": str(node.get("name") or ""),
        "description": str(node.get("description") or "").strip(),
        "dependencies": [str(value) for value in node.get("dependencies") or []],
        "cases": cases,
        "ui": _ui_bindings(text),
        "exact_messages": _exact_messages(text),
        "quoted_terms": _quoted_terms(text),
        "required_initial_data": _required_initial_data(node),
        "reference_images": _reference_images(text),
        "verification_dimensions": _dimensions(text),
    }
    payload["source_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return payload


def compile_contracts(nodes: Iterable[Mapping]) -> dict:
    compiled = [compile_contract(node) for node in nodes]
    return {
        "version": CONTRACT_VERSION,
        "basis": "deterministic projection of requirements.yaml; not official acceptance tests",
        "nodes": compiled,
    }


def save_contracts(path: Path, contracts: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contracts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_node(contract: Mapping, include_steps: bool) -> str:
    lines = [f"[{contract.get('id')}] {contract.get('name', '')}"]
    deps = contract.get("dependencies") or []
    if deps:
        lines.append("Prerequisites: " + ", ".join(map(str, deps)))
    ui = contract.get("ui") or []
    if ui:
        lines.append("Exact role/name bindings: " + "; ".join(
            f"{item.get('role')}={json.dumps(item.get('name'), ensure_ascii=False)}" for item in ui))
    messages = contract.get("exact_messages") or []
    if messages:
        lines.append("Exact visible messages/values: " + "; ".join(json.dumps(v, ensure_ascii=False) for v in messages))
    already_classified = {str(item.get("name")) for item in ui} | {str(value) for value in messages}
    terms = [value for value in contract.get("quoted_terms") or [] if str(value) not in already_classified]
    if terms:
        lines.append("Other quoted terms (preserve spelling; use their YAML context): "
                     + "; ".join(json.dumps(v, ensure_ascii=False) for v in terms))
    initial = contract.get("required_initial_data") or []
    if initial:
        lines.append("Required fresh-store data/state (verbatim; initialize only a new store, never reseed a "
                     "deleted record):")
        lines.extend("  INITIAL: " + str(value) for value in initial)
    dims = contract.get("verification_dimensions") or []
    if dims:
        lines.append("Required check dimensions: " + ", ".join(map(str, dims)))
    images = contract.get("reference_images") or []
    if images:
        lines.append("Reference images declared by requirements (visual evidence; inspect with an image-capable "
                     "tool/model when available): " + ", ".join(map(str, images)))
    for case in contract.get("cases") or []:
        lines.append("CASE: " + str(case.get("name") or "scenario"))
        if include_steps:
            for phase in ("given", "when", "then", "other"):
                values = case.get(phase) or []
                for value in values:
                    lines.append(f"  {phase.upper()}: {value}")
        else:
            counts = ", ".join(f"{phase.upper()}={len(case.get(phase) or [])}"
                               for phase in ("given", "when", "then") if case.get(phase))
            lines.append("  Execute the YAML steps in order and verify every outcome"
                         + (f" ({counts})." if counts else "."))
    return "\n".join(lines)


def render_contracts(contracts: Mapping, node_ids: Iterable[str] | None = None,
                     max_chars: int = 30_000, include_steps: bool = True,
                     require_all: bool = False) -> str:
    """Render whole contract blocks.

    `require_all` is for an active node/wave: return every selected scenario so
    the caller can split the wave using the real size instead of silently
    planning from a truncated contract. Suite-wide final review remains bounded
    and points to the complete JSON artifact when later nodes do not fit.
    """
    wanted = set(map(str, node_ids)) if node_ids is not None else None
    selected = [node for node in contracts.get("nodes") or []
                if wanted is None or str(node.get("id")) in wanted]
    header = (
        "DERIVED REQUIREMENT VERIFICATION CONTRACT (not official Playwright tests).\n"
        "This checklist is generated deterministically from requirements.yaml; it adds no fixtures, selectors, "
        "routes, or behaviour. Treat the YAML semantics as authoritative. Implement and exercise every GIVEN/WHEN/THEN "
        "flow, including negative, permission, persistence, and reload outcomes. Do not claim official-test coverage. "
        "The full requirement descriptions and structured steps remain in .arc/requirement-contracts.json.\n"
    )
    chunks = [header]
    included = 0
    for node in selected:
        block = _render_node(node, include_steps) + "\n"
        if not require_all and sum(map(len, chunks)) + len(block) > max_chars:
            break
        chunks.append(block)
        included += 1
    if included < len(selected):
        chunks.append(f"[contract prompt omitted {len(selected) - included} complete node(s) to stay within budget; "
                      "their full contracts are in .arc/requirement-contracts.json]\n")
    return "\n".join(chunks)


def source_literal_gaps(contracts: Mapping, sources: Mapping[str, str], max_items: int = 16) -> list[str]:
    """Return bounded advisory gaps for exact, non-parameterized UI literals.

    Absence from source is not proof of a failure (a value may be composed at
    runtime), so callers must present these as inspection hints, never verdicts.
    """
    source = "\n".join(str(value) for value in sources.values())
    gaps: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for node in contracts.get("nodes") or []:
        node_id = str(node.get("id") or "")
        candidates = [(f"{item.get('role')} name", str(item.get("name") or ""))
                      for item in node.get("ui") or []]
        candidates += [("visible message/value", str(value)) for value in node.get("exact_messages") or []]
        for kind, value in candidates:
            if (not value or len(value) > 140 or re.search(r"[<>{}]", value)
                    or (kind, value, node_id) in seen):
                continue
            seen.add((kind, value, node_id))
            if value not in source:
                gaps.append(f"REQ_LITERAL {node_id}: {kind} {json.dumps(value, ensure_ascii=False)} is not a source literal")
                if len(gaps) >= max_items:
                    return gaps
    return gaps


def source_seed_gaps(contracts: Mapping, sources: Mapping[str, str],
                     node_ids: Iterable[str] | None = None, max_items: int = 12) -> list[str]:
    """Find explicit seed identifiers/values absent from the application tree.

    This does not infer records from ordinary GIVEN navigation/setup. Only
    `required_initial_data` promoted from explicit requirement wording is
    considered. Quoted literals are strong traceability anchors, while the
    complete verbatim constraint remains available to the review turn.
    """
    wanted = set(map(str, node_ids)) if node_ids is not None else None
    source = "\n".join(str(value) for value in sources.values())
    gaps: list[str] = []
    seen: set[tuple[str, str]] = set()
    for node in contracts.get("nodes") or []:
        node_id = str(node.get("id") or "")
        if wanted is not None and node_id not in wanted:
            continue
        for constraint in node.get("required_initial_data") or []:
            for value in _quoted_terms(str(constraint)):
                key = (node_id, value)
                if key in seen or len(value) < 2 or re.search(r"[<>{}]", value):
                    continue
                seen.add(key)
                if value not in source:
                    gaps.append(
                        f"SEED_DATA {node_id}: required initial literal "
                        f"{json.dumps(value, ensure_ascii=False)} is absent from application sources; "
                        f"inspect the fresh-store owner for: {constraint}"
                    )
                    if len(gaps) >= max_items:
                        return gaps
    return gaps


def seed_gaps_by_node(contracts: Mapping, sources: Mapping[str, str]) -> dict[str, list[str]]:
    """Group required-seed gaps by the node that declares them.

    A missing literal is evidence against its own requirement only; one
    leaf's gap (or a classifier false positive) must not fail unrelated leaves.
    """
    grouped: dict[str, list[str]] = {}
    for node in contracts.get("nodes") or []:
        node_id = str(node.get("id") or "")
        gaps = source_seed_gaps(contracts, sources, [node_id])
        if gaps:
            grouped[node_id] = gaps
    return grouped
