"""Reproduce local input-size and compiler-coverage measurements; no model calls."""
import argparse
import json
import time
from pathlib import Path

from layered_tests import compile_basic, digest, helper_excerpt
from main import load_requirement_tree, topo_order
from scenario_tests import HELPERS, suite_fixtures


def measure():
    node = {'id': 'REQ-1', 'description': 'The home page has a button named “Open 1”.', 'scenarios': []}
    fixtures = suite_fixtures([node])
    source, gap = compile_basic(node, fixtures, '')
    assert source and not gap
    helper = HELPERS.read_text()
    short = helper_excerpt(helper, source)
    evidence = {'sources': {'REQ-1': node['description']}, 'fixtures': str(fixtures), 'source': source, 'helper': helper}
    compact = {**evidence, 'helper': short}
    whole_chars = len(json.dumps(evidence, ensure_ascii=False))
    short_chars = len(json.dumps(compact, ensure_ascii=False))
    tasks = []
    for name in ('smoke--counter', 'smoke--dice', 'hackathon--sheet', 'hackathon--github', 'arc-bench-web--keep'):
        path = Path(__file__).resolve().parents[1] / 'tasks' / name
        tree = load_requirement_tree(path)
        nodes = topo_order(tree)
        fixtures = suite_fixtures(nodes)
        started = time.perf_counter()
        gaps = [n['id'] for n in nodes if not compile_basic(n, fixtures, '')[0]]
        tasks.append({'task': name, 'requirements_sha256': digest(tree), 'nodes': len(nodes),
                      'candidates': len(nodes) - len(gaps), 'gaps': gaps,
                      'compile_seconds': round(time.perf_counter() - started, 6)})
    return {'method': 'Same minimal entry evidence; replace full helper with exact function closure and all module globals.',
            'compiler_sha256': digest(Path(__file__).resolve().parents[1].joinpath('layered_tests.py').read_bytes()),
            'helper_sha256': digest(HELPERS.read_bytes()), 'fixture': node, 'spec_chars': len(source),
            'full_helper_chars': len(helper), 'short_helper_chars': len(short),
            'helper_reduction_percent': round(100 * (1 - len(short) / len(helper)), 2),
            'full_evidence_chars': whole_chars, 'short_evidence_chars': short_chars,
            'evidence_reduction_percent': round(100 * (1 - short_chars / whole_chars), 2),
            'candidate_coverage': tasks,
            'limitations': ['Characters are not tokens or model latency.',
                            'Candidates have not been independently model-reviewed or executed.',
                            'A candidate is one minimal entry, not full basic or business coverage.',
                            'Unrepresentable entries block a node; no empty-suite pass.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True)
    path = Path(parser.parse_args().evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = measure()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
