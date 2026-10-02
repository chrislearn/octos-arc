"""Deliver complete, source-reviewed prerequisites to text-only generation.

Selection follows declared case fixtures and known public helper literals.
The size preference may select a dependency closure instead of the whole
catalogue, but never removes a required record from that closure. The caller's
serialized prompt budget remains the hard input limit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def identities(row: dict) -> set[str]:
    return {str(row[field]).lower() for field in
            ('username', 'name', 'identifier', 'display_name', 'slug', 'id')
            if isinstance(row.get(field), (str, int)) and str(row[field])}


def values(value) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(values(v) for v in value.values()),
                           {str(key).lower() for key in value}) if value else set()
    if isinstance(value, list):
        return set().union(*(values(v) for v in value)) if value else set()
    return {str(value).lower()} if isinstance(value, (str, int)) else set()


def referenced_names(document: dict, evidence: str, plan: list[dict],
                     node_ids: list[str]) -> set[str]:
    names = set()
    if document.get('task') != 'hackathon--github':
        return names
    # These literals are the public contract of the frozen GitHub helper,
    # not inferred application routes or private seed APIs.
    for match in re.finditer(r"\bh\.fixtureRepo\(\s*(['\"])([\w-]+)\1\s*\)", evidence):
        names.add('spec-' + match[2].lower().replace('_', '-'))
    for match in re.finditer(r"\bh\.(?:pr|issue|organization|compare)\(\s*\w+\s*,\s*(['\"])([\w-]+)\1(?:\s*[,)]|\s*$)", evidence):
        fid = match[2].lower().replace('_', '-')
        names.update(('spec-' + fid, 'spec-org-' + fid))
    for row in plan:
        # Metadata also resolves computed expressions such as
        # fixtureRepo('issue-edit-' + role), without executing test code.
        if row.get('node_id') in node_ids and row.get('fixture'):
            names.update(('spec-' + row['fixture'], 'spec-org-' + row['fixture']))
    return names


def select_prerequisites(document: dict, evidence: str, *, plan=(), node_ids=()) -> tuple[dict, list[str]]:
    records = [(key, index, row) for key, rows in document.items() if isinstance(rows, list)
               for index, row in enumerate(rows) if isinstance(row, dict)]
    names = referenced_names(document, evidence, list(plan), list(node_ids))
    lowered = evidence.lower()
    selected = {(key, index) for key, index, row in records if identities(row) & names or any(
        re.search(r'(?<![\w-])' + re.escape(value) + r'(?![\w-])', lowered)
        for value in identities(row))}
    while True:
        refs = set().union(*(values(row) for key, index, row in records if (key, index) in selected)) if selected else set()
        active = set().union(*(identities(row) for key, index, row in records if (key, index) in selected)) if selected else set()
        expanded = selected | {(key, index) for key, index, row in records if identities(row) & refs or (
            any(part in key.lower() for part in ('grant', 'permission', 'membership', 'relation'))
            and values(row) & active)}
        if expanded == selected:
            break
        selected = expanded
    result = {key: value for key, value in document.items() if not isinstance(value, list)}
    required = []
    for key, index, row in records:
        if (key, index) in selected:
            result.setdefault(key, []).append(row)
            required.append(f'{key}[{index}]')
    return result, required


def fixture_context(flow, evidence: str, node_ids=()) -> str:
    directory = getattr(flow, 'tests_dir', None)
    if not getattr(flow, 'frozen_suite', None) or not isinstance(directory, Path):
        return ''
    import os
    cap = max(0, int(os.environ.get('OCTOS_ARC_FIXTURE_CONTEXT_CHARS', '12000')))
    if not cap:
        return ''
    source = directory / 'fixtures.json'
    if not source.exists():
        raise ValueError('Frozen suite has no public fixture manifest')
    document = json.loads(source.read_text(encoding='utf8'))
    if not isinstance(document, dict):
        raise ValueError('Frozen fixture manifest must be an object')
    render = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if len(render(document)) <= cap:
        selected = document
        required = [f'{key}[{i}]' for key, rows in document.items() if isinstance(rows, list)
                    for i, row in enumerate(rows) if isinstance(row, dict)]
    else:
        plan_path = directory / 'case-plan.json'
        plan = json.loads(plan_path.read_text(encoding='utf8')) if plan_path.exists() else []
        selected, required = select_prerequisites(document, evidence, plan=plan, node_ids=node_ids)
    if not required:
        return ''
    body = render(selected)
    # Keep owners, role accounts, nested branches/reviews and grants together.
    # Passing a filesystem path to a text-only turn cannot deliver those bytes.
    if len(body) > cap:
        metric = getattr(flow, 'metric', None)
        if callable(metric):
            metric('fixture_context', complete=True, over_inline_preference=True,
                   required_records=required, required_chars=len(body), cap_chars=cap,
                   source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    return ('\nPublic fixture prerequisites (read-only source-reviewed records; provision through normal '
            'application seeds, preserve independent records, no private test API). '
            'This dependency closure is complete; initialize stable IDs once and resolve every '
            'owner/account/team/branch/review/check reference from the same canonical records. '
            'Never use a username as an unrelated collection primary key, truncate these relationships, '
            'or reseed persisted edits on login/restart. Original atomic behavior rules outrank '
            'conflicting screenshots or generic scenario wording.\n' + body + '\n')
