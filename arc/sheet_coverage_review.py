"""Specific assertion witnesses and remaining gaps, not a coverage percentage."""
from embedded_suites import requirements_digest


def coverage_review(tree, plan):
    nodes = {}
    def visit(node):
        if node.get('type') == 'ATOMIC':
            nodes[node['id']] = node
        for child in node.get('children', []):
            visit(child)
    visit(tree)
    checks = [
        ('REQ-1-2-2', 'rename dialog is prefilled with the last saved name', ['trim and save workbook name']),
        ('REQ-3-1-2', 'both paste entry points preserve significant whitespace and leading zeros', ['plain text paste preserves significant whitespace']),
        ('REQ-3-2-1', 'copy preserves exact ordinary values in both source and target', ['copy preserves exact ordinary text']),
        ('REQ-3-1-3', 'all exposed selected cells match the saved rectangle', ['complete rectangle replaces', 'drag replaces and persists']),
        ('REQ-4-1-1', 'inline formulas commit and cancel; two-dimensional aggregates preserve expression/results', ['inline grid formulas', 'two-dimensional aggregate input']),
        ('REQ-4-1-2', 'horizontal and vertical offsets adjust only the relevant axis', ['horizontal formula copy', 'vertical formula copy']),
        ('REQ-5-1-1', 'chronological sort distinguishes ISO offset dates from string comparison', ['date keys sort chronologically']),
        ('REQ-5-1-2', 'Before distinguishes ISO offset dates from string comparison', ['condition Before']),
        ('REQ-5-2-1', 'nonnumeric values are rejected through all four write entry points', ['numeric validation rejects nonnumeric']),
        ('REQ-5-3-1', 'column pivot restores all four field selections through reopening and another browser', ['column pivot reopens all saved']),
    ]
    reviewed = []
    for node_id, behavior, patterns in checks:
        witnesses = [{'file': row['file'], 'title': row['title']} for row in plan
                     if row['phase'] == 'node' and node_id in row['requires']
                     and any(pattern in row['title'] for pattern in patterns)]
        assert witnesses, (node_id, behavior)
        reviewed.append({'requirement_id': node_id, 'behavior': behavior,
                         'basis': nodes[node_id]['description'], 'exported_witnesses': witnesses,
                         'status': 'executable_source_reviewed', 'product_certification': False})
    return {
        'version': 1, 'requirements_sha256': requirements_digest(tree), 'official': False,
        'review_kind': 'source_and_test_infrastructure_review',
        'atomic_gate_coverage_complete': set(nodes) == {r['node_id'] for r in plan if r['phase'] == 'node'},
        'semantic_coverage_complete': False, 'product_runtime_certified': False,
        'nodes': {nid: {'exported_case_count': sum(r['phase'] == 'node' and r['node_id'] == nid for r in plan),
                        'complete_clause_coverage_claimed': False} for nid in nodes},
        'reviewed_behaviors': reviewed,
        'remaining_gaps': [
            {'requirements': ['REQ-1-2-1','REQ-1-2-2','REQ-1-3-1','REQ-2-1-1','REQ-2-1-3','REQ-2-1-4'],
             'behavior': 'valid lifecycle operations fail without partial records; retry succeeds',
             'status': 'requires_implementation_harness'},
            {'requirements': ['REQ-2-2-1','REQ-2-2-2','REQ-3-1-2','REQ-3-2-1','REQ-5-1-1','REQ-5-2-1'],
             'behavior': 'storage-failure rollback of structure, paste, move, sorting and rule modifications',
             'status': 'requires_implementation_harness'},
            {'requirements': ['REQ-3-1-1'], 'behavior': 'write-failure injection for encoded bodies, cross-origin APIs and WebSocket; arbitrary roleless error phrasing',
             'status': 'requires_interaction_adapter',
             'reason': 'The existing witness covers same-origin plain-text HTTP writes and visible alerts or recognized error text. Unavailable injection is a harness limitation, not product certification.'},
            {'requirements': ['REQ-1','REQ-2','REQ-3','REQ-4','REQ-5'],
             'behavior': 'full multi-workbook state snapshot and durability across real process restart',
             'status': 'requires_implementation_harness'},
            {'requirements': ['REQ-5-1-1','REQ-5-1-2'], 'behavior': 'supported date grammar and locale-specific input formats',
             'status': 'requires_requirement_clarification',
             'reason': 'The chronology witnesses use standard ISO date-times with explicit offsets; they do not require locale-specific parsing.'},
            {'requirements': ['REQ-3-2-2'], 'behavior': 'whether pivot refresh participates in undo history',
             'status': 'requires_requirement_clarification',
             'reason': 'Redo is now checked before refresh, avoiding a forced history policy.'},
        ],
        'interpretation': 'All 24 atomic gates exist. Listed assertions are specific witnesses; neither file counts nor reviewed status prove complete clause coverage.'}
