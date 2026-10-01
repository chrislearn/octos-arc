"""Make retained final assertions executable in the exported requirement gates.

Every witness owns fresh data and runs at the last capability it exercises.
It is not an alias of an integration file, and cannot pull a later UI into an
early node. The original primary requirement remains explicit provenance.
"""
from copy import deepcopy
from requirement_order import topo_order

def complete_node_coverage(cases, tree):
    order = {node['id']: i for i, node in enumerate(topo_order(tree))}
    result = deepcopy(cases)
    for file, recipes in cases.items():
        if not file.startswith('INTEGRATION-'):
            continue
        for source in recipes:
            owner = max(source['requires'], key=order.__getitem__)
            witness = deepcopy(source)
            witness.update(node_id=owner, phase='node',
                           title='context ' + source['node_id'] + ': ' + source['title'],
                           origin_node_id=source['node_id'],
                           origin_file=file + '.spec.ts', origin_title=file + ': ' + source['title'])
            if source.get('fixture'):
                fixture = source['fixture'] + '-node'
                witness['fixture'] = fixture
                witness['source_fixture'] = source['fixture']
                witness['body'] = witness['body'].replace("'" + source['fixture'] + "'", "'" + fixture + "'")
            result.setdefault(owner, []).append(witness)
    return result
