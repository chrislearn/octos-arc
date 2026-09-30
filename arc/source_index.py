"""Bounded, advisory source relationships; never a substitute for a compiler."""
import hashlib
import posixpath
import re
from urllib.parse import urlsplit


class SourceIndex:
    def __init__(self, sources):
        self.sources = dict(sources)
        self.versions = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in self.sources.items()}
        self.dependencies = {p: set() for p in self.sources}
        for path, source in self.sources.items():
            for name in re.findall(r'''(?:from\s*|import\s*|require\s*\(\s*)['"](\.[^'"]+)['"]''', source):
                base = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
                extensions = ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.json', '.css')
                candidates = [base] + [base + ext for ext in extensions] + [base + '/index' + ext for ext in extensions]
                target = next((p for p in candidates if p in self.sources), None)
                if target:
                    self.dependencies[path].add(target)

    def related(self, paths):
        paths = set(paths) & self.sources.keys()
        return paths | {q for p in paths for q in self.dependencies[p]} | {
            p for p, deps in self.dependencies.items() if deps & paths}

    def navigation_owners(self, evidence):
        """Resolve literal JSX routes to imported renderers for source quoting.

        Dynamic routers, ambiguous tags/imports and external failure pages
        remain unknown. This selects context, never a reachability verdict.
        """
        from route_evidence import frontend_route_index, _jsx_tags
        urls = [m[2] for m in re.finditer(r"\.goto\(\s*(['\"`])([^'\"`\r\n]*)\1\s*[,)]", evidence)]
        urls += re.findall(r'(?m)^\s*Page URL at failure: (https?://[^\s]+)', evidence)
        paths = set()
        for url in urls:
            if '${' in url or url.startswith('//'):
                continue
            try:
                parsed = urlsplit(url)
            except ValueError:
                continue
            if parsed.scheme and parsed.scheme not in {'http', 'https'}:
                continue
            if parsed.netloc and parsed.hostname not in {'localhost', '127.0.0.1', '0.0.0.0', '::1'}:
                continue
            if parsed.path.startswith('/') and '..' not in parsed.path.split('/'):
                paths.add(parsed.path.rstrip('/') or '/')
        if not paths:
            return set()
        # Build tooling can use import() without participating in the browser
        # route tree. Include client sources and their static dependencies,
        # rather than treating every frontend build script as a router.
        browser_paths = {p for p in self.sources if p.startswith('frontend/src/') or
                         p.startswith('frontend/') and posixpath.basename(p) in
                         {'App.jsx', 'App.tsx', 'main.js', 'main.jsx', 'main.ts', 'main.tsx'}}
        pending = list(browser_paths)
        while pending:
            path = pending.pop()
            for dep in self.dependencies[path] - browser_paths:
                if dep.startswith('frontend/'):
                    browser_paths.add(dep)
                    pending.append(dep)
        table = frontend_route_index({p: self.sources[p] for p in browser_paths})
        if not table['complete']:
            return set()
        found = set()
        for row in table['declarations']:
            if (row['path'].rstrip('/') or '/') not in paths:
                continue
            source = self.sources[row['file']]
            tags = [(start, end) for start, end, name, kind, attrs in _jsx_tags(source)
                    if name == 'Route' and kind in {'open', 'self'}
                    and source.count('\n', 0, start) + 1 == row['line']]
            if len(tags) != 1:
                continue
            start, end = tags[0]
            element = re.search(r'\belement\s*=\s*\{\s*<([A-Z]\w*)\s*/>\s*\}', source[start:end])
            if not element:
                continue
            imports = re.findall(r'(?m)^\s*import\s+' + re.escape(element[1]) +
                                 r'''\s+from\s+['"](\.[^'"\r\n]+)['"]''', source)
            if len(imports) != 1:
                continue
            base = posixpath.normpath(posixpath.join(posixpath.dirname(row['file']), imports[0]))
            candidates = [base] + [base + ext for ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs')]
            candidates += [base + '/index' + ext for ext in ('.js', '.jsx', '.ts', '.tsx')]
            targets = {p for p in candidates if p in self.sources}
            if len(targets) == 1:
                found |= targets
        return found

    def contract_context(self, paths, owners=()):
        """Required owners and dependencies, without pulling every routed page.

        Composition roots are always visible. Their shared/layout dependencies
        travel too, but unrelated page imports do not expand the whole app.
        Dependencies of actual edit targets and explicit contract owners are
        followed transitively; missing/external imports remain absent.
        """
        hubs = {p for p in self.sources if posixpath.basename(p) in
                {'App.jsx', 'App.tsx', 'app.js', 'router.js', 'main.jsx', 'main.tsx'}}
        counts = {}
        for deps in self.dependencies.values():
            for dep in deps:
                counts[dep] = counts.get(dep, 0) + 1
        common = {dep for hub in hubs for dep in self.dependencies[hub]
                  if counts.get(dep, 0) > 1 or 'layout' in posixpath.basename(dep).lower()}
        found = ((set(paths) - hubs) | set(owners) | common) & self.sources.keys()
        pending = list(found)
        while pending:
            path = pending.pop()
            for dep in self.dependencies[path] - found - hubs:
                found.add(dep)
                pending.append(dep)
        return found | hubs

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
