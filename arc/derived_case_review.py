"""Versioned, independent pre-implementation review of derived test cases."""
from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import Path

from scenario_review import behavior_test_titles, grounded_behavior_test, semantic_contract_evidence
from test_policy import test_block

TITLES = re.compile(r"^test\('((?:\\.|[^'\\])*)',", re.M)
_INTERNAL_SHORTCUTS = (
    (re.compile(r"\bpage\.goto\s*\("), "direct_page_navigation"),
    (re.compile(r"\b(?:page\.)?request\.(?:get|post|put|patch|delete|fetch)\s*\("), "direct_api_request"),
    (re.compile(r"\b(?:localStorage|sessionStorage)\b"), "browser_storage_access"),
    (re.compile(r"\bpage\.(?:evaluate|route|url)\s*\(|\btoHaveURL\s*\("), "browser_internals"),
    (re.compile(r"\.locator\(\s*['\"`](?:\.|#|\[data-)"), "implementation_selector"),
)


def static_case_issues(block: str, target: dict | None) -> list[str]:
    """Check provenance and black-box boundaries without judging semantics.

    Generated DSL helpers such as resetState and watchResponse remain valid;
    they are not direct requests from a test case. Requirement-grounded API
    assertions still go through the separate proposal and review gates.
    """
    issues = [] if target is not None else ["unmapped_scenario"]
    for pattern, reason in _INTERNAL_SHORTCUTS:
        if pattern.search(block):
            issues.append(reason)
    return issues


def audit_generated_suite(directory: Path, targets: list[dict], node_ids: set[str]) -> list[dict]:
    """Read-only suite audit; missing cases are gaps, never invented tests."""
    issues: list[dict] = []
    for node_id in sorted(node_ids):
        path = directory / f"{node_id}.spec.ts"
        if not path.is_file():
            issues.append({"node_id": node_id, "title": "", "reason": "missing_spec", "kind": "gap"})
            continue
        source = path.read_text(encoding="utf-8")
        titles = [match.group(1).replace("\\'", "'") for match in TITLES.finditer(source)]
        for title in dict.fromkeys(titles):
            target = next((row for row in targets if row.get("node_id") == node_id
                           and title.startswith(str(row.get("title") or "") + " [")), None)
            reasons = (["duplicate_title"] if titles.count(title) != 1 else [])
            block = test_block(source, title)
            reasons.extend(static_case_issues(block or "", target))
            for reason in reasons:
                issues.append({"node_id": node_id, "title": title, "reason": reason,
                               "kind": "candidate"})
        if not titles:
            issues.append({"node_id": node_id, "title": "", "reason": "empty_spec", "kind": "gap"})
    return issues
class CaseStatus(str, Enum):
    """Persistent per-case review states; execution outcomes are separate."""
    UNREVIEWED = "unreviewed"
    NEEDS_CORRECTION = "needs_correction"
    APPROVED_BEHAVIOR = "approved_behavior"
    APPROVED_BASIC = "approved_basic"
    APPROVED_SMOKE_ONLY = "approved_smoke_only"
    INVALID = "invalid"
    DISPUTED = "disputed"
    SKIPPED_UNREVIEWED = "skipped_unreviewed"
    SKIPPED_WITH_REASON = "skipped_with_reason"
    UNVERIFIED_GAP = "unverified_gap"


REVIEW_STATUSES = {CaseStatus.APPROVED_BEHAVIOR, CaseStatus.APPROVED_SMOKE_ONLY,
                   CaseStatus.NEEDS_CORRECTION, CaseStatus.DISPUTED,
                   CaseStatus.SKIPPED_WITH_REASON}
REVIEW_FIELDS = {"id", "status", "requirement_quote", "test_quote", "reason", "branch", "obligation_ids", "obligation_evidence"}
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
        if item.get("branch", "unknown") not in ("success", "rejection", "mixed", "unknown"):
            return [], "schema_invalid"
        if 'obligation_ids' in item and (not isinstance(item['obligation_ids'], list) or
                not all(isinstance(key, str) for key in item['obligation_ids'])):
            return [], 'schema_invalid'
        evidence = item.get('obligation_evidence', [])
        if (not isinstance(evidence, list) or len(evidence) > 100 or any(
                not isinstance(witness, dict) or set(witness) != {'obligation_id', 'requirement_quote', 'test_quote'}
                or any(not isinstance(value, str) or len(value) > 4500 for value in witness.values())
                for witness in evidence)):
            return [], 'schema_invalid'
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
            + "\n".join(map(str, target.get("steps") or [])) + "\n" + ancestors
            + ("\nSource obligations: " + json.dumps(target['obligations'], sort_keys=True, ensure_ascii=False)
               if target.get('obligations') else ''))


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
    return (str(target.get("description") or "") + "\n" + "\n".join(steps)
            + "\n" + "\n".join(row.get("quote", "") for row in target.get("obligations", [])))


def numbered_review_quotes(row: dict) -> dict[str, str]:
    """Stable, source-derived quote choices; an ID carries no review authority."""
    result: dict[str, str] = {}
    for prefix, source in (("R", row.get("outcome", "")), ("T", row.get("case", ""))):
        lines = [line.strip() for line in str(source).splitlines() if line.strip()]
        if prefix == "T":
            lines = [line for line in lines if re.search(r"\b(?:h\.)?expect\w*\s*\(|\bassert\s*\(", line)]
        for line in dict.fromkeys(lines):
            if len(line) >= 12 and len(result) < 100:
                result[f"{prefix}{1 + sum(key.startswith(prefix) for key in result)}"] = line
    return result


def restore_review_quote_ids(decision: dict, quotes: dict[str, str]) -> dict:
    """Replace selected IDs with exact source text before the existing validator."""
    restored = dict(decision)
    for field in ("requirement_quote", "test_quote"):
        value = restored.get(field)
        if isinstance(value, str) and value in quotes:
            restored[field] = quotes[value]
    evidence = restored.get("obligation_evidence")
    if isinstance(evidence, list):
        restored["obligation_evidence"] = [
            {key: quotes.get(value, value) if key in ("requirement_quote", "test_quote")
             and isinstance(value, str) else value for key, value in item.items()}
            if isinstance(item, dict) else item for item in evidence]
    return restored


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
        titles = [m.group(1).replace("\\'", "'") for m in TITLES.finditer(source)]
        for title in dict.fromkeys(titles):
            block = test_block(source, title)
            target = next((t for t in by_title if title.startswith(t["title"] + " [")), None)
            static_issues = (["duplicate_title"] if titles.count(title) != 1 else [])
            static_issues += static_case_issues(block or "", target)
            if not block and not static_issues:
                continue
            requirement = requirement_text(target, (context or {}).get(node_id, ""))
            structural = bool(not static_issues and target and title in behavior_test_titles(source)
                              and grounded_behavior_test(source, title, target))
            if structural and target.get("semantic_contracts"):
                # A generic visible-text assertion must not approve an
                # identity/session or negative-account oracle merely because
                # it contains a requirement word. Other cases may cover the
                # remaining branches; each approved case needs one real edge.
                structural = any(semantic_contract_evidence(source, title, contract["kind"])
                                 for contract in target["semantic_contracts"])
            status = ("invalid" if static_issues else "unreviewed" if structural
                      else "approved_smoke_only" if re.search(r" \[(?:entry|reach)\](?:\s|$)", title)
                      else "needs_correction")
            rows.append({"id": sha([node_id, title])[:24], "node_id": node_id,
                         "scenario_id": str(target.get("id") or "") if target else "",
                         "title": title, "file": path.name,
                         "requirements_hash": sha(requirement), "file_hash": sha(source),
                         "case_hash": sha(block or ""), "status": status,
                         "static_issues": static_issues,
                         "origin": target.get("origin", "requirement_scenario") if target else "unmatched",
                         "obligations": target.get('obligations', []) if target else [],
                         "requirement": requirement, "outcome": outcome_text(target), "case": block or ""})
    return rows


def assertion_after_action(case: str, quote: str) -> bool:
    """Do not certify a setup assertion as the feature's outcome witness."""
    if not case or not quote:
        return False
    # Generated phase wrappers are one line. Remove setup lines before looking
    # for action evidence: entering the seed is not the requested workflow.
    case = "\n".join(line for line in case.splitlines()
                     if not re.search(r"test\.step\(['\"]setup:", line))
    # expectDownload clicks the named control and verifies the resulting file
    # in one helper call, so it is both the action and the assertion.
    if re.search(r"\b(?:expectDownload|expectSignInRejected)\s*\(", quote):
        return True
    actions = list(re.finditer(r"await\s+h\.(?!expect\w*\s*\(|openHome\s*\(|signIn\s*\(|resetState\s*\(|watchResponse\s*\()\w+\s*\(", case))
    if not actions:
        return False
    first_action = actions[0].start()
    return any(match.start() > first_action for match in re.finditer(re.escape(quote), case))


def review_validation_errors(row: dict, verdict: dict) -> list[str]:
    """Explain witness rejection without mistaking the reviewer's prose for approval."""
    errors = []
    if verdict.get('status') != 'approved_behavior' or row.get('status') != 'unreviewed':
        return ['case_not_behavior_candidate_or_not_approved']
    def witness_errors(req, test, outcome):
        result = []
        if not isinstance(req, str) or len(req.strip()) < 12 or req not in outcome:
            result.append('requirement_quote_not_in_authoritative_outcome')
        if not isinstance(test, str) or len(test.strip()) < 12 or test not in row['case']:
            result.append('test_quote_not_in_case')
        elif not re.search(r"\b(?:h\.)?expect\w*\s*\(|\bassert\s*\(", test):
            result.append('test_quote_has_no_assertion')
        elif not assertion_after_action(row['case'], test):
            result.append('assertion_does_not_follow_action')
        return result
    errors += witness_errors(verdict.get('requirement_quote'), verdict.get('test_quote'), row.get('outcome', ''))
    if not isinstance(verdict.get('reason'), str) or len(verdict['reason'].strip()) < 12:
        errors.append('missing_review_reason')
    if row.get('obligations'):
        ids = verdict.get('obligation_ids', [])
        allowed = {item['id']: item for item in row['obligations']}
        if not isinstance(ids, list) or not ids or any(not isinstance(key, str) or key not in allowed for key in ids):
            return errors + ['invalid_or_missing_obligation_ids']
        evidence = verdict.get('obligation_evidence', [])
        if not isinstance(evidence, list):
            return errors + ['invalid_obligation_evidence']
        for key in ids:
            # Legacy source-less rows remain readable; new ledgers require individual witnesses.
            quote = allowed[key].get('quote')
            if not quote:
                continue
            witnesses = [item for item in evidence if isinstance(item, dict) and item.get('obligation_id') == key]
            if len(witnesses) != 1:
                errors.append(f'{key}: missing_or_duplicate_obligation_witness')
            else:
                errors += [f'{key}: {reason}' for reason in witness_errors(
                    witnesses[0].get('requirement_quote'), witnesses[0].get('test_quote'), quote)]
    return errors


def validate_review(row: dict, verdict: dict) -> bool:
    return not review_validation_errors(row, verdict)


def safe_records(rows: list[dict]) -> list[dict]:
    """Persist hashes and conclusions, without duplicating all test source."""
    return [{key: value for key, value in row.items() if key not in {"requirement", "outcome", "case"}}
            for row in rows]
