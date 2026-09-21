"""Conservative checks for hazards in the task-neutral Express scaffold.

Only literal route declarations and an unmistakable single-page layout are
examined. Other applications keep their own routing semantics.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROUTE = re.compile(r"\bapp\.(?P<method>get|post|put|patch|delete)\s*\(\s*"
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


def _matches(dynamic: str, literal: str) -> bool:
    left, right = dynamic.strip('/').split('/'), literal.strip('/').split('/')
    return len(left) == len(right) and any(piece.startswith(':') for piece in left) and all(
        a.startswith(':') or a == b for a, b in zip(left, right))


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


def scaffold_issues(project: Path) -> list[str]:
    """Return actionable errors only for applications using our generic entry."""
    server = project / 'backend/server.js'
    try:
        if 'Generic web entry' not in server.read_text(encoding='utf-8')[:200]:
            return []
    except OSError:
        return []

    issues: list[str] = []
    routes = project / 'backend/routes'
    prior: dict[str, list[tuple[str, str, int]]] = {}
    for file in sorted(routes.glob('*.js')) if routes.is_dir() else []:
        text = file.read_text(encoding='utf-8', errors='replace')
        for match in _ROUTE.finditer(text):
            route = match.group('path')
            if '${' in route:
                continue
            method = match.group('method').upper()
            line = text.count('\n', 0, match.start()) + 1
            for earlier, earlier_file, earlier_line in prior.get(method, []):
                if _matches(earlier, route):
                    issues.append(f'{file.relative_to(project)}:{line}: {method} {route} is shadowed by '
                                  f'{earlier_file}:{earlier_line} {method} {earlier}; register the literal path first')
                    break
            prior.setdefault(method, []).append((route, str(file.relative_to(project)), line))

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
