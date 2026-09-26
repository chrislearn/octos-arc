"""Versioned, independent pre-implementation review of derived test cases."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scenario_review import behavior_test_titles, grounded_behavior_test, semantic_contract_evidence
from test_policy import test_block

TITLES = re.compile(r"^test\('((?:\\.|[^'\\])*)',", re.M)
REVIEW_STATUSES = {"approved_behavior", "approved_smoke_only", "needs_correction",
                   "disputed", "skipped_with_reason"}
REVIEW_FIELDS = {"id", "status", "requirement_quote", "test_quote", "reason"}
REVIEW_FENCE = re.compile(r"\A```(?:json)?\r?\n([\s\S]*?)\r?\n```\Z", re.I)


def review_request_admissible(phase: str, phase_order: list[str], counts: dict[str, int],
                              spent: int, cap: int) -> bool:
    """Reserve one request for each as-yet-unreviewed top-level category."""
    reserved = sum(other != phase and not counts.get(other, 0) for other in phase_order)
    return spent + reserved < cap


def parse_review_decisions(reply: str, expected_ids: set[str], *, max_chars: int = 65536,
                           max_items: int = 6) -> tuple[list[dict], str | None]:
    """Accept one complete JSON array, optionally in exactly one Markdown fence.

    A malformed batch is never partially promoted. Missing IDs remain
    unreviewed and duplicate/foreign IDs invalidate the whole batch.
    """
    if not isinstance(reply, str) or len(reply) > max_chars:
        return [], "format_invalid"
    source = reply.strip()
    if source.startswith("```"):
        fenced = REVIEW_FENCE.fullmatch(source)
        if not fenced:
            return [], "format_invalid"
        source = fenced.group(1).strip()
    try:
        decisions = json.loads(source)
    except (TypeError, ValueError):
        return [], "format_invalid"
    if not isinstance(decisions, list) or len(decisions) > min(max_items, len(expected_ids)):
        return [], "schema_invalid"
    seen = set()
    for item in decisions:
        if (not isinstance(item, dict) or set(item) - REVIEW_FIELDS
                or not isinstance(item.get("id"), str) or item["id"] not in expected_ids
                or item["id"] in seen or item.get("status") not in REVIEW_STATUSES
                or any(not isinstance(item[key], str) or len(item[key]) > 4500
                       for key in ("requirement_quote", "test_quote", "reason") if key in item)):
            return [], "schema_invalid"
        seen.add(item["id"])
    return decisions, None


def sha(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def requirement_text(target: dict | None, ancestors: str = "") -> str:
    if not target:
        return ""
    return (str(target.get("description") or "") + "\n"
            + "\n".join(map(str, target.get("steps") or [])) + "\n" + ancestors)


def outcome_text(target: dict | None) -> str:
    """The authoritative outcome, excluding GIVEN/WHEN setup and ancestors."""
    if not target:
        return ""
    steps = []
    for step in target.get("steps") or []:
        if isinstance(step, dict):
            if str(step.get("keyword") or "").upper() == "THEN":
                steps.append(str(step.get("content") or ""))
        elif re.match(r"\s*THEN\s*:", str(step), re.I):
            steps.append(str(step))
    return str(target.get("description") or "") + "\n" + "\n".join(steps)


def skip_category(reason: str) -> str:
    """A proposed skip is a coverage gap, classified without model authority."""
    text = str(reason).lower()
    if re.search(r"\b(?:dsl|helper|operation|upload|placeholder|allowed literal|file control)\b", text):
        return "harness_unsupported"
    if re.search(r"\b(?:fixture|seed|second account|starting state)\b", text):
        return "fixture_unavailable"
    if re.search(r"\b(?:duplicate|redundant|already covered)\b", text):
        return "scenario_redundant"
    return "requirement_disputed"


def collect_cases(directory: Path, targets: list[dict], node_ids: set[str],
                  context: dict[str, str] | None = None) -> list[dict]:
    """One record per case, including smoke and unmatched cases.

    A structural candidate is *not* an approval. Only an independent review
    with verbatim requirement and assertion witnesses can grant that status.
    """
    rows = []
    for node_id in sorted(node_ids):
        path = directory / f"{node_id}.spec.ts"
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        by_title = sorted((t for t in targets if t.get("node_id") == node_id),
                          key=lambda t: len(t.get("title", "")), reverse=True)
        for title in [m.group(1).replace("\\'", "'") for m in TITLES.finditer(source)]:
            block = test_block(source, title)
            if not block:
                continue
            target = next((t for t in by_title if title.startswith(t["title"] + " [")), None)
            requirement = requirement_text(target, (context or {}).get(node_id, ""))
            structural = bool(target and title in behavior_test_titles(source)
                              and grounded_behavior_test(source, title, target))
            if structural and target.get("semantic_contracts"):
                # A generic visible-text assertion must not approve an
                # identity/session or negative-account oracle merely because
                # it contains a requirement word. Other cases may cover the
                # remaining branches; each approved case needs one real edge.
                structural = any(semantic_contract_evidence(source, title, contract["kind"])
                                 for contract in target["semantic_contracts"])
            status = ("unreviewed" if structural else "approved_smoke_only" if title.endswith((" [entry]", " [reach]"))
                      else "needs_correction")
            rows.append({"id": sha([node_id, title])[:24], "node_id": node_id,
                         "scenario_id": str(target.get("id") or "") if target else "",
                         "title": title, "file": path.name,
                         "requirements_hash": sha(requirement), "file_hash": sha(source),
                         "case_hash": sha(block), "status": status,
                         "requirement": requirement, "outcome": outcome_text(target), "case": block})
    return rows


def validate_review(row: dict, verdict: dict) -> bool:
    """Ground an approval in exact, independently checked quotations."""
    if verdict.get("status") != "approved_behavior" or row.get("status") != "unreviewed":
        return False
    req = verdict.get("requirement_quote")
    test = verdict.get("test_quote")
    return (isinstance(req, str) and len(req.strip()) >= 12 and req in row.get("outcome", "")
            and isinstance(test, str) and len(test.strip()) >= 12 and test in row["case"]
            and bool(re.search(r"\b(?:h\.)?expect\w*\s*\(|\bassert\s*\(", test))
            and isinstance(verdict.get("reason"), str) and len(verdict["reason"].strip()) >= 12)


def safe_records(rows: list[dict]) -> list[dict]:
    """Persist hashes and conclusions, without duplicating all test source."""
    return [{key: value for key, value in row.items() if key not in {"requirement", "outcome", "case"}}
            for row in rows]
