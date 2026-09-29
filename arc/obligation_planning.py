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


def prepare_obligations(flow, nodes):
    """Two bounded turns per small batch, with leaf-local admission."""
    tree = getattr(flow, 'requirement_tree', None)
    if not tree or not nodes:
        return
    if not hasattr(flow, 'derived_obligation_status'):
        flow.derived_obligation_status = {}
    if not hasattr(flow, 'derived_obligations'):
        flow.derived_obligations = []
    max_attempts = 3 if getattr(flow, '_completeness_active', False) else 2
    pending = [n for n in nodes if flow.derived_obligation_status.get(str(n['id']), {}).get('status') != 'reviewed'
               and flow.derived_obligation_status.get(str(n['id']), {}).get('attempts', 0) < max_attempts]
    if not pending:
        return
    path = flow.output_dir / 'derived-tests' / 'review' / 'obligations.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    for node in pending:
        flow.derived_obligation_status.setdefault(str(node['id']), {'status': 'incomplete', 'errors': ['not yet reviewed'], 'attempts': 0})
    phase_left = getattr(flow, 'derived_preflight_deadline', float('inf')) - time.monotonic()
    # Two independent turns took about 200 seconds for one leaf in 8ea2.
    # Keep a per-leaf allowance; the global and final-phase deadlines still win.
    cap = max(0, int(os.environ.get('OCTOS_ARC_OBLIGATION_SECONDS',
                                str(max(2400, len(getattr(flow, 'derived_nodes', nodes)) * 210)))))
    spent = getattr(flow, 'derived_obligation_seconds', 0.0)
    deadline = time.monotonic() + max(0, min(cap - spent, phase_left * .30,
                                           flow.remaining() - flow.final_phase_reserve() - 600))
    started = time.monotonic()
    parallel_results = None
    try:
        batch_size = max(1, min(6, int(os.environ.get('OCTOS_ARC_OBLIGATION_BATCH_LEAVES', '3'))))
        batch_count = (len(pending) + batch_size - 1) // batch_size
        batches = []
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset:offset + batch_size]
            ids = [str(n['id']) for n in batch]
            sources, ancestry = source_scope(tree, ids)
            batches.append((batch, ids, sources, ancestry, obligation_prompt(sources, ancestry)))
        from spec_parallel import SpecRequest, reservation_tokens
        jobs = []
        jobs_by_batch = {}
        for index, (_, ids, _, ancestry, prompt) in enumerate(batches):
            if not ancestry or len(prompt) > flow.codegen_context_chars():
                continue
            job = SpecRequest(prompt, min(300, max(30, int((deadline - started) / max(1, 2 * batch_count)))),
                              'derived obligation extraction',
                              'You audit requirement contracts. Return one JSON object only.',
                              reservation_tokens(prompt), deadline)
            jobs.append(job)
            jobs_by_batch[index] = job
        pool = (flow.isolated_spec_requests(
            len(jobs), allowed=lambda _job: deadline - time.monotonic() >= 60 and not flow.wound_down())
            if hasattr(flow, 'isolated_spec_requests') else None)
        parallel_results = pool.ordered(jobs) if pool is not None else None
        first_parallel_reply = next(parallel_results) if parallel_results is not None else None
        parallel_fallback = first_parallel_reply is None and parallel_results is not None
        for batch_index, offset in enumerate(range(0, len(pending), batch_size)):
            batch, ids, sources, ancestry, prompt = batches[batch_index]
            if (deadline - time.monotonic() < 60 or flow.wound_down() or flow.review_budget_spent() or flow.derived_preflight_tokens_spent()
                    or not ancestry):
                continue
            if len(prompt) > flow.codegen_context_chars():
                for leaf in ids:
                    flow.derived_obligation_status[leaf]['errors'] = ['insufficient_context']
                continue
            batch_deadline = min(deadline, time.monotonic() +
                                 max(0, deadline - time.monotonic()) / (batch_count - batch_index))
            flow.start_derived_designs(ids, 'extracting business test obligations')
            replies, first_rows, rows = [], [], []
            by_leaf, global_errors = {leaf: [] for leaf in ids}, []
            first_parseable = False
            for turn in range(2):
                left = batch_deadline - time.monotonic()
                if left < 30 or flow.derived_preflight_tokens_spent() or flow.wound_down() or flow.review_budget_spent():
                    break
                # A slow batch must not consume the review window of every
                # sibling. Smaller output also avoids giant truncated JSON.
                per_turn = min(300, max(30, left / (2 - turn)))
                flow.snapshot_protected()
                prefetched = None
                job = jobs_by_batch.get(batch_index) if not parallel_fallback and turn == 0 else None
                if job is not None and parallel_results is not None:
                    prefetched = first_parallel_reply if job is jobs[0] else next(parallel_results)
                    if prefetched is None:
                        parallel_fallback = True
                if prefetched is not None:
                    ok, reply = prefetched.ok, prefetched.text
                else:
                    ok, reply = flow.text_turn(prompt, per_turn,
                        'derived obligation extraction' if turn == 0 else 'derived obligation independent review',
                        system='You audit requirement contracts. Return one JSON object only.', spec_chars=len(prompt))
                replies.append(str(reply))
                rows, by_leaf, global_errors = (parse_obligation_details(reply, sources, ancestry) if ok else
                                                ([], {leaf: [] for leaf in ids}, ['request unavailable']))
                if turn == 0:
                    first_rows = rows
                    first_parseable = ok and bool(rows) and not any(error in global_errors for error in
                        ('invalid JSON object', 'invalid JSON envelope', 'missing obligations array'))
                    prompt += ('\nIndependently review and correct the SOURCE-GROUNDED CANDIDATES below. '
                               'Compare every source clause for omissions, invented rules, merged error branches '
                               'and lost format details. Return a COMPLETE corrected ledger in the same schema. '
                               'An omitted ancestor or leaf is a coverage gap.\nCANDIDATES:\n'
                               + json.dumps(first_rows, ensure_ascii=False)
                               + '\nVALIDATION ERRORS:\n'
                               + json.dumps(global_errors + [e for part in by_leaf.values() for e in part], ensure_ascii=False))
                    if len(prompt) > flow.codegen_context_chars():
                        global_errors.append('insufficient_context for independent review'); break
            # Commit candidate rows before approving a leaf. If merging fails,
            # exception recovery must not preserve a reviewed status without
            # the corresponding obligation records.
            if len(replies) == 2 and rows:
                flow.derived_obligations = [row for row in flow.derived_obligations if not set(row['applies_to']) & set(ids)] + rows
            for leaf in ids:
                errors = global_errors + by_leaf.get(leaf, [])
                warnings = [f'{source_id}: identical scenario outcome repeated in source'
                            for source_id in ancestry.get(leaf, [])
                            if repeated_source_text(sources.get(source_id, ''))]
                if leaf not in ancestry:
                    errors = [f'{leaf}: missing from requirement tree'] + errors
                if not first_parseable:
                    errors = ['initial extraction invalid or unavailable'] + errors
                if len(replies) != 2:
                    errors = ['independent review unavailable'] + errors
                reviewed = len(replies) == 2 and first_parseable and not errors and bool(rows)
                previous = flow.derived_obligation_status.get(leaf, {})
                flow.derived_obligation_status[leaf] = {
                    'status': 'reviewed' if reviewed else 'incomplete',
                    'errors': errors, 'warnings': warnings,
                    'attempts': previous.get('attempts', 0) + 1,
                    'candidate_obligations': sum(leaf in row['applies_to'] for row in rows)}
            # Sourced candidates remain visible as debt; only a fully audited
            # leaf can execute them or use them as repair authority.
            errors = global_errors + [e for part in by_leaf.values() for e in part]
            (path.parent / ('obligation-' + hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12] + '.json')).write_text(
                json.dumps({'leaves': ids, 'replies': replies, 'errors': errors,
                            'node_status': {leaf: flow.derived_obligation_status[leaf] for leaf in ids}},
                           ensure_ascii=False, indent=2))
            flow.metric('derived_obligations', nodes=ids,
                        reviewed=[leaf for leaf in ids if flow.derived_obligation_status[leaf]['status'] == 'reviewed'],
                        obligations=len(rows), errors=errors)
    finally:
        if parallel_results is not None:
            parallel_results.close()
        flow.derived_obligation_seconds = spent + time.monotonic() - started
        report = json.dumps({'version': 1, 'obligations': flow.derived_obligations,
            'nodes': flow.derived_obligation_status, 'seconds': flow.derived_obligation_seconds}, ensure_ascii=False, indent=2)
        path.write_text(report)
        design_dir = flow.output_dir / 'design'
        design_dir.mkdir(exist_ok=True)
        (design_dir / 'test-obligations.json').write_text(report)
        flow.snapshot_protected()
