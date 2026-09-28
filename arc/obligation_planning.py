"""Independent, source-grounded obligation extraction for generated tests.

Semantic review is a planning decision, never evidence that the application passes.
Missing or invalid plans remain explicit gaps without withholding implementation.
"""
from __future__ import annotations

import hashlib
import json
import os
import time


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


def parse_obligations(reply, sources, ancestry):
    """Accept only exact source quotes, known applicability and stable IDs."""
    errors, result = [], []
    try:
        body = json.loads(reply)
    except (ValueError, TypeError):
        return [], ['invalid JSON object']
    if not isinstance(body, dict) or not isinstance(body.get('obligations'), list):
        return [], ['missing obligations array']
    for index, item in enumerate(body['obligations']):
        if not isinstance(item, dict):
            errors.append(f'obligation {index}: expected object'); continue
        owner, quote, outcome = (item.get(key) for key in ('requirement_id', 'quote', 'outcome'))
        applies = item.get('applies_to')
        if (not isinstance(owner, str) or owner not in sources or not isinstance(quote, str)
                or len(quote.strip()) < 12 or quote not in sources[owner]
                or not isinstance(outcome, str) or len(outcome.strip()) < 12
                or item.get('branch') not in {'success', 'rejection', 'mixed'}
                or not isinstance(applies, list) or not applies
                or any(not isinstance(leaf, str) or owner not in ancestry.get(leaf, []) for leaf in applies)):
            errors.append(f'obligation {index}: invalid quote, branch, outcome or applicability'); continue
        canonical = dict(requirement_id=owner, quote=quote, outcome=outcome,
                         branch=item['branch'], applies_to=sorted(set(applies)))
        canonical['id'] = 'OB-' + hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:20]
        if canonical not in result:
            result.append(canonical)
    for leaf in ancestry:
        if not any(leaf in row['applies_to'] and row['requirement_id'] == leaf for row in result):
            errors.append(f'{leaf}: no leaf-specific obligation')
        for parent in ancestry[leaf][:-1]:
            if len(sources[parent].strip()) >= 12 and not any(row['requirement_id'] == parent and leaf in row['applies_to'] for row in result):
                errors.append(f'{leaf}: missing inherited source {parent}')
    gaps = body.get('gaps', [])
    if not isinstance(gaps, list):
        errors.append('gaps must be an array')
    else:
        errors.extend('semantic gap: ' + str(gap)[:600] for gap in gaps)
    return result, errors


def applicable_obligations(flow, node_id):
    rows = getattr(flow, 'derived_obligations', None)
    if rows is None:
        rows = (getattr(flow, 'app_design_doc', None) or {}).get('obligations', [])
    return [row for row in rows if node_id in row.get('applies_to', [row.get('requirement_id')])]


def prepare_obligations(flow, nodes):
    """Two independent turns per small batch, bounded by the category window."""
    tree = getattr(flow, 'requirement_tree', None)
    if not tree or not nodes:
        return
    if not hasattr(flow, 'derived_obligation_status'):
        flow.derived_obligation_status = {}
        flow.derived_obligations = []
    pending = [n for n in nodes if flow.derived_obligation_status.get(str(n['id']), {}).get('status') != 'reviewed']
    if not pending:
        return
    path = flow.output_dir / 'derived-tests' / 'review' / 'obligations.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    for node in pending:
        flow.derived_obligation_status.setdefault(str(node['id']), {'status': 'incomplete', 'errors': ['not yet reviewed']})
    phase_left = getattr(flow, 'derived_preflight_deadline', float('inf')) - time.monotonic()
    cap = max(0, int(os.environ.get('OCTOS_ARC_OBLIGATION_SECONDS', str(max(2400, len(getattr(flow, 'derived_nodes', nodes)) * 90)))))
    spent = getattr(flow, 'derived_obligation_seconds', 0.0)
    deadline = time.monotonic() + max(0, min(cap - spent, phase_left * .30,
                                           flow.remaining() - flow.final_phase_reserve() - 600))
    started = time.monotonic()
    try:
        for offset in range(0, len(pending), 6):
            batch = pending[offset:offset + 6]
            ids = [str(n['id']) for n in batch]
            sources, ancestry = source_scope(tree, ids)
            for leaf in ids:
                flow.derived_obligation_status[leaf] = {'status': 'incomplete', 'errors': ['extraction unavailable']}
            if (deadline - time.monotonic() < 60 or flow.wound_down() or flow.review_budget_spent() or flow.derived_preflight_tokens_spent()
                    or not ancestry):
                continue
            prompt = ('Extract an exhaustive test obligation ledger from the original requirements below. '
                      'One independent hard outcome, format field/rule, state transition, error branch or persistence rule '
                      'per obligation. Preserve exact official schemas, values and HTTP status codes where given. '
                      'Separate valid and invalid workflows, and identify preconditions and unchanged state on failure '
                      'in outcome. Do not invent product rules. Include inherited parent constraints for applicable leaves; '
                      'for scope-only parents record their scope restriction, not a new product feature. '
                      'Return ONLY {"obligations":[{"requirement_id":"source ID","applies_to":["leaf ID"],'
                      '"quote":"exact original substring","branch":"success|rejection|mixed",'
                      '"outcome":"concrete action and observable result"}],"gaps":[]}. '
                      'Record unresolved contradictions or unsupported obligations in gaps; do not silently omit them. '
                      'No application code or generated tests are evidence.\nSOURCES:\n' + json.dumps(sources, ensure_ascii=False)
                      + '\nLEAF ANCESTRY:\n' + json.dumps(ancestry))
            if len(prompt) > flow.codegen_context_chars():
                for leaf in ids:
                    flow.derived_obligation_status[leaf]['errors'] = ['insufficient_context']
                continue
            flow.start_derived_designs(ids, 'extracting business test obligations')
            replies, rows, errors = [], [], []
            for turn in range(2):
                left = deadline - time.monotonic()
                if left < 30 or flow.derived_preflight_tokens_spent() or flow.wound_down() or flow.review_budget_spent():
                    break
                flow.snapshot_protected()
                ok, reply = flow.text_turn(prompt, min(600, left / (2 - turn)),
                    'derived obligation extraction' if turn == 0 else 'derived obligation independent review',
                    system='You audit requirement contracts. Return one JSON object only.', spec_chars=len(prompt))
                replies.append(str(reply))
                rows, errors = parse_obligations(reply, sources, ancestry) if ok else ([], ['request unavailable'])
                if turn == 0:
                    prompt += ('\nIndependently review and correct this proposal. Compare every source clause against '
                               'the ledger for omissions, invented rules, merged error branches and lost format details. '
                               'Return a complete corrected ledger in the same schema.\nPROPOSAL:\n' + str(reply)
                               + '\nSTRUCTURAL ERRORS:\n' + json.dumps(errors))
                    if len(prompt) > flow.codegen_context_chars():
                        errors.append('insufficient_context for independent review'); break
            reviewed = len(replies) == 2 and not errors and bool(rows)
            for leaf in ids:
                flow.derived_obligation_status[leaf] = {'status': 'reviewed' if reviewed else 'incomplete',
                                                       'errors': errors or ([] if reviewed else ['independent review unavailable'])}
            # Keep failed batches as explicit gaps, not partially trusted obligations.
            if reviewed:
                flow.derived_obligations = [row for row in flow.derived_obligations if not set(row['applies_to']) & set(ids)] + rows
            (path.parent / ('obligation-' + hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12] + '.json')).write_text(
                json.dumps({'leaves': ids, 'replies': replies, 'errors': errors}, ensure_ascii=False, indent=2))
            flow.metric('derived_obligations', nodes=ids, status='reviewed' if reviewed else 'incomplete',
                        obligations=len(rows), errors=errors)
    finally:
        flow.derived_obligation_seconds = spent + time.monotonic() - started
        report = json.dumps({'version': 1, 'obligations': flow.derived_obligations,
            'nodes': flow.derived_obligation_status, 'seconds': flow.derived_obligation_seconds}, ensure_ascii=False, indent=2)
        path.write_text(report)
        design_dir = flow.output_dir / 'design'
        design_dir.mkdir(exist_ok=True)
        (design_dir / 'test-obligations.json').write_text(report)
        flow.snapshot_protected()
