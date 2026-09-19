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
    source = frontend / 'src'
    html = list(source.rglob('*.html')) if source.is_dir() else []
    if not spa and len(html) == 1 and html[0].name == 'index.html':
        try:
            page = html[0].read_text(encoding='utf-8', errors='replace')
            scripts = '\n'.join(file.read_text(encoding='utf-8', errors='replace')
                                for file in source.rglob('*.js')
                                if 'shared' not in file.relative_to(source).parts)
        except OSError:
            return issues
        if ('history.pushState' in page + scripts or 'startRouter(' in page + scripts) and _client_side_link(page):
            issues.append('frontend: client-side links use history.pushState but only index.html exists; '
                          'set frontend/package.json arc.spa=true for direct loads and refreshes, or add HTML pages')
    return issues
