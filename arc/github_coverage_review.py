"""Reproducible semantic coverage review, distinct from file coverage."""
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
        ('REQ-1-1-1', 'homepage provides direct Sign up and rejected registration clears passwords', ['homepage Sign up', 'rejected registration retains nonsensitive']),
        ('REQ-1-1-2', 'failed login retains identifier clears password and permits a valid retry', ['rejected login clears password']),
        ('REQ-1-1-3', 'invalid recovery code or confirmation clears both passwords without changing credentials', ['rejected recovery clears both passwords']),
        ('REQ-2-1-1', 'public organization identity and repository-only navigation survive reload', ['public organization shows both identities']),
        ('REQ-2-1-2', 'prescribed account-menu organization entry shows both identities and member navigation', ['account menu organization entry']),
        ('REQ-2-2-3', 'People refuses visitors and nonmembers while preserving ordinary member reads', ['People denies visitors']),
        ('REQ-2-2-1', 'Teams list and detail refuse visitors and nonmembers while preserving member reads', ['Teams list and detail deny']),
        ('REQ-3-1', 'personal search links use exact names separately from visible owner metadata', ['personal repository results expose exact names']),
        ('REQ-2-1-2', 'display names are rejected as identifiers and field errors remain independent', ['display names cannot replace identifiers']),
        ('REQ-4-3-2', 'legal slash branches retain selection and nested file context after reload', ['legal slash branch survives']),
        ('REQ-4-4', 'slash branch writes edits and commit history preserve main', ['slash branch web writes']),
        ('REQ-6-2-2', 'comparison controls have exact Base and Compare accessible names', ['comparison controls have the exact']),
        ('REQ-6-3-4', 'Request changes accepts an omitted optional summary and persists the decision', ['Request changes accepts an omitted']),
        ('REQ-6-3-1', 'global search and downstream files issues and PRs use the same organization repository', ['global search file issue and PR navigation']),
        ('REQ-1-1-1', 'legal username and email lengths are accepted', ['username legal length', 'email legal length']),
        ('REQ-2-2-1', 'team length boundary and duplicate relationship rejection persist', ['team legal length', 'duplicate team']),
        ('REQ-5-2-2', 'Write has independent title/description save authority', ['Write saves title']),
        ('REQ-5-3-2', 'Triage has positive label authority', ['Triage toggles']),
        ('REQ-1-1-1', 'isolated invalid inputs and duplicate email cannot partially create an account', ['isolated registration rejection', 'duplicate email retains']),
        ('REQ-1-1-2', 'minimum and maximum compliant passwords and trimmed email produce persistent sign-in', ['registration accepts password boundary']),
        ('REQ-2-2-2', 'valid parent changes persist without altering the original parent team relationship', ['valid parent change persists']),
        ('REQ-2-2-4', 'last Owner refusal retains People and team membership', ['last Owner removal']),
        ('REQ-5-4', 'Triage has positive status authority without Write content authority', ['Triage closes and reopens']),
        ('REQ-6-1', 'independent visitor proves persisted check setter separately from account menu', ['persists setter']),
        ('REQ-6-3-4', 'Request changes persists exact summary and status', ['Request changes submission']),
        ('REQ-1-3', 'rejected password preserves old credentials and rejects the candidate', ['missing current password and mismatch']),
        ('REQ-2-3', 'private team grant changes access, preserves outsider denial and is idempotent', ['live team grant admits its member']),
        ('REQ-4-2-1', 'file history excludes unrelated commits; branch order persists', ['branch history keeps newest-first']),
        ('REQ-4-4', 'path/message boundaries and unauthorized creation preserve history', ['file path is rejected', 'overlong trimmed', 'cannot commit files']),
        ('REQ-5-2-3', 'blank comment preserves loaded discussion; Read/Triage cannot comment', ['blank comment adds no article', 'cannot publish a comment']),
        ('REQ-5-3-3', 'PR milestone add/remove, cross-repository exclusion and role denial', ['PR milestone toggles', 'cannot change a PR milestone']),
        ('REQ-6-2-1', 'Open excludes Draft/Closed and a PR after a real merge', ['Open filter excludes Draft Closed']),
        ('REQ-6-2-2', 'comparison shows the seeded commit message or exact compare-only commit count', ['Base/Compare comboboxes']),
        ('REQ-6-3-1', 'PR compare-only commits exclude the seeded base commit and its ancestor after reload', ['visitor PR overview, commits']),
        ('REQ-6-3-4', 'author, Draft, Read and Triage cannot persist review decisions', ['cannot persist a review decision']),
        ('REQ-6-5', 'Write/Read/Triage cannot merge; failed required check blocks an approved PR', ['cannot merge or change the base branch', 'failed required check']),
    ]
    reviewed = []
    for node_id, behavior, patterns in checks:
        witnesses = [{'file': r['file'], 'title': r['title']} for r in plan
                     if r['phase'] == 'node' and node_id in r['requires']
                     and any(pattern in r['title'] for pattern in patterns)]
        assert witnesses, (node_id, behavior)
        reviewed.append({'requirement_id': node_id, 'behavior': behavior,
                         'basis': nodes[node_id]['description'], 'exported_witnesses': witnesses,
                         'status': 'executable_source_reviewed', 'product_certification': False})
    gaps = [
        {'requirements': ['REQ-1-1-1','REQ-2-2-1','REQ-2-2-4'], 'behavior': 'remaining empty-input and team legal-length-1 witnesses, same-name teams across organizations, last-Owner direct grants and unrelated-organization/personal-repository preservation', 'status': 'requires_additional_witnesses', 'reason': 'Isolated invalid inputs and team/People rollback now have witnesses; they do not certify every legal boundary or every untouched relationship.'},
        {'requirements': ['ROOT', 'REQ-2-2', 'REQ-3-1', 'REQ-4-4', 'REQ-6-5'], 'behavior': 'server authorization independent of hidden UI; real storage failure, restart and rollback, including member removal across organization/team/grant stores and initialized repository creation',
         'status': 'requires_implementation_harness',
         'reason': 'Needs legitimate request construction and target process/storage control. No private API or filesystem schema is imposed.'},
        {'requirements': ['REQ-6-5'], 'behavior': 'conflicts, confirmation-time concurrent head changes and both merge parents',
         'status': 'requires_extended_commit_witness',
         'reason': 'Eligibility and real base bytes do not certify the complete commit graph or concurrent revalidation.'},
    ]
    return {'version': 1, 'requirements_sha256': requirements_digest(tree), 'official': False,
            'review_kind': 'source_and_test_infrastructure_review',
            'atomic_gate_coverage_complete': set(nodes) == {r['node_id'] for r in plan if r['phase'] == 'node'},
            'semantic_coverage_complete': False, 'product_runtime_certified': False,
            'nodes': {nid: {'exported_case_count': sum(r['phase'] == 'node' and r['node_id'] == nid for r in plan),
                           'complete_clause_coverage_claimed': False} for nid in nodes},
            'reviewed_behaviors': reviewed, 'remaining_gaps': gaps,
            'interpretation': 'All 47 atomic gates exist. Witnesses check specific behavior; they do not prove every clause. Remaining gaps are explicit and never skipped or counted as passed.'}
