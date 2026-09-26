"""Conservative checks for hazards in the task-neutral Express scaffold.

Only literal route declarations and an unmistakable single-page layout are
examined. Other applications keep their own routing semantics.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_ROUTE = re.compile(r"\bapp\.(?P<method>get|post|put|patch|delete|all)\s*\(\s*"
                    r"(?P<quote>['\"`])(?P<path>/[^'\"`\r\n]+)(?P=quote)")
_ANCHOR = re.compile(r'<a\b[^>]*>', re.I)
_HREF = re.compile(r'\bhref\s*=\s*[\'\"](/[^\'\"]+)[\'\"]', re.I)
_CLASS_VALUE = re.compile(
    r'\bclass(?:Name)?\s*=\s*(?:[\'\"](?P<plain>[^\'\"]*)[\'\"]|\{\s*[`\'\"](?P<jsx>[^`\'\"]*)[`\'\"]\s*\})',
    re.I,
)
_TAILWIND_IMPORT = re.compile(r'@import\s+[\'\"]tailwindcss(?:[\'\"/;])', re.I)
_UTILITY_PREFIX = re.compile(
    r'^(?:(?:sm|md|lg|xl|2xl|hover|focus|focus-visible|active|disabled|group-hover):)*'
    r'(?:bg|text|border|rounded|shadow|ring|font|leading|tracking|p[trblxy]?|m[trblxy]?|'
    r'w|h|min-w|max-w|min-h|max-h|gap|space-[xy]|grid-cols|col-span|items|justify|content|'
    r'overflow|z|top|right|bottom|left|inset|translate-[xy]|scale|opacity|duration|ease)-'
)
_UTILITY_WORDS = {
    'block', 'hidden', 'inline', 'inline-block', 'flex', 'inline-flex', 'grid', 'contents',
    'relative', 'absolute', 'fixed', 'sticky', 'grow', 'shrink', 'truncate', 'antialiased',
}


def _client_side_link(page: str) -> bool:
    for tag in _ANCHOR.findall(page):
        if not re.search(r'\bdata-(?:link|route|nav)\b', tag, re.I):
            continue
        href = _HREF.search(tag)
        if not href:
            continue
        path = href.group(1).split('?', 1)[0].split('#', 1)[0]
        if path not in ('/', '') and not path.startswith(('/api/', '//')) and not Path(path).suffix:
            return True
    return False


def _uncompiled_utility_css(frontend: Path, manifest: dict) -> str | None:
    """Find strong evidence that utility classes will be inert in the browser."""
    source = frontend / 'src'
    if not source.is_dir():
        return None
    code_files = [p for p in source.rglob('*') if p.is_file()
                  and p.suffix in {'.html', '.js', '.mjs', '.jsx', '.ts', '.tsx', '.vue'}]
    css_files = [p for p in source.rglob('*') if p.is_file() and p.suffix in {'.css', '.scss'}]
    try:
        code = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in code_files)
        css = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in css_files)
    except OSError:
        return None
    tokens: set[str] = set()
    for match in _CLASS_VALUE.finditer(code):
        for token in (match.group('plain') or match.group('jsx') or '').split():
            token = token.strip('`\'"{}(),')
            if token in _UTILITY_WORDS or _UTILITY_PREFIX.match(token):
                tokens.add(token)
    # One or two utility-like application class names prove nothing. A broad
    # cluster is the generated-but-uncompiled Tailwind failure this check owns.
    if len(tokens) < 10:
        return None
    dependencies = {}
    for group in ('dependencies', 'devDependencies', 'optionalDependencies'):
        if isinstance(manifest.get(group), dict):
            dependencies.update(manifest[group])
    has_tailwind = 'tailwindcss' in dependencies
    imports_tailwind = bool(_TAILWIND_IMPORT.search(css))
    if has_tailwind and imports_tailwind:
        return None
    # Preserve a deliberately hand-written utility sheet when most of the
    # detected tokens have literal selectors in the bundled source CSS.
    defined = sum(1 for token in tokens if re.search(
        r'\.' + re.escape(token) + r'(?=[\s,.#:{>+~\[])', css))
    if defined >= max(6, len(tokens) * 3 // 4):
        return None
    sample = ', '.join(sorted(tokens)[:8])
    if has_tailwind:
        remedy = 'import "tailwindcss" from a source CSS file so the existing Vite plugin emits the utilities'
    else:
        remedy = ('add the pinned tailwindcss/@tailwindcss/vite dependencies and import "tailwindcss", '
                  'or replace the utility tokens with CSS rules that are actually bundled')
    return (f'frontend: found {len(tokens)} utility-style class tokens ({sample}) but no active utility CSS; '
            f'{remedy}')


def _generic_entry(project: Path) -> bool:
    try:
        return 'Generic web entry' in (project / 'backend/server.js').read_text(encoding='utf-8')[:200]
    except OSError:
        return False


# Installed by the generic template; their module-level state is infrastructure.
_TASK_NEUTRAL_BACKEND = {'backend/lib/arc.js', 'backend/lib/store.js', 'backend/lib/collection.js',
                         'backend/lib/errors.js', 'backend/lib/query.js'}


def backend_sources(project: Path, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """backend/routes and backend/lib JavaScript by workspace-relative path.
    `overrides` (path -> new text) previews a write before it happens."""
    sources: dict[str, str] = {}
    for folder in ('backend/routes', 'backend/lib'):
        base = project / folder
        for file in sorted(base.rglob('*.js')) if base.is_dir() else []:
            if 'node_modules' in file.parts:
                continue
            try:
                sources[file.relative_to(project).as_posix()] = file.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
    for rel, text in (overrides or {}).items():
        if rel.startswith(('backend/routes/', 'backend/lib/')) and rel.endswith('.js'):
            sources[rel] = text
    return sources


def _segments(route: str) -> list[str]:
    return [':' if piece.startswith(':') else '*' if piece.startswith('*') else '?' if '{' in piece else piece
            for piece in route.split('/') if piece]


def _covers(earlier: str, later: str) -> bool:
    """Mirror of blueprints/arc-runtime.js: `earlier` matches every request for `later`."""
    a, b = _segments(earlier), _segments(later)
    if '?' in a or '?' in b:
        return False
    for index, piece in enumerate(a):
        if piece == '*':
            return len(b) > index
        if index >= len(b) or (piece != ':' and piece != b[index]) or (piece == ':' and b[index] == '*'):
            return False
    return len(a) == len(b)


def static_route_conflicts(sources: dict[str, str]) -> list[dict]:
    """Duplicate and shadowed literal app.METHOD routes in registration order
    (the entry requires backend/routes/*.js sorted by file name). Same fields
    and wording as the runtime registry in blueprints/arc-runtime.js."""
    return _static_routes(sources)[1]


def static_routes(sources: dict[str, str]) -> list[dict]:
    """Literal app.METHOD routes in registration order: method, path, file, line."""
    return _static_routes(sources)[0]


def route_table_note(project: Path, max_routes: int = 80) -> str:
    """Prompt block: which file owns each registered API route."""
    routes = static_routes(backend_sources(project))
    if not routes:
        return ""
    rows = [f"{r['method']} {r['path']} -> {r['file']}:{r['line']}" for r in routes[:max_routes]]
    more = f"\n(+{len(routes) - max_routes} more)" if len(routes) > max_routes else ""
    return ("Registered API routes (owner file:line). Change an existing route in its owner file; a reply that "
            "registers the same METHOD and path again is rejected:\n" + "\n".join(rows) + more + "\n")


def _static_routes(sources: dict[str, str]) -> tuple[list[dict], list[dict]]:
    routes: list[dict] = []
    conflicts: list[dict] = []
    files = sorted(rel for rel in sources if rel.startswith('backend/routes/') and rel.count('/') == 2)
    for rel in files:
        text = sources[rel]
        for match in _ROUTE.finditer(text):
            route = match.group('path')
            if '${' in route:
                continue
            method = match.group('method').upper()
            line = text.count('\n', 0, match.start()) + 1
            for prior in routes:
                if prior['method'] != method:
                    continue
                where, owner = f'{rel}:{line}', f"{prior['file']}:{prior['line']}"
                base = {'method': method, 'path': route, 'file': rel, 'line': line,
                        'owner_file': prior['file'], 'owner_line': prior['line']}
                if _segments(prior['path']) == _segments(route):
                    conflicts.append({**base, 'kind': 'duplicate', 'message': (
                        f"{method} {route} ({where}) is already registered as {method} {prior['path']} at {owner}; "
                        f"Express only runs the first handler. Keep one handler and change it in {prior['file']}.")})
                    break
                if _covers(prior['path'], route):
                    conflicts.append({**base, 'kind': 'shadowed', 'message': (
                        f"{method} {route} ({where}) never runs: {method} {prior['path']} at {owner} matches it "
                        f"first; register it before that route.")})
                    break
            routes.append({'method': method, 'path': route, 'file': rel, 'line': line})
    return routes, conflicts


def _conflict_key(conflict: dict) -> tuple:
    # Line numbers move with every edit; the conflict itself does not.
    return (conflict['kind'], conflict['method'], tuple(_segments(conflict['path'])),
            conflict['file'], conflict['owner_file'])


def introduced_route_conflicts(project: Path, files: dict[str, str]) -> list[dict]:
    """Conflicts that writing `files` (path -> new text) would add to the app."""
    if not any(rel.startswith('backend/routes/') for rel in files):
        return []
    before = {_conflict_key(c) for c in static_route_conflicts(backend_sources(project))}
    return [c for c in static_route_conflicts(backend_sources(project, files)) if _conflict_key(c) not in before]


def runtime_route_report(project: Path, timeout: float = 20.0) -> dict | None:
    """The route table Express itself registered (routers, template strings and
    helpers included), from the generic entry's ARC_ROUTE_DUMP mode. None when
    the entry, its runtime helper or installed dependencies are missing."""
    backend = project / 'backend'
    node = shutil.which('node')
    try:
        entry = (backend / 'server.js').read_text(encoding='utf-8')
    except OSError:
        return None
    if (not node or "require('./lib/arc')" not in entry or not (backend / 'lib/arc.js').is_file()
            or not (backend / 'node_modules/express').is_dir()):
        return None
    with tempfile.TemporaryDirectory(prefix='arc-routes-') as scratch:
        dump = Path(scratch) / 'routes.json'
        env = dict(os.environ, ARC_ROUTE_DUMP=str(dump), ARC_DATA_DIR=str(Path(scratch) / 'data'),
                   ARC_EXTRA_PORTS='0', PORT='0')
        env.pop('ARC_TEST_HOOKS', None)
        try:
            subprocess.run([node, 'server.js'], cwd=backend, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=timeout, check=False)
            report = json.loads(dump.read_text(encoding='utf-8'))
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    if not isinstance(report, dict) or not isinstance(report.get('routes'), list):
        return None
    report.setdefault('conflicts', [])
    return report


_NAMED_WILDCARD = re.compile(r"\bapp\.(?:get|post|put|patch|delete|all)\s*\(\s*['\"`][^'\"`]*/\*(?P<name>[A-Za-z_]\w*)")
_POSITIONAL_PARAM = re.compile(r"\breq\.params\s*\[\s*['\"]?0['\"]?\s*\]")


def express5_param_issues(sources: dict[str, str]) -> list[str]:
    """Express 5 names every wildcard: '/files/*path' fills req.params.path
    (an array of segments), and req.params[0] is always undefined."""
    issues: list[str] = []
    for rel, text in sources.items():
        wildcard = _NAMED_WILDCARD.search(text)
        positional = _POSITIONAL_PARAM.search(text)
        if wildcard and positional:
            line = text.count('\n', 0, positional.start()) + 1
            name = wildcard.group('name')
            issues.append(f"{rel}:{line}: reads req.params[0], but Express 5 names wildcards: a route ending in "
                          f"'/*{name}' puts the matched segments in req.params.{name} (an array; join('/') "
                          f"for a path). req.params[0] is undefined, so every such request misses.")
    return issues


_MODULE_STATE = re.compile(r"^(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
                           r"(?:new\s+(?:Map|Set|WeakMap|WeakSet)\s*\(|\[\s*\]|\{\s*\})", re.M)


def module_state_issues(sources: dict[str, str]) -> list[str]:
    """Empty module-level containers are in-memory state: the store reset the
    harness runs between tests cannot clear them, and a restart silently does."""
    issues: list[str] = []
    for rel, text in sources.items():
        if rel in _TASK_NEUTRAL_BACKEND or 'onReset' in text:
            continue
        for match in _MODULE_STATE.finditer(text):
            line = text.count('\n', 0, match.start()) + 1
            name = match.group('name')
            issues.append(f"{rel}:{line}: module-level state `{name}` survives store resets and is lost on restart; "
                          f"persist it through lib/store or lib/collection, or register "
                          f"require('../lib/store').onReset(() => /* clear {name} */).")
            break
    return issues


def scaffold_warnings(project: Path, runtime: bool = False) -> list[str]:
    """Defects worth fixing that never stop a build or a measurement: they go
    to the repair context next to the failures they may explain."""
    if not _generic_entry(project):
        return []
    sources = backend_sources(project)
    report = runtime_route_report(project) if runtime else None
    conflicts = report['conflicts'] if report is not None else static_route_conflicts(sources)
    warnings = [str(conflict.get('message')) for conflict in conflicts if conflict.get('message')]
    return warnings + express5_param_issues(sources) + module_state_issues(sources)


def scaffold_issues(project: Path) -> list[str]:
    """Return actionable build blockers only for applications using our generic entry."""
    if not _generic_entry(project):
        return []
    issues: list[str] = []
    frontend = project / 'frontend'
    try:
        manifest = json.loads((frontend / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return issues  # the build validates the manifest separately
    if not isinstance(manifest, dict) or not isinstance(manifest.get('arc'), dict):
        spa = False
    else:
        spa = manifest['arc'].get('spa') is True
    utility_issue = _uncompiled_utility_css(frontend, manifest)
    if utility_issue:
        issues.append(utility_issue)
    source = frontend / 'src'
    html = list(source.rglob('*.html')) if source.is_dir() else []
    if not spa and len(html) == 1 and html[0].name == 'index.html':
        try:
            page = html[0].read_text(encoding='utf-8', errors='replace')
            scripts = '\n'.join(file.read_text(encoding='utf-8', errors='replace')
                                for file in source.rglob('*') if file.is_file()
                                and file.suffix in {'.js', '.mjs', '.jsx', '.ts', '.tsx', '.vue'}
                                and 'shared' not in file.relative_to(source).parts)
        except OSError:
            return issues
        framework_router = (re.search(r"['\"]react-router(?:-dom)?['\"]", scripts)
                            and re.search(r'\b(?:BrowserRouter|createBrowserRouter)\b', scripts))
        if framework_router or (('history.pushState' in page + scripts or 'startRouter(' in page + scripts)
                                and _client_side_link(page + scripts)):
            issues.append('frontend: client-side links use history.pushState but only index.html exists; '
                          'set frontend/package.json arc.spa=true for direct loads and refreshes, or add HTML pages')
    return issues
