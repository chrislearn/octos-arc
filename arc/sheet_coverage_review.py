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
        ('REQ-5-1-1', 'ISO date-only sorting keeps equal keys stable and records intact; typed comparison is not certified', ['date keys sort chronologically']),
        ('REQ-5-1-2', 'Before excludes equal/later ISO date-only values and empty cells', ['condition Before']),
        ('REQ-5-2-1', 'nonnumeric values are rejected through all four write entry points', ['numeric validation rejects nonnumeric']),
        ('REQ-5-3-1', 'column pivot restores all four field selections through reopening and another browser', ['column pivot reopens all saved']),
        ('REQ-1-3-1', 'complete CSV import preserves multi-letter columns and rows beyond the initial viewport', ['complete import exposes AA']),
        ('REQ-2-1-4', 'four-sheet deletion activates a genuinely adjacent survivor', ['third of four sheets']),
        ('REQ-3-1-1', 'failed inline Enter retains both last successful grid value and formula bar before retry', ['failed grid Enter']),
        ('REQ-3-1-3', 'one pointer move persists a full rectangle and delayed responses retain newer successful edits', ['one pointer move', 'late selection response']),
        ('REQ-4-2-2', 'row-zero references and malformed decimal tokens preserve stable errors and recover dependents', ['audit regression: =']),
        ('REQ-4-1-1', 'zero arithmetic remains a visible numeric value with correct dependent results', ['zero arithmetic']),
        ('REQ-5-1-1', 'non-ISO parseable dates sort chronologically; formula keys retain expressions and full records', ['unambiguous non-ISO dates', 'numeric formula results sort']),
        ('REQ-5-1-1', 'failed sorting preserves order and reports failure before successful retry', ['failed sort keeps']),
        ('REQ-5-1-2', 'failed filter application retains the saved predicate before retry', ['failed filter apply']),
        ('REQ-5-2-1', 'exact context-sensitive number messages and immediate modified bounds', ['single-cell number error', 'modified inclusive number bounds']),
        ('REQ-5-2-1', 'failed first save, rule modification and deletion retain prior saved constraints before retry', ['failed first rule save', 'failed rule modify', 'failed rule delete']),
        ('REQ-5-3-1', 'SUM/AVERAGE Refresh rejects sources without numbers atomically and accepts a numeric-zero retry', ['refresh with no numeric values']),
        ('REQ-5-3-1', 'AVERAGE includes formula zero as a numeric record', ['AVERAGE includes formula zero']),

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
             'behavior': 'real storage-failure rollback of structure, paste, move, sorting and rule modifications; HTTP rejection for sorting and rules is covered',
             'status': 'requires_implementation_harness'},
            {'requirements': ['REQ-3-1-1'], 'behavior': 'write-failure injection for WebSocket, local storage, changing endpoints and arbitrary roleless error phrasing',
             'status': 'requires_interaction_adapter',
             'reason': 'The witness learns successful HTTP write endpoints and supports encoded and cross-origin requests; error discovery uses visible alerts or recognized text. Unrelated background writes or changing endpoints need an implementation adapter. Unavailable injection is a harness limitation, not product certification.'},
            {'requirements': ['REQ-1','REQ-2','REQ-3','REQ-4','REQ-5'],
             'behavior': 'full multi-workbook state snapshot and durability across real process restart',
             'status': 'requires_implementation_harness'},
            {'requirements': ['REQ-5-1-1','REQ-5-1-2'], 'behavior': 'remaining date grammar, timezone and locale-specific formats',
             'status': 'requires_requirement_clarification',
             'reason': 'Non-ISO English month witnesses now distinguish chronological from lexical order in both directions. Remaining date grammars and timezone/locale choices are unspecified; offset date-times are not imposed by gates.'},
            {'requirements': ['REQ-3-2-2'], 'behavior': 'whether pivot refresh participates in undo history',
             'status': 'requires_requirement_clarification',
             'reason': 'Redo is now checked before refresh, avoiding a forced history policy.'},
        ],
        'interpretation': 'All 24 atomic gates exist. Listed assertions are specific witnesses; neither file counts nor reviewed status prove complete clause coverage.'}
