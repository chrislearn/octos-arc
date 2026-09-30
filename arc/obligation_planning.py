"""Independent, source-grounded obligation extraction for generated tests.

Semantic review is a planning decision, never evidence that the application passes.
Missing or invalid plans remain explicit gaps without withholding implementation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time


_SCOPE_ONLY = re.compile(r'\b(?:outside (?:the )?(?:core )?scope|out of scope|beyond (?:the )?scope)\b', re.I)
_CAPABILITY_ACTIONS = re.compile(r'\b(?:view\w*|open\w*|creat\w*|renam\w*|import\w*|export\w*|delet\w*|sort\w*|filter\w*)\b', re.I)


def obligation_kind(owner, leaf, quote):
    """Keep scope statements and broad category lists out of leaf test oracles."""
    hard_rule = re.search(r'\b(?:must|shall|required|after|when|if)\b', quote, re.I)
    if _SCOPE_ONLY.search(quote) and not hard_rule and not re.search(r'\bsupports\b', quote, re.I):
        return 'context'
    if (owner != leaf and len(quote) <= 240 and quote.count('.') <= 1 and not hard_rule
            and re.search(r'^\s*supports\b', quote, re.I)):
        actions = {match.group(0).lower()[:4] for match in _CAPABILITY_ACTIONS.finditer(quote)}
        if len(actions) >= 3:
            return 'summary'
    return 'test'


def repeated_source_text(source):
    lines = [line.strip() for line in source.splitlines() if len(line.strip()) >= 60]
    return len(lines) != len(set(lines))


def duplicate_only_gap(reason, affected, sources, ancestry):
    """An identical repeated outcome is not a competing business rule."""
    if not re.search(r'\b(?:exact|identical)\s+duplicat\w*|\b(?:identical|verbatim)\s+repeat\w*|\bappears?\s+twice\s+verbatim\b', reason, re.I):
        return False
    if re.search(r'\b(?:contradict\w*|conflict\w*|incompatib\w*|differ\w*|inconsisten\w*)\b', reason, re.I):
        return False
    return bool(affected) and all(any(repeated_source_text(sources.get(owner, ''))
                                      for owner in ancestry[leaf]) for leaf in affected)


def dedupe_source_text(source):
    seen, result = set(), []
    for line in source.splitlines():
        key = line.strip()
        if len(key) >= 60 and key in seen:
            continue
        seen.add(key)
        result.append(line)
    return '\n'.join(result)


def source_scope(tree, leaves):
    wanted = set(leaves)
    sources, ancestry = {}, {}
    def visit(node, parents):
        if not isinstance(node, dict):
            return
        key = str(node.get('id') or '')
        chain = parents + ([key] if key else [])
        if key:
            # Preserve original strings rather than a JSON-escaped quotation.
            text = str(node.get('description') or '')
            text += '\n' + '\n'.join(str(s.get('content') or '') for scenario in node.get('scenarios', [])
                                      for s in scenario.get('steps', []) if str(s.get('keyword', '')).upper() == 'THEN')
            sources[key] = text
        if key in wanted:
            ancestry[key] = chain
        for child in node.get('children') or []:
            visit(child, chain)
    visit(tree, [])
    ids = {key for chain in ancestry.values() for key in chain}
    return {key: sources[key] for key in sources if key in ids}, ancestry


def parse_obligation_details(reply, sources, ancestry):
    """Validate each leaf separately; an unrelated sibling cannot veto it."""
    errors = {leaf: [] for leaf in ancestry}
    global_errors, result = [], []
    try:
        if isinstance(reply, str) and reply.lstrip().startswith('```'):
            fence = re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```\s*', reply, re.I)
            if not fence:
                return [], errors, ['invalid JSON envelope']
            reply = fence.group(1)
        body = json.loads(reply)
    except (ValueError, TypeError):
        return [], errors, ['invalid JSON object']
    if not isinstance(body, dict) or not isinstance(body.get('obligations'), list):
        return [], errors, ['missing obligations array']
    for index, item in enumerate(body['obligations']):
        if not isinstance(item, dict):
            global_errors.append(f'obligation {index}: expected object'); continue
        owner, quote, outcome = (item.get(key) for key in ('requirement_id', 'quote', 'outcome'))
        applies = item.get('applies_to')
        # A shared-parent row may name leaves assigned to another small batch.
        # Validate and publish only this batch's leaves; the other leaves need
        # their own review, and cannot make this batch's valid quote disappear.
        valid_scope = isinstance(applies, list) and bool(applies) and all(
            isinstance(leaf, str) and bool(leaf) for leaf in applies)
        affected = set(applies).intersection(ancestry) if valid_scope else None
        if valid_scope and not affected:
            continue
        if (not isinstance(owner, str) or owner not in sources or not isinstance(quote, str)
                or len(quote.strip()) < 12 or quote not in sources[owner]
                or not isinstance(outcome, str) or len(outcome.strip()) < 12
                or item.get('branch') not in {'success', 'rejection', 'mixed'}
                or affected is None):
            message = f'obligation {index}: invalid quote, branch, outcome or applicability'
            if affected:
                for leaf in affected:
                    errors[leaf].append(message)
            else:
                global_errors.append(message)
            continue
        # IDs belong to a leaf, even when the model writes one shared-parent
        # row for several leaves. A retry for one leaf must not invalidate a
        # sibling's reviewed obligation IDs and case witnesses.
        for leaf in sorted(affected):
            if owner not in ancestry[leaf]:
                errors[leaf].append(f'obligation {index}: invalid source applicability')
                continue
            canonical = dict(requirement_id=owner, quote=quote, outcome=outcome,
                             branch=item['branch'], applies_to=[leaf])
            kind = obligation_kind(owner, leaf, quote)
            if kind != 'test':
                canonical['kind'] = kind
            canonical['id'] = 'OB-' + hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:20]
            if canonical not in result:
                result.append(canonical)
    for leaf in ancestry:
        if not any(leaf in row['applies_to'] and row['requirement_id'] == leaf for row in result):
            errors[leaf].append(f'{leaf}: no leaf-specific obligation')
        for parent in ancestry[leaf][:-1]:
            if (len(sources[parent].strip()) >= 12
                    and not any(row['requirement_id'] == parent and leaf in row['applies_to'] for row in result)):
                errors[leaf].append(f'{leaf}: missing inherited source {parent}')
    gaps = body.get('gaps')
    if not isinstance(gaps, list):
        global_errors.append('gaps must be an array')
    else:
        for gap in gaps:
            if isinstance(gap, dict):
                reason = str(gap.get('reason') or '')[:600]
                affected = gap.get('applies_to')
                if (not reason or not isinstance(affected, list) or not affected
                        or any(not isinstance(leaf, str) or not leaf for leaf in affected)):
                    global_errors.append('semantic gap: invalid scope or reason')
                    continue
                affected = set(affected).intersection(ancestry)
                if not affected:
                    continue
            else:
                reason = str(gap)[:600]
                mentioned = {source_id for source_id in sources if re.search(
                    r'(?<![A-Za-z0-9_-])' + re.escape(source_id) + r'(?![A-Za-z0-9_-])', reason)}
                affected = [leaf for leaf, chain in ancestry.items() if mentioned.intersection(chain)]
            if duplicate_only_gap(reason, affected, sources, ancestry):
                continue
            message = 'semantic gap: ' + reason
            if affected:
                for leaf in affected:
                    errors[leaf].append(message)
            else:
                global_errors.append(message)
    return result, errors, global_errors


def parse_obligations(reply, sources, ancestry):
    """Compatibility view of exact source quotes and all validation errors."""
    rows, by_leaf, global_errors = parse_obligation_details(reply, sources, ancestry)
    return rows, global_errors + [error for errors in by_leaf.values() for error in errors]


def applicable_obligations(flow, node_id):
    rows = getattr(flow, 'derived_obligations', None)
    if rows is None:
        rows = (getattr(flow, 'app_design_doc', None) or {}).get('obligations', [])
    def summary_covered(row):
        owner = str(row.get('requirement_id') or '')
        tree = getattr(flow, 'requirement_tree', None)
        def find(node):
            if not isinstance(node, dict):
                return None
            if str(node.get('id')) == owner:
                return node
            for child in node.get('children') or []:
                found = find(child)
                if found is not None:
                    return found
            return None
        parent = find(tree)
        if parent is None:
            return False
        def leaves(node):
            children = node.get('children') or []
            if not children:
                return [node]
            return [leaf for child in children if isinstance(child, dict) for leaf in leaves(child)]
        descendant_text = '\n'.join(str(part) for leaf in leaves(parent)
                                    for part in (leaf.get('name') or '', leaf.get('description') or ''))
        stems = {match.group(0).lower()[:4] for match in _CAPABILITY_ACTIONS.finditer(str(row.get('quote') or ''))}
        return bool(stems) and all(re.search(r'\b' + re.escape(stem) + r'\w*\b', descendant_text, re.I)
                                    for stem in stems)
    return [row for row in rows
            if node_id in row.get('applies_to', [row.get('requirement_id')])
            and (row.get('kind', 'test') == 'test'
                 or (row.get('kind') == 'summary' and not summary_covered(row)))]


def reviewed_obligations_intact(flow, node_id):
    """Exception recovery may retain approval only with its exact source ledger."""
    rows = getattr(flow, 'derived_obligations', None)
    if not isinstance(rows, list):
        return False
    selected = [row for row in rows if isinstance(row, dict)
                and node_id in row.get('applies_to', [])]
    sources, ancestry = source_scope(getattr(flow, 'requirement_tree', None), [node_id])
    if node_id not in ancestry or not selected:
        return False
    try:
        reply = json.dumps({'obligations': selected, 'gaps': []})
        checked, by_leaf, global_errors = parse_obligation_details(reply, sources, ancestry)
        return (bool(checked) and len(checked) == len(selected) and not by_leaf[node_id] and not global_errors
                and {row['id'] for row in checked} == {row.get('id') for row in selected})
    except (TypeError, ValueError, KeyError):
        return False


def obligation_prompt(sources, ancestry):
    """Stable shared prefix followed by the batch's exact source contracts."""
    return ('Extract an exhaustive test obligation ledger from the original requirements below. '
            'One independent hard outcome, format field/rule, state transition, error branch or persistence rule '
            'per obligation. Preserve exact official schemas, values and HTTP status codes where given. '
            'Separate valid and invalid workflows, and identify preconditions and unchanged state on failure '
            'in outcome. Do not invent product rules. Include inherited parent constraints for applicable leaves; '
            'for scope-only parents record their scope restriction, not a new product feature. '
            'For EACH leaf include at least one exact quote from that leaf and from EACH ancestor '
            'with substantive text. One parent obligation may apply to several leaves. '
            'Return ONLY {"obligations":[{"requirement_id":"source ID","applies_to":["leaf ID"],'
            '"quote":"exact original substring","branch":"success|rejection|mixed",'
            '"outcome":"concrete action and observable result"}],'
            '"gaps":[{"applies_to":["leaf ID"],"reason":"unresolved issue"}]}. '
            'Record unresolved contradictions or unsupported obligations in leaf-scoped gaps; do not silently omit them. '
            'No application code or generated tests are evidence.\nSOURCES:\n' + json.dumps(
                {key: dedupe_source_text(value) for key, value in sources.items()}, ensure_ascii=False)
            + '\nLEAF ANCESTRY (every listed source needs coverage):\n' + json.dumps(ancestry))


_COMPLEX_SOURCE = re.compile(
    r'\b(?:if|unless|except|otherwise|either|both|before|after|without|and|or|not|never|'
    r'cannot|can.t|won.t|doesn.t|isn.t|only|requires?|must|shall|'
    r'fail\w*|reject\w*|den(?:y|ied|ies)\w*|'
    r'permission\w*|authoriz\w*|persist\w*|atomic|transaction\w*|import|export|format|csv|json|'
    r'error\w*|invalid|role|access|limit\w*)\b|[;,；，、]|如果|否则|当.+时|不能|不会|不得|'
    r'不可|仅|只有|必须|禁止|失败|拒绝|权限|保存后|刷新后|同时|以及|\n\s*\S', re.I)


def _uncovered_source_clauses(leaf, sources, ancestry, rows):
    uncovered = []
    for owner in ancestry.get(leaf, []):
        for line in sources.get(owner, '').splitlines():
            for clause in re.split(r'(?<=[.!?。！？])\s+', line.strip()):
                clause = clause.strip()
                if (len(clause) >= 12 and not _SCOPE_ONLY.search(clause)
                        and not any(leaf in row.get('applies_to', []) and row.get('requirement_id') == owner
                                    and clause in row.get('quote', '') for row in rows)):
                    uncovered.append(f'{owner}: source clause not represented: {clause[:100]}')
    return uncovered


def _simple_obligations(sources, ancestry):
    """Compile only unambiguous, single-clause source text without an LLM."""
    proposals = []
    for leaf, chain in ancestry.items():
        for owner in chain:
            quote = sources.get(owner, '').strip()
            if not quote:
                continue
            if (len(quote) < 12 or len(quote) > 240 or _COMPLEX_SOURCE.search(quote)
                    or len(re.findall(r'[.!?。！？]', quote)) > 1):
                return None
            proposals.append(dict(requirement_id=owner, applies_to=[leaf], quote=quote,
                                  branch='success', outcome=quote))
    rows, by_leaf, errors = parse_obligation_details(
        json.dumps({'obligations': proposals, 'gaps': []}, ensure_ascii=False), sources, ancestry)
    if errors or any(by_leaf.values()) or not rows:
        return None
    return rows


def prepare_obligations(flow, nodes):
    """One source-grounded planning pass; no model self-review or retry.

    The independent *case* audit remains mandatory. A missing or ambiguous
    obligation plan is debt, never permission to run an unreviewed test.
    """
    tree = getattr(flow, 'requirement_tree', None)
    if not tree or not nodes:
        return
    flow.derived_obligation_status = getattr(flow, 'derived_obligation_status', {})
    flow.derived_obligations = getattr(flow, 'derived_obligations', [])
    pending = [node for node in nodes if str(node.get('id')) not in flow.derived_obligation_status
               or flow.derived_obligation_status[str(node.get('id'))].get('attempts', 0) == 0]
    if not pending:
        return
    suite = getattr(flow, 'derived_tests_dir', None) or flow.output_dir / 'derived-tests'
    path = suite / 'review' / 'obligations.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    batch_size = max(1, min(6, int(os.environ.get('OCTOS_ARC_OBLIGATION_BATCH_LEAVES', '3'))))
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset:offset + batch_size]
        ids = [str(node.get('id')) for node in batch]
        sources, ancestry = source_scope(tree, ids)
        initial = getattr(flow, 'initial_test_planning_index', None) or {}
        current_hash = hashlib.sha256(json.dumps(tree, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        imported = []
        if initial.get('requirements_hash') == current_hash:
            for item in initial.get('obligations', []):
                if not isinstance(item, dict):
                    continue
                owner, quote = item.get('requirement_id'), item.get('quote')
                if not isinstance(quote, str) or len(re.findall(r'[.!?。！？](?:\s|$)', quote)) > 1:
                    continue  # whole paragraphs are not atomic reusable obligations
                applies = item.get('applies_to') or [leaf for leaf, chain in ancestry.items() if owner in chain]
                imported.append({**item, 'applies_to': applies})
        seeded, seed_errors, seed_global = parse_obligation_details(
            json.dumps({'obligations': imported, 'gaps': []}), sources, ancestry) if imported else ([], {}, [])
        reused = bool(seeded) and not seed_global and not any(seed_errors.values()) and not any(
            _uncovered_source_clauses(leaf, sources, ancestry, seeded) for leaf in ids)
        rows = seeded if reused else _simple_obligations(sources, ancestry) if len(ancestry) == len(ids) else None
        errors = {leaf: [] for leaf in ids}
        global_errors = []
        replies = []
        if rows is None:
            prompt = obligation_prompt(sources, ancestry)
            if seeded:
                prompt += ('\nALREADY SOURCE-GROUNDED OBLIGATIONS (retained by the harness):\n'
                           + json.dumps(seeded, ensure_ascii=False)
                           + '\nExtract only missing outcomes/branches and source clauses. Do not repeat retained obligations. '
                             'They are merged before the same complete-source validation; report unresolved gaps.')
            left = min(getattr(flow, 'derived_preflight_deadline', float('inf')) - time.monotonic(),
                       flow.remaining() - flow.final_phase_reserve() - 600)
            if (left >= 30 and len(prompt) <= flow.codegen_context_chars()
                    and not flow.wound_down() and not flow.review_budget_spent()
                    and not flow.derived_preflight_tokens_spent()):
                flow.start_derived_designs(ids, 'extracting business test obligations')
                flow.snapshot_protected()
                ok, reply = flow.text_turn(prompt, min(300, left), 'derived obligation extraction',
                                           system='You audit requirement contracts. Return one JSON object only.',
                                           spec_chars=len(prompt))
                replies.append(str(reply))
                if ok:
                    if seeded:
                        try:
                            raw = str(reply).strip()
                            if raw.startswith('```'):
                                raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
                            body = json.loads(raw)
                            if isinstance(body, dict) and isinstance(body.get('obligations'), list):
                                body['obligations'] = seeded + body['obligations']
                                reply = json.dumps(body, ensure_ascii=False)
                        except (ValueError, TypeError):
                            pass
                    rows, parsed_errors, global_errors = parse_obligation_details(reply, sources, ancestry)
                    errors.update(parsed_errors)
                else:
                    global_errors = ['request unavailable']
            else:
                global_errors = ['insufficient planning budget or context']
        valid_rows = rows or []
        # Commit sourced candidates, even when one leaf has an explicit gap.
        flow.derived_obligations = [row for row in flow.derived_obligations
                                    if not set(row.get('applies_to') or []).intersection(ids)] + valid_rows
        for leaf in ids:
            issues = global_errors + errors.get(leaf, [])
            if leaf not in ancestry:
                issues = ['missing from requirement tree'] + issues
            selected = [row for row in valid_rows if leaf in row.get('applies_to', [])]
            if not selected:
                issues = ['no source-grounded obligations'] + issues
            issues.extend(_uncovered_source_clauses(leaf, sources, ancestry, valid_rows))
            flow.derived_obligation_status[leaf] = {
                'status': 'source_grounded' if not issues else 'incomplete',
                'errors': issues, 'attempts': 1, 'candidate_obligations': len(selected),
                'method': ('reused_initial' if reused else 'mechanical' if not replies and rows is not None else
                           'model_once' if replies else 'not_attempted'),
            }
        (path.parent / ('obligation-' + hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12] + '.json')).write_text(
            json.dumps({'leaves': ids, 'replies': replies, 'errors': global_errors,
                        'node_status': {leaf: flow.derived_obligation_status[leaf] for leaf in ids}},
                       ensure_ascii=False, indent=2))
        flow.metric('derived_obligations', nodes=ids,
                    grounded=[leaf for leaf in ids if flow.derived_obligation_status[leaf]['status'] == 'source_grounded'],
                    obligations=len(valid_rows), errors=global_errors)
    flow.derived_obligation_seconds = getattr(flow, 'derived_obligation_seconds', 0.0) + time.monotonic() - started
    report = json.dumps({'version': 1, 'obligations': flow.derived_obligations,
                         'nodes': flow.derived_obligation_status, 'seconds': flow.derived_obligation_seconds},
                        ensure_ascii=False, indent=2)
    path.write_text(report)
    design_dir = flow.output_dir / 'design'
    design_dir.mkdir(exist_ok=True)
    (design_dir / 'test-obligations.json').write_text(report)
    flow.snapshot_protected()
