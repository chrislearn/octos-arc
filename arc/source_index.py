"""Bounded, advisory source relationships; never a substitute for a compiler."""
import hashlib
import posixpath
import re


class SourceIndex:
    def __init__(self, sources):
        self.sources = dict(sources)
        self.versions = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in self.sources.items()}
        self.dependencies = {p: set() for p in self.sources}
        for path, source in self.sources.items():
            for name in re.findall(r'''(?:from\s*|import\s*|require\s*\(\s*)['"](\.[^'"]+)['"]''', source):
                base = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
                candidates = [base] + [base + ext for ext in ('.js', '.jsx', '.ts', '.tsx', '/index.js', '/index.ts', '/index.tsx')]
                target = next((p for p in candidates if p in self.sources), None)
                if target:
                    self.dependencies[path].add(target)

    def related(self, paths):
        paths = set(paths) & self.sources.keys()
        return paths | {q for p in paths for q in self.dependencies[p]} | {
            p for p, deps in self.dependencies.items() if deps & paths}

    def affected(self, paths):
        """Transitive callers, unlike the bounded display's one-hop context."""
        found = set(paths)
        while True:
            expanded = found | {p for p, deps in self.dependencies.items() if deps & found}
            if expanded == found:
                return found
            found = expanded

    def render(self, paths, limit=5000):
        lines = ['Source relationships (heuristic; verify callers before changing contracts):']
        for path in sorted(self.related(paths)):
            source = self.sources[path]
            symbols = re.findall(r'(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function|class|const)\s+(\w+)', source)
            props = re.findall(r'<([A-Z]\w*)\b([^<>]*?)/?>', source)
            calls = [name + '(' + ','.join(re.findall(r'\b(\w+)\s*=', attrs)) + ')' for name, attrs in props]
            lines.append(f'{path}: imports={",".join(sorted(self.dependencies[path]))}; symbols={",".join(symbols[:20])}; components={",".join(calls[:20])}')
        return '\n'.join(lines)[:limit]


def failure_groups(grouped, targets):
    """Merge concrete identical runtime errors or explicit feature ownership.

    Generic assertion/timeouts alone never demonstrate a shared root cause.
    Unknown ownership stays in one fallback group rather than forcing one turn
    per test. This is scheduling evidence, not a diagnosis.
    """
    groups = []
    for node, outcomes in grouped.items():
        keys = {'file:' + p for p in targets.get(node, ())}
        for result in outcomes:
            diagnostic = '\n'.join([result.message or '', *(result.action_errors or [])])
            for line in diagnostic.splitlines():
                match = re.search(r'(?:ReferenceError: .+ is not defined|TypeError: .+|SyntaxError: .+|ERR_MODULE_NOT_FOUND.*)', line)
                if match:
                    keys.add('runtime:' + re.sub(r'\x1b\[[0-9;]*m', '', match.group()).strip())
        if not keys:
            keys = {'unknown'}
        merged = {node}
        rest = []
        # Repeat to handle a bridge between two previously separate groups.
        pending = groups
        while pending:
            old_ids, old_keys = pending.pop(0)
            if keys & old_keys:
                merged |= old_ids
                keys |= old_keys
                pending.extend(rest)
                rest = []
            else:
                rest.append((old_ids, old_keys))
        groups = rest + [(merged, keys)]
    return [sorted(ids) for ids, _ in sorted(groups, key=lambda g: (-len(g[0]), sorted(g[0])))]

