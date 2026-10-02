"""Build-time prerequisite annotations for GitHub test recipes."""
import re


GITHUB_HELPER_CAPABILITIES = {
    'register': {'REQ-1-1-1'}, 'signIn': {'REQ-1-1-2'}, 'signOut': {'REQ-1-2'},
    'repo': {'REQ-3-1', 'REQ-3-3'}, 'organization': {'REQ-2-1-1'},
    'issue': {'REQ-5-1-1', 'REQ-5-1-2'},
    'pr': {'REQ-6-2-1', 'REQ-6-3-1'}, 'compare': {'REQ-6-2-1', 'REQ-6-2-2'},
    'canonicalOrganization': {'REQ-2-1-1'},
    'memberOrganization': {'REQ-2-1-2'},
    'canonicalRepo': {'REQ-3-1', 'REQ-3-3'},
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


