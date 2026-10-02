"""Public helper prerequisites for source-reviewed GitHub tests.

These are implementation prerequisites, never passing behavior verdicts.
Preparation cycles are built together and measured once their members exist.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from requirement_order import dependency_graph, topo_order


GITHUB_HELPER_CAPABILITIES = {
    'register': {'REQ-1-1-1'}, 'signIn': {'REQ-1-1-2'}, 'signOut': {'REQ-1-2'},
    'repo': {'REQ-3-1', 'REQ-3-3'}, 'organization': {'REQ-2-1-1'},
    'issue': {'REQ-5-1-1', 'REQ-5-1-2'},
    'pr': {'REQ-6-2-1', 'REQ-6-3-1'}, 'compare': {'REQ-6-2-1', 'REQ-6-2-2'},
    'canonicalOrganization': {'REQ-2-1-1'},
    'canonicalRepo': {'REQ-2-1-1', 'REQ-3-3'},
    'scenarioIssue': {'REQ-5-1-1', 'REQ-5-1-2'},
    'scenarioPr': {'REQ-6-2-1', 'REQ-6-3-1'},
}


def github_setup_features(body: str, helpers: str) -> set[str]:
    """Follow calls in the reviewed helper source, including organization -> repo."""
    starts = list(re.finditer(r'export\s+(?:async\s+)?function\s+(\w+)\s*\(', helpers))
    functions = {match.group(1): helpers[match.end():
                 starts[i + 1].start() if i + 1 < len(starts) else len(helpers)]
                 for i, match in enumerate(starts)}
    todo = re.findall(r'\bh\.(\w+)\s*\(', body)
    seen, result = set(), set()
    # The registration scenario explicitly ends by signing in with the new
    # email; its inline interaction has the same setup as the public helper.
    if re.search(r"h\.button\(\w+\s*,\s*['\"]Sign in['\"]\)\.click", body):
        result.add('REQ-1-1-2')
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        result.update(GITHUB_HELPER_CAPABILITIES.get(name, ()))
        source = functions.get(name, '')
        todo.extend(callee for callee in functions
                    if re.search(r'(?<![\w.])' + re.escape(callee) + r'\s*\(', source))
    return result


def annotate_github_setup(cases: dict, helpers: str) -> dict:
    for recipes in cases.values():
        for row in recipes:
            row['setup_requires'] = sorted(github_setup_features(row['body'], helpers)
                                           - {row['node_id']})
    return cases


def frozen_setup_dependencies(directory: Path, manifest: dict, tree: dict) -> dict[str, set[str]]:
    """Read verified metadata; infer omitted setup for older GitHub manifests.

    File-level unions are appropriate here: every case in a node spec must be
    ready. The caller must verify the immutable suite identity first.
    """
    if manifest.get('name') != 'hackathon--github':
        return {}
    known = {str(node['id']) for node in topo_order(tree)}
    plan = json.loads((directory / 'case-plan.json').read_text())
    helpers = (directory / 'helpers.ts').read_text()
    result = {owner: set(prerequisites) for owner, prerequisites in dependency_graph(tree).items()}
    for row in plan:
        if row.get('phase') != 'node':
            continue
        owner = row['node_id']
        if owner not in known or row['file'] != owner + '.spec.ts':
            raise ValueError('Invalid frozen setup owner')
        required = set(row.get('setup_requires', ())) | set(row.get('requires', ()))
        required |= github_setup_features((directory / row['file']).read_text(), helpers)
        if required - known:
            raise ValueError('Unknown frozen setup requirements: ' + ', '.join(sorted(required - known)))
        result.setdefault(owner, set()).update(required - {owner})
    return result


def setup_generation_order(tree: dict, setup: dict[str, set[str]]) -> tuple[list[dict], list[list[str]]]:
    """Build prerequisite owners first without making preparation cycles a deadlock."""
    ordered = topo_order(tree)
    if not any(setup.values()):
        return ordered, []
    nodes = {str(node['id']): node for node in ordered}
    rank = {node_id: i for i, node_id in enumerate(nodes)}
    graph = dependency_graph(tree)
    for owner, prerequisites in setup.items():
        if owner not in nodes or set(prerequisites) - nodes.keys():
            raise ValueError('Unknown setup dependency')
        graph[owner] = sorted(set(graph[owner]) | set(prerequisites), key=rank.__getitem__)
    done, active, result, cycles = set(), [], [], []

    def visit(owner):
        if owner in done:
            return
        if owner in active:
            cycle = active[active.index(owner):] + [owner]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        active.append(owner)
        for prerequisite in graph[owner]:
            visit(prerequisite)
        active.pop()
        done.add(owner)
        result.append(nodes[owner])

    for node in ordered:
        visit(str(node['id']))
    return result, cycles


def missing_setup(owner: str, setup: dict[str, set[str]], implemented: set[str]) -> set[str]:
    todo, required = list(setup.get(owner, ())), {owner}
    while todo:
        prerequisite = todo.pop()
        if prerequisite in required:
            continue
        required.add(prerequisite)
        todo.extend(setup.get(prerequisite, ()))
    return (required - {owner}) - implemented
