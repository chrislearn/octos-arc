#!/usr/bin/env python3
"""Create a labeled diagnostic subset without modifying official inputs.

This is NOT a full-task benchmark score. Preserve ancestor descriptions and
test support files, and reject subsets missing atomic dependencies.
"""
import argparse
import copy
from pathlib import Path
import shutil
import yaml

from main import load_requirement_tree
from requirement_order import topo_order


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    parser.add_argument('tests', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--ids', nargs='+', required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must not already exist')
    tree = load_requirement_tree(args.task)
    nodes = {str(node['id']): node for node in topo_order(tree)}
    wanted = set(args.ids)
    if not wanted <= nodes.keys():
        parser.error('Unknown atomic node')
    for node_id in wanted:
        if any(dep in nodes and dep not in wanted for dep in nodes[node_id].get('dependencies', [])):
            parser.error('Subset omits an atomic dependency')
    def select(node):
        node = copy.deepcopy(node)
        if node.get('type') == 'ATOMIC':
            return node if node['id'] in wanted else None
        node['children'] = [child for item in node.get('children', []) if (child := select(item))]
        return node if node['children'] else None
    selected = select(tree)
    selected['name'] += ' — diagnostic subset only'
    shutil.copytree(args.task, args.output / 'task')
    (args.output / 'task/requirements.yaml').write_text(yaml.safe_dump(selected, allow_unicode=True, sort_keys=False))
    for path in args.tests.rglob('*'):
        if not path.is_file() or (path.name.endswith('.spec.ts') and path.name not in {f'{node_id}.spec.ts' for node_id in wanted}):
            continue
        target = args.output / 'tests' / path.relative_to(args.tests)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    print(f'Diagnostic subset: {len(wanted)}/{len(nodes)} atomic requirements; not a full-task benchmark')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
