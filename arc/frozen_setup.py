"""Schedule implementation prerequisites supplied with a test suite."""
from __future__ import annotations

import json
from pathlib import Path

from requirement_order import dependency_graph, topo_order


def frozen_setup_dependencies(directory: Path, tree: dict) -> dict[str, set[str]]:
    """Use declared case metadata; suite selection belongs to the command."""
    plan_path = directory / 'case-plan.json'
    if not plan_path.is_file():
        return {}
    plan = json.loads(plan_path.read_text())
    # Suites without preparation metadata use the ordinary requirement order.
    if not any('setup_requires' in row for row in plan):
        return {}
    result = {owner: set(prerequisites) for owner, prerequisites in dependency_graph(tree).items()}
    for row in plan:
        if row.get('phase') == 'node':
            owner = row['node_id']
            required = set(row.get('setup_requires', ())) | set(row.get('requires', ()))
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
