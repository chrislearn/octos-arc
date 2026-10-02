"""Reviewed UI prerequisites for Sheet recipes; no model or product API.

The graph's document-stable topological order is the actual node-generation
order. A case using a later capability belongs in final acceptance. Shared
read/navigation helpers do not imply that their target feature is complete.
"""
import re

def sheet_features(body):
    features=set()
    helpers={
        'blank':['REQ-1-2-1'], 'edit':['REQ-3-1-1'], 'paste':['REQ-3-1-2'],
        'sourceData':['REQ-1-2-1','REQ-3-1-2'], 'range':['REQ-3-1-3'], 'selection':['REQ-3-1-3'],
        'formula':['REQ-4-1-1'], 'validation':['REQ-5-2-1','REQ-3-1-3'], 'numericRule':['REQ-5-2-1','REQ-3-1-3'],
        'prepareValidation':['REQ-5-2-1','REQ-3-1-3'],
        'pivot':['REQ-5-3-1','REQ-3-1-3','REQ-2-1-1'], 'csv':['REQ-1-3-2'], 'renameWorkbook':['REQ-1-2-2'],
        'filterValues':['REQ-5-1-2'], 'condition':['REQ-5-1-2'], 'visibleRows':['REQ-5-1-2'],
    }
    for helper,ids in helpers.items():
        if re.search(r'\bh\.'+helper+r'\s*\(',body):features.update(ids)
    if re.search(r'''["'`]=''',body) or '\\t=' in body or '\\n=' in body:
        features.add('REQ-4-1-1')
    patterns={
        'REQ-2-1-1':r'''h\.button\([^;\n]*?["']Add worksheet["']''',
        'REQ-2-1-2':r'h\.tab\([^;\n]*?\)\.click\(',
        'REQ-2-1-3':r'''h\.sheetMenu\([^;\n]*?["']Rename["']''',
        'REQ-2-1-4':r'''h\.sheetMenu\([^;\n]*?["']Delete["']''',
        'REQ-2-2-1':r'''h\.structure\([^;\n]*?["']row["']''',
        'REQ-2-2-2':r'''h\.structure\([^;\n]*?["']column["']''',
        'REQ-3-2-1':r'Control\+[cx]|["\'](?:Copy|Cut)["\']',
        'REQ-3-2-2':r'Control\+[zy]|["\'](?:Undo|Redo)["\']',
        'REQ-5-1-1':r'''h\.data\([^;\n]*?["']Sort range["']''',
        'REQ-5-1-2':r'''h\.data\([^;\n]*?["'](?:Create|Clear) filter["']''',
        'REQ-5-2-1':r'''h\.data\([^;\n]*?["']Data validation["']''',
        'REQ-5-3-1':r'''h\.data\([^;\n]*?["']Create pivot table["']''',
    }
    for node,pattern in patterns.items():
        if re.search(pattern,body):features.add(node)
    if 'REQ-4-1-1' in features and 'Control+c' in body:features.add('REQ-4-1-2')
    return features

def partition_sheet_cases(cases,tree):
    from requirement_order import topo_order
    order={n['id']:i for i,n in enumerate(topo_order(tree))}
    grouped={}
    for file,recipes in cases.items():
        for original in recipes:
            row=dict(original);node=row['node_id']
            required=set(row['requires'])|sheet_features(row['body'])
            row['requires']=[node]+sorted(required-{node})
            target=file
            if row['phase']=='node' and any(order[rid]>order[node] for rid in required):
                row['phase']='integration';target='INTEGRATION-deferred-'+node.removeprefix('REQ-')
            grouped.setdefault(target,[]).append(row)
    return grouped
