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

    def planned_artifact_candidates(self, artifacts, limit=12):
        """Bounded heuristic mapping of planned URLs/files to current source.

        An exact quoted route wins; a same-named route/page file is only a
        candidate. This is for self-audit context, never a completion verdict.
        """
        found = set()
        for artifact in artifacts:
            value = str(artifact.get('path') or '')
            if value in self.sources:
                found.add(value)
                continue
            if not value.startswith('/') or len(value) < 2:
                continue
            exact = [path for path, source in self.sources.items()
                     if re.search(r'''['"`]''' + re.escape(value) + r'''['"`]''', source)]
            if exact:
                found.update(exact)
                continue
            parts = [p.lower() for p in value.split('/') if p and not p.startswith(':')]
            if not parts:
                continue
            stem = parts[-1]
            if stem in {'api', 'app'}:
                continue
            found.update(path for path in self.sources
                         if posixpath.basename(path).split('.', 1)[0].lower() == stem)
        return sorted(found)[:limit]

    def render(self, paths, limit=5000):
        lines = ['Source relationships (heuristic; verify callers before changing contracts):']
        for path in sorted(self.related(paths)):
            source = self.sources[path]
            symbols = re.findall(r'(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function|class|const)\s+(\w+)', source)
            signatures = re.findall(r'function\s+\w+\s*\([^)]{0,180}\)', source)
            routes = re.findall(r'''\b(?:app|router)\.(?:get|post|put|patch|delete)\(\s*['"][^'"]+['"]''', source)
            requests = re.findall(r'''\bfetch\(\s*['"`][^'"`\n]{1,120}['"`]''', source)
            props = re.findall(r'<([A-Z]\w*)\b([^<>]*?)/?>', source)
            calls = [name + '(' + ','.join(re.findall(r'\b(\w+)\s*=', attrs)) + ')' for name, attrs in props]
            lines.append(f'{path}: imports={",".join(sorted(self.dependencies[path]))}; symbols={",".join(symbols[:20])}; components={",".join(calls[:20])}')
            if signatures or routes or requests:
                lines.append('  contracts: ' + '; '.join(signatures[:6] + routes[:10] + requests[:10]))
        return '\n'.join(lines)[:limit]


def failure_groups(grouped, targets):
    """Merge concrete identical runtime errors, locator gates, or ownership.

    Generic assertion/timeouts alone never demonstrate a shared root cause.
    An identical role/name locator does: several scenarios blocked on the same
    named navigation control are usually downstream victims of one missing or
    incorrectly exposed entry point.  This is stronger than a shared helper
    frame, which says only where the test library noticed the timeout.
    Unknown ownership does not demonstrate a shared cause. The group selector
    can still fit several independent groups in one bounded turn.
    This is scheduling evidence, not a diagnosis.
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
                # Playwright call logs render the exact contract that blocked,
                # for example: waiting for getByRole('button', { name: /my account/i }).first().
                # Keep role/name (or the corresponding text/label selector),
                # discard only first/last/nth selection so downstream tests of
                # the same shared gate land in one repair group.
                clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
                locator = re.search(
                    r"waiting for (getBy(?:Role|Text|Label|Placeholder|TestId)\(.{1,240}?\))"
                    r"(?:\.(?:first|last|nth)\([^)]*\))?(?:\s|$)", clean)
                if locator:
                    keys.add('locator:' + re.sub(r'\s+', ' ', locator.group(1)).strip())
        if not keys:
            keys = {'unknown:' + node}
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


def select_repair_groups(groups, visits, slots):
    """Fit group coverage into existing round limits, without adding calls."""
    ordered = sorted(groups, key=lambda ids: (visits.get(tuple(ids), 0), -len(ids), ids))
    slots = max(1, slots)
    count = max(1, (len(groups) + slots - 1) // slots)
    selected = ordered[:count]
    for group in selected:
        visits[tuple(group)] = visits.get(tuple(group), 0) + 1
    return sorted({node for group in selected for node in group})
