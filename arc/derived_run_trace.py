#!/usr/bin/env python3
"""Read-only snapshots of a local YAML-to-spec run and its review state."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue  # the writer may be in the middle of its final line
        if isinstance(value, dict):
            rows.append(value)
    return rows


def snapshot(output_dir: Path) -> dict:
    output_dir = output_dir.resolve()
    arc = output_dir / '.arc'
    suite = output_dir / 'derived-tests'
    marker = read_json(suite / 'suite-origin.json')
    if not marker:
        suites = sorted(output_dir.glob('derived-tests-*'))
        suite = next((path for path in suites if read_json(path / 'suite-origin.json').get('owner')
                      == 'octos-derived-suite-v1'), suite)
        marker = read_json(suite / 'suite-origin.json')
    review = suite / 'review'
    requirements = output_dir / 'requirements' / 'requirements.yaml'
    requirement_sha = hashlib.sha256(requirements.read_bytes()).hexdigest() if requirements.is_file() else None
    plan = read_json(review / 'plan.json')
    cases = read_json(review / 'cases.json')
    handoff = read_json(review / 'spec-handoff.json')
    coverage = read_json(arc / 'derived-coverage.json')
    mechanical = read_json(suite / 'mechanical-outcomes.json')
    audit = read_json(review / 'static-audit.json')
    metrics = read_jsonl(arc / 'flow-metrics.jsonl')
    usage = read_jsonl(arc / 'llm-usage.jsonl')
    by_label: dict[str, dict[str, int]] = defaultdict(lambda: {'requests': 0, 'prompt_tokens': 0,
                                                               'completion_tokens': 0, 'cache_hit_tokens': 0})
    for row in usage:
        label = str(row.get('label') or 'unknown')
        values = by_label[label]
        values['requests'] += int(row.get('requests') or 1)
        for source, destination in (('prompt_tokens', 'prompt_tokens'),
                                    ('completion_tokens', 'completion_tokens'),
                                    ('prompt_cache_hit_tokens', 'cache_hit_tokens')):
            values[destination] += int(row.get(source) or 0)
    stages = [row for row in metrics if row.get('kind') == 'derived_spec_stage']
    background = [row for row in metrics if row.get('kind') == 'derived_background']
    overflow = [row for row in metrics if row.get('kind') == 'derived_prompt_overflow']
    rejections: Counter[str] = Counter()
    for row in metrics:
        if row.get('kind') == 'derived_model_review':
            rejections.update({str(key): int(value) for key, value in
                               (row.get('remaining_invalid_categories') or {}).items()})
    nodes = [{key: row.get(key) for key in ('node_id', 'status', 'implementation_state',
                                           'candidate_covered', 'approved_behavior_cases',
                                           'approved_scenarios', 'unverified_scenarios', 'total',
                                           'test_admission')}
             for row in handoff.get('nodes', []) if isinstance(row, dict)]
    return {
        'observed_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'output_dir': str(output_dir), 'suite_dir': str(suite),
        'requirement_sha256': requirement_sha,
        # The suite marker hashes the parsed tree, not requirements.yaml bytes.
        'suite_tree_sha256': marker.get('requirements_sha256'),
        'terminal_state': read_json(arc / 'terminal-state.json').get('state'),
        'spec_files': len(list(suite.glob('*.spec.ts'))) if suite.is_dir() else 0,
        'mechanical_outcomes': dict(Counter(row.get('status', 'unknown') for row in mechanical.get('rows', []))),
        'plan_statuses': dict(Counter(row.get('status', 'unknown') for row in plan.get('targets', []))),
        'case_statuses': dict(Counter(row.get('status', 'unknown') for row in cases.get('cases', []))),
        'handoff_statuses': dict(Counter(row.get('status', 'unknown') for row in nodes)),
        'nodes': nodes,
        'coverage_totals': coverage.get('totals', {}),
        'execution': coverage.get('execution'),
        'static_audit_reasons': dict(Counter(row.get('reason', 'unknown') for row in audit.get('issues', []))),
        'stage_counts': dict(Counter(row.get('stage', 'unknown') for row in stages)),
        'background_outcomes': dict(Counter(row.get('outcome', 'unknown') for row in background)),
        'remaining_invalid_categories': dict(rejections),
        'prompt_overflows': [{key: row.get(key) for key in ('target_id', 'node_id', 'prompt_chars',
                                                            'limit_chars', 'phase_context_chars',
                                                            'source_description_chars', 'guidance_chars')}
                             for row in overflow],
        'model_usage_by_label': dict(by_label),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--watch', action='store_true', help='append snapshots until terminal state appears')
    parser.add_argument('--interval', type=float, default=30.0)
    parser.add_argument('--out', type=Path, help='write JSON for one snapshot, JSONL for --watch')
    args = parser.parse_args()
    if args.watch and (args.out is None or args.interval <= 0):
        parser.error('--watch requires --out and a positive --interval')
    while True:
        state = snapshot(args.output_dir)
        serialized = json.dumps(state, ensure_ascii=False, sort_keys=True)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            if args.watch:
                with args.out.open('a', encoding='utf-8') as stream:
                    stream.write(serialized + '\n')
            else:
                args.out.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            print(json.dumps(state, ensure_ascii=False, indent=2))
        if not args.watch or state['terminal_state']:
            return 0
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
