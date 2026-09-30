#!/usr/bin/env python3
"""Read-only performance evidence audit; never starts a model or application."""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(rows):
    fields = ('prompt_tokens', 'completion_tokens', 'reasoning_tokens', 'prompt_cache_hit_tokens')
    result = {key: sum(row.get(key, 0) for row in rows) for key in fields}
    result['requests'] = len(rows)
    result['elapsed_seconds_sum'] = sum(row['elapsed_ms'] for row in rows) / 1000
    result['uncached_prompt_tokens'] = result['prompt_tokens'] - result['prompt_cache_hit_tokens']
    result['non_reasoning_completion_tokens'] = result['completion_tokens'] - result['reasoning_tokens']
    if rows:
        result['cache_ratio'] = result['prompt_cache_hit_tokens'] / result['prompt_tokens']
        result['reasoning_completion_ratio'] = result['reasoning_tokens'] / result['completion_tokens']
        result['elapsed_seconds_median'] = statistics.median(row['elapsed_ms'] / 1000 for row in rows)
        result['prompt_token_range'] = [min(row['prompt_tokens'] for row in rows), max(row['prompt_tokens'] for row in rows)]
        if len(rows) > 2:
            elapsed = [row['elapsed_ms'] for row in rows]
            result['descriptive_pearson_elapsed_output'] = statistics.correlation(elapsed, [row['completion_tokens'] for row in rows])
            result['descriptive_pearson_elapsed_input'] = statistics.correlation(elapsed, [row['prompt_tokens'] for row in rows])
            result['descriptive_pearson_elapsed_uncached_input'] = statistics.correlation(elapsed, [row['prompt_tokens'] - row['prompt_cache_hit_tokens'] for row in rows])
    return result


def collect(run, source):
    sys.path.insert(0, str(source / 'arc'))
    import main
    from llm_proxy import force_write_decision, prompt_fingerprint

    arc = run / '.arc'
    usage = read_rows(arc / 'llm-usage.jsonl')
    flow = read_rows(arc / 'flow-metrics.jsonl')
    ledger = read_rows(arc / 'request-ledger.jsonl')
    events = read_rows(arc / 'octos-events.jsonl')
    context = {row['request_id']: row for row in ledger if row['event'] == 'context'}
    first = [row for row in usage if row['phase'] == 'implement' and not re.search(r'\((?:protocol|complete|context|retry)', row['label'])]
    protocol = [row for row in flow if row['kind'] == 'turn' and any(word in row['label'] for word in ('protocol correction', 'complete blocks retry'))]
    groups = {f'{phase}_{"codegen" if codegen else "tools"}': summarize([row for row in usage if row['phase'] == phase and row['codegen'] == codegen])
              for phase, codegen in [('implement', True), ('repair', True), ('repair', False)]}
    node_usage = collections.defaultdict(list)
    for row in usage:
        node_usage[re.match(r'REQ-\d+-\d+-\d+', row['label']).group()].append(row)
    measurements = {row['node_id']: {'passed': row['passed'], 'total': row['total']}
                    for row in flow if row['kind'] == 'acceptance' and row.get('scope') == 'node'}
    nodes = []
    for node_id, rows in node_usage.items():
        stats = summarize(rows)
        nodes.append({'node_id': node_id, 'model_requests': stats['requests'],
                      'model_elapsed_seconds': stats['elapsed_seconds_sum'],
                      'prompt_tokens': stats['prompt_tokens'], 'completion_tokens': stats['completion_tokens'],
                      'reasoning_tokens': stats['reasoning_tokens'], 'cache_ratio': stats['cache_ratio'],
                      'latest_node_measurement': measurements.get(node_id)})
    previous, changes = {}, []
    for row in usage:
        names = context[row['request_id']]['tools']
        key = row['turn_serial']
        if key in previous and names != previous[key]:
            changes.append({key: row[key] for key in ('request_id', 'turn_serial', 'label', 'prompt_tokens', 'prompt_cache_hit_tokens', 'prefix_shared_chars')} | {'before': previous[key], 'after': names})
        previous[key] = names

    names = ['edit_file', 'grep', 'list_dir', 'read_file', 'write_file']
    probe = {'model': 'deepseek-v4-flash', 'messages': [{'role': 'system', 'content': 'fixed'}, {'role': 'user', 'content': 'active node'}],
             'tools': [{'type': 'function', 'function': {'name': name, 'parameters': {'type': 'object'}}} for name in names]}
    before = json.dumps(probe).encode()
    limited = json.loads(force_write_decision(before, 10, 12, 200))
    after = copy.deepcopy(probe)
    after['messages'].append({'role': 'assistant', 'tool_calls': [{'id': '1', 'type': 'function', 'function': {'name': 'edit_file', 'arguments': '{}'}}]})
    restored = json.loads(force_write_decision(json.dumps(after).encode(), 11, 12, 201))
    different_schema = copy.deepcopy(probe)
    different_schema['tools'] = different_schema['tools'][:-1]
    probes = {'initial_tools': names, 'budget_tools': [x['function']['name'] for x in limited['tools']],
              'after_write_tools': [x['function']['name'] for x in restored['tools']],
              'text_fingerprint_ignores_tool_schema': prompt_fingerprint(before, '')[0] == prompt_fingerprint(json.dumps(different_schema).encode(), '')[0]}

    suite = arc / 'frozen-tests/hackathon--sheet'
    design = json.loads((arc / 'design/app.json').read_text())
    helper = (suite / 'helpers.ts').read_text()
    hypothetical = re.sub(r'^export \{ expect \};\n', '', helper, flags=re.M)
    helper_rows, design_rows = [], []
    for path in sorted(suite.glob('REQ-*.spec.ts')):
        node = path.name.removesuffix('.spec.ts')
        spec = path.read_text()
        references = set(main._IDENT.findall(spec))
        current = main.trim_helper_to_references(helper, references)
        estimate = len(main.trim_helper_to_references(hypothetical, references)) + len('export { expect };\n')
        helper_rows.append({'node_id': node, 'current_helper_chars': len(current), 'hypothetical_helper_chars': estimate, 'hypothetical_saving_chars': len(current) - estimate})
        stable, active = main.app_design_blocks(design, spec, 24000, requirement_ids=[node])
        design_rows.append({'node_id': node, 'stable_chars': len(stable), 'stable_utf8_bytes': len(stable.encode()),
                            'stable_sha256': hashlib.sha256(stable.encode()).hexdigest(), 'active_chars': len(active), 'spec_file_chars': len(spec)})
    compact = json.dumps(design, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    tools = [row['params'] for row in events if row.get('method') == 'tool/completed']
    received_ids = {row['request_id'] for row in ledger if row['event'] == 'request_received'}
    attempted_ids = {row['request_id'] for row in ledger if row['event'] == 'attempt_started'}
    hashes = {str(path.relative_to(run)): hashlib.sha256(path.read_bytes()).hexdigest() for path in
              [arc / name for name in ('llm-usage.jsonl', 'flow-metrics.jsonl', 'request-ledger.jsonl', 'octos-events.jsonl')] + [suite / 'helpers.ts', arc / 'design/app.json', suite / 'suite-origin.json']}
    code_hashes = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                   [source / 'arc' / name for name in ('main.py', 'llm_proxy.py', 'context_ledger.py', 'source_index.py', 'web_stack.py', 'web_checks.py')]}
    return {'schema': 'octos.arc.performance-review.v1', 'collected_at': datetime.now(timezone.utc).isoformat(),
            'run': str(run), 'source_for_code_probes': str(source), 'source_artifact_sha256': hashes, 'code_sha256': code_hashes,
            'all': summarize(usage), 'groups': groups, 'nodes': nodes, 'first_implementation': summarize(first),
            'usage_models': dict(collections.Counter(row['model'] for row in usage)), 'usage_reasoning_modes': dict(collections.Counter(row['mode'] for row in usage)),
            'usage_request_ids_unique': len({row['request_id'] for row in usage}) == len(usage),
            'token_arithmetic_valid': all(row['total_tokens'] == row['prompt_tokens'] + row['completion_tokens'] and row['reasoning_tokens'] <= row['completion_tokens'] for row in usage),
            'ledger_events': dict(collections.Counter(row['event'] for row in ledger)), 'received_without_attempt_ids': sorted(received_ids - attempted_ids),
            'pending_requests_at_proxy_stop': [row.get('pending_requests') for row in ledger if row['event'] == 'proxy_stopped'],
            'protocol_retry_turns': [{'label': row['label'], 'elapsed_seconds': row['elapsed_seconds']} for row in protocol],
            'protocol_retry_elapsed_seconds_sum': sum(row['elapsed_seconds'] for row in protocol),
            'tools': {'count': len(tools), 'counts_by_name': dict(collections.Counter(row['tool_name'] for row in tools)),
                      'reported_execution_ms_sum': sum(row.get('duration_ms', 0) for row in tools)},
            'context_duplicate_read_chars_sum': sum(row.get('duplicate_read_chars', 0) for row in context.values()),
            'same_turn_tool_set_changes': changes, 'offline_probes': probes,
            'design': {'entities': len(design['data_model']), 'compact_chars': len(compact), 'compact_utf8_bytes': len(compact.encode()),
                       'node_blocks': design_rows, 'stable_blocks_identical': len({row['stable_sha256'] for row in design_rows}) == 1},
            'helpers': {'file_chars': len(helper), 'node_estimates': helper_rows,
                        'hypothetical_saving_chars_median': statistics.median(row['hypothetical_saving_chars'] for row in helper_rows)},
            'implementation_context': [row for row in flow if row['kind'] == 'implementation_context'],
            'codegen_outcomes': dict(collections.Counter(row['outcome'] for row in flow if row['kind'] == 'codegen')),
            'run_metadata': json.loads((run / 'run-metadata.json').read_text()),
            'infrastructure_incident': json.loads((run / 'binary-replacement-incident.json').read_text())}


def review(evidence):
    tests = []

    def check(name, passed, detail):
        tests.append({'name': name, 'status': 'passed' if passed else 'failed', 'detail': detail})

    overall = evidence['all']
    groups_reconcile = all(sum(group[key] for group in evidence['groups'].values()) == overall[key]
                           for key in ('requests', 'prompt_tokens', 'completion_tokens', 'reasoning_tokens', 'prompt_cache_hit_tokens'))
    nodes_reconcile = (sum(node['model_requests'] for node in evidence['nodes']) == overall['requests']
                       and all(sum(node[key] for node in evidence['nodes']) == overall[key]
                               for key in ('prompt_tokens', 'completion_tokens', 'reasoning_tokens'))
                       and abs(sum(node['model_elapsed_seconds'] for node in evidence['nodes']) - overall['elapsed_seconds_sum']) < 0.001)
    check('132 completed reported upstream requests', overall['requests'] == 132 and evidence['usage_request_ids_unique'] and groups_reconcile and nodes_reconcile, overall['requests'])
    check('tokens reconcile without double-counting reasoning', evidence['token_arithmetic_valid'] and overall['prompt_tokens'] == 3674067 and overall['completion_tokens'] == 621296 and overall['reasoning_tokens'] == 469246, overall)
    check('cache count independently recomputed', overall['prompt_cache_hit_tokens'] == 2745600, overall['cache_ratio'])
    first = evidence['first_implementation']
    check('first implementation subset excludes context and correction requests', first['requests'] == 10 and first['prompt_cache_hit_tokens'] == 69632 and first['prompt_tokens'] == 301592, first)
    check('protocol retry duration selects unique outer turns', len(evidence['protocol_retry_turns']) == 6 and abs(evidence['protocol_retry_elapsed_seconds_sum'] - 1322.502) < 0.001, evidence['protocol_retry_turns'])
    check('tool events reconcile', evidence['tools']['count'] == 143 and evidence['tools']['counts_by_name']['read_file'] == 105 and evidence['tools']['reported_execution_ms_sum'] == 2225, evidence['tools'])
    check('two schema oscillations accompany zero input-cache reads', len(evidence['same_turn_tool_set_changes']) == 2 and all(row['prompt_cache_hit_tokens'] == 0 for row in evidence['same_turn_tool_set_changes']), evidence['same_turn_tool_set_changes'])
    probes = evidence['offline_probes']
    check('current code reproduces tool-set oscillation', 'list_dir' in probes['initial_tools'] and 'list_dir' not in probes['budget_tools'] and probes['initial_tools'] == probes['after_write_tools'], probes)
    check('text fingerprint has a confirmed tool-schema blind spot', probes['text_fingerprint_ignores_tool_schema'], probes['text_fingerprint_ignores_tool_schema'])
    check('frozen shared design is identical across 24 node specimens', len(evidence['design']['node_blocks']) == 24 and evidence['design']['stable_blocks_identical'] and all(row['stable_chars'] == 11853 for row in evidence['design']['node_blocks']), evidence['design']['stable_blocks_identical'])
    check('all 24 helper specimens currently take the full-file fallback', len(evidence['helpers']['node_estimates']) == 24 and all(row['current_helper_chars'] == evidence['helpers']['file_chars'] == 11383 for row in evidence['helpers']['node_estimates']), evidence['helpers']['file_chars'])
    check('run is explicitly incomplete because of infrastructure interruption', evidence['run_metadata']['exit_code'] == 130 and evidence['infrastructure_incident']['replacement_stdio_cli_exit_code'] == 2, evidence['infrastructure_incident']['first_affected_node'])
    return {'schema': 'octos.arc.performance-review-checks.v1', 'passed': all(row['status'] == 'passed' for row in tests),
            'checks': tests, 'scope': 'offline arithmetic, data provenance and pure-function probes; no product acceptance or model A/B experiment',
            'runtime_code_changed': False, 'model_requests_started': 0,
            'independent_totals_reconciled': groups_reconcile and nodes_reconcile}


def review_documents(directory):
    """Validate the saved report and review links without changing either document."""
    report = directory / 'report.md'
    review_record = directory / 'review.md'
    failures = []
    for document in (report, review_record):
        for target in re.findall(r'\]\(([^)]+)\)', document.read_text()):
            if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                continue
            match = re.match(r'^(.*?)(?::(\d+))?$', target)
            path = Path(match[1])
            if not path.is_absolute():
                path = directory / path
            if not path.is_file() or (match[2] and int(match[2]) > len(path.read_text().splitlines())):
                failures.append({'document': document.name, 'target': target})
    return {'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
            'manual_review': review_record.name, 'local_links_valid': not failures,
            'invalid_local_links': failures}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    evidence = collect(args.run.resolve(), args.source.resolve())
    findings = review(evidence)
    findings.update(review_documents(Path(__file__).resolve().parent))
    findings['passed'] = findings['passed'] and findings['local_links_valid']
    args.output.mkdir(parents=True, exist_ok=True)
    for name, document in [('evidence.json', evidence), ('review-checks.json', findings)]:
        (args.output / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': findings['passed'], 'checks': len(findings['checks']), 'output': str(args.output)}, ensure_ascii=False))
    raise SystemExit(0 if findings['passed'] else 1)
