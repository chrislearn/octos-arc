"""Bounded source and trusted runtime registration evidence.

A missing registration blocks only in a closed literal table or a complete
route dump from the bundled server. Neither proves handler behavior.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def _quoted_end(source, start):
    quote, i = source[start], start + 1
    while i < len(source):
        if source[i] == '\\':
            i += 2
        elif source[i] == quote:
            return i + 1
        else:
            i += 1
    return len(source)


def _comment_end(source, i):
    if source.startswith('//', i):
        end = source.find('\n', i)
        return len(source) if end < 0 else end
    if source.startswith('/*', i):
        end = source.find('*/', i + 2)
        return len(source) if end < 0 else end + 2
    return i


def _jsx_tags(source):
    """Scan opening tags with balanced attribute expressions, skipping JS strings.

    Expressions are opaque: preserve an {} marker so path={expr} and spreads
    cannot silently become a pathless layout. This is not a JS/JSX parser.
    """
    i = 0
    while i < len(source):
        end = _comment_end(source, i)
        if end != i:
            i = end
            continue
        if source[i] in "\"'`":
            i = _quoted_end(source, i)
            continue
        match = re.match(r'<(/?)([A-Za-z][\w.]*)\b', source[i:]) if source[i] == '<' else None
        if not match:
            i += 1
            continue
        start, name, close = i, match[2], bool(match[1])
        i += match.end()
        attrs, depth = [], 0
        while i < len(source):
            char = source[i]
            end = _comment_end(source, i) if depth else i
            if end != i:
                i = end
                continue
            if char in "\"'`":
                end = _quoted_end(source, i)
                if not depth:
                    attrs.append(source[i:end])
                i = end
                continue
            if char == '{':
                if not depth:
                    attrs.append('{}')
                depth += 1
            elif char == '}':
                depth -= 1
            elif char == '>' and not depth:
                i += 1
                break
            elif not depth:
                attrs.append(char)
            i += 1
        else:
            yield start, i, name, 'invalid', ''.join(attrs)
            return
        text = ''.join(attrs)
        kind = 'close' if close else 'self' if text.rstrip().endswith('/') else 'open'
        yield start, i, name, kind, text


def _attributes(text):
    """Top-level attribute names/values; strings cannot impersonate attributes."""
    attrs, uncertain, i = {}, False, 0
    while i < len(text):
        if text[i].isspace() or text[i] == '/':
            i += 1
            continue
        name = re.match(r'[A-Za-z_$][\w$:-]*', text[i:])
        if not name:
            return attrs, True
        key = name[0]
        i += name.end()
        while i < len(text) and text[i].isspace():
            i += 1
        value = True  # boolean attribute, e.g. index
        if i < len(text) and text[i] == '=':
            i += 1
            while i < len(text) and text[i].isspace():
                i += 1
            if i < len(text) and text[i] in "\"'":
                end = _quoted_end(text, i)
                value = text[i + 1:end - 1]
                if '\\' in value or '&' in value:
                    value = None  # escapes/entities need a real JSX parser
                i = end
            elif text.startswith('{}', i):
                value, i = None, i + 2
            else:
                return attrs, True
        if key in attrs:
            uncertain = True
        attrs[key] = value
    return attrs, uncertain


def route_shape(path):
    """Compare parameter names independently, retaining optional/splat syntax."""
    return re.sub(r':[A-Za-z_$][\w$]*', ':', path.rstrip('/') or '/')


def frontend_route_index(sources):
    declarations, reasons, tables = [], [], 0
    for filename, source in sorted(sources.items()):
        if not filename.startswith('frontend/') or not filename.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs')):
            continue
        # Object routers, aliases and descendant routers are outside the closed
        # literal table. A known literal declaration can still be recorded.
        if re.search(r'\b(?:useRoutes|create\w*Router|createRoutesFrom\w*)\b|\bRoute\s+as\s|\bRoutes\s+as\s|\b(?:import|lazy)\s*\(', source):
            reasons.append(filename + ': dynamic/object/aliased router')
        stack, cursor, active = [], 0, False
        for start, end, name, kind, attrs in _jsx_tags(source):
            if active:
                gap = source[cursor:start]
                gap = re.sub(r'\{\s*/\*.*?\*/\s*\}', '', gap, flags=re.S)
                if gap.strip():
                    reasons.append(filename + ': expression or unsupported children in table')
            if name.endswith('Router') and 'basename' in _attributes(attrs)[0]:
                reasons.append(filename + ': router basename requires runtime resolution')
            if name.endswith(('.Routes', '.Route')):
                reasons.append(filename + ': namespaced router')
            if name == 'Routes' and kind == 'open':
                tables += 1
                if active or stack or attrs.strip():
                    reasons.append(filename + ': nested or parameterized Routes')
                active = True
                stack = ['']
            elif name == 'Routes' and kind == 'close':
                if not active or len(stack) != 1:
                    reasons.append(filename + ': unbalanced Routes')
                active, stack = False, []
            elif name == 'Route':
                if not active:
                    reasons.append(filename + ': route outside a literal Routes table')
                if kind == 'close':
                    if len(stack) > 1:
                        stack.pop()
                    else:
                        reasons.append(filename + ': unbalanced Route')
                else:
                    parent = stack[-1] if stack else None
                    attributes, spread = _attributes(attrs)
                    value = attributes.get('path')
                    dynamic = ('path' in attributes and not isinstance(value, str)
                               or 'index' in attributes and attributes['index'] is not True)
                    if dynamic or spread or kind == 'invalid':
                        reasons.append(filename + ': dynamic path/spread or incomplete tag')
                        full = None
                    elif isinstance(value, str) and parent is not None:
                        full = value if value.startswith('/') else parent.rstrip('/') + '/' + value
                    else:
                        full = parent
                    if full is not None and ('path' in attributes or attributes.get('index') is True):
                        declarations.append({'path': full or '/', 'file': filename,
                                             'line': source.count('\n', 0, start) + 1})
                        if re.search(r'[*?()\\]', full):
                            reasons.append(filename + ': wildcard/optional/pattern route')
                    if kind == 'open':
                        stack.append(full)
            elif active:
                reasons.append(filename + ': composed route children')
            cursor = end
        if active or stack:
            reasons.append(filename + ': unclosed table')
    if tables > 1:
        reasons.append('multiple tables may be mounted at relative base paths')
    if not tables:
        reasons.append('no closed literal Routes table found')
    return {'declarations': declarations, 'complete': bool(tables) and not reasons,
            'reasons': sorted(set(reasons)), 'scope': 'literal JSX registration; runtime reachability unverified'}


def frontend_route_evidence(index, path):
    matches = [row for row in index['declarations'] if route_shape(row['path']) == route_shape(path)]
    ambiguous = any(route_shape(row['path']).lower() == route_shape(path).lower()
                    for row in index['declarations']) and not matches
    ambiguous = ambiguous or bool(re.search(r'[%?#]', path))
    return {'status': 'present' if matches else 'proven_missing' if index['complete'] and not ambiguous else 'unknown',
            'path': path, 'normalized_path': route_shape(path), 'sources': matches,
            'scope': index['scope'], 'reasons': index['reasons'] +
            (['case/encoding/query semantics require runtime resolution'] if ambiguous else [])}


def backend_route_evidence(sources, method, path):
    """Direct app registrations only; mounts/computed registries stay unknown.

    Negative evidence is intentionally restricted to simple exported registration
    tables with identifier handlers. General JS control flow is not interpreted.
    """
    rows, complete, seen = [], True, False
    call = re.compile(r'''\bapp\.(get|post|put|patch|delete|head|options)\s*\(\s*(['"])(/[^'"\n]*)\2\s*,\s*([A-Za-z_$][\w$]*)\s*\)\s*;?''')
    for filename, source in sorted(sources.items()):
        if not filename.startswith('backend/') or not filename.endswith(('.js', '.cjs', '.mjs', '.ts')):
            continue
        # Only route table modules can support a negative proof. General
        # entrypoints may mount prefixes or register routes programmatically.
        if not filename.startswith('backend/routes/'):
            if re.search(r'\b(?:app|router)\s*\.|\bRouter\s*\(', source):
                complete = False
            continue
        seen = True
        cleaned = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
        table = re.fullmatch(r'\s*module\.exports\s*=\s*\(?app\)?\s*=>\s*\{(.*)\}\s*;?\s*', cleaned, re.S)
        if not table or call.sub('', table[1]).strip():
            complete = False
        # Only use declarations within supported tables; other source forms
        # must be verified via the live registry, including app.use mounts.
        if table:
            for match in call.finditer(table[1]):
                if re.search(r'[*?()\\]', match[3]):
                    complete = False
                if (match[1].upper() == method.upper()
                        and route_shape(match[3]).lower() == route_shape(path).lower()
                        and route_shape(match[3]) != route_shape(path)):
                    complete = False  # default/custom case sensitivity is not inferred
                if match[1].upper() == method.upper() and route_shape(match[3]) == route_shape(path):
                    rows.append({'file': filename, 'path': match[3], 'method': method.upper()})
    return {'status': 'present' if rows else 'proven_missing' if seen and complete else 'unknown',
            'path': path, 'method': method.upper(), 'normalized_path': route_shape(path), 'sources': rows,
            'scope': 'direct literal app registration; mounts/control flow and runtime reachability unverified',
            'reasons': [] if seen and complete else ['backend registration graph is not a closed literal table']}


def runtime_backend_routes(project: Path, sources: dict[str, str], *, timeout: int = 4) -> dict:
    """Ask the trusted generic server for its registered routes without binding a port.

    A missing route is useful negative evidence only when the server and route
    tracker are still the bundled versions and business routers are not mounted
    through an untracked app.use/router.route chain. Startup failures stay
    unknown; this probe never declares a generated application healthy.
    """
    blueprints = Path(__file__).with_name('blueprints')
    server = sources.get('backend/server.js', '')
    server = re.sub(r'Number\(process\.env\.PORT \|\| \d+\)',
                    'Number(process.env.PORT || __ARC_DEFAULT_PORT__)', server)
    server = re.sub(r'ports\.push\(\.\.\.\[[\d,\s]*\]\)',
                    'ports.push(...__ARC_EXTRA_PORTS__)', server)
    if (server != (blueprints / 'server.js').read_text(encoding='utf-8')
            or sources.get('backend/lib/arc.js') !=
            (blueprints / 'arc-runtime.js').read_text(encoding='utf-8')):
        return {'status': 'unknown', 'reason': 'route dump requires the bundled server and tracker'}
    route_sources = {name: source for name, source in sources.items()
                     if name.startswith('backend/routes/') and name.endswith(('.js', '.cjs'))}
    if any(re.search(r'''\b(?:app|router)\s*(?:\.\s*(?:use|route)|\[\s*['"](?:use|route)['"]\s*\])\s*\(|\bRouter\s*\(''', source)
           or re.search(r'\b(?:setTimeout|setImmediate|queueMicrotask|import)\s*\(|\bprocess\.nextTick\s*\('
                        r'|\.then\s*\(|\bmodule\.exports\s*=\s*async\b'
                        r'|\b(?:const|let|var)\s+\w+\s*=\s*app\b', source)
           for source in route_sources.values()):
        return {'status': 'unknown', 'reason': 'mounted or chained routes need live request evidence'}
    node = shutil.which('node')
    if not node or not (project / 'backend/node_modules/express').exists():
        return {'status': 'unknown', 'reason': 'node or express unavailable'}
    try:
        with tempfile.TemporaryDirectory(prefix='arc-route-dump-') as scratch:
            target = Path(scratch) / 'routes.json'
            env = dict(os.environ, ARC_ROUTE_DUMP=str(target), ARC_DATA_DIR=str(Path(scratch) / 'data'),
                       ARC_TEST_HOOKS='0', ARC_EXTRA_PORTS='0', PORT='0')
            run = subprocess.run([node, 'server.js'], cwd=project / 'backend', env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=timeout, check=False)
            if run.returncode != 0 or not target.is_file():
                return {'status': 'unknown', 'reason': 'route dump failed or application did not load'}
            report = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {'status': 'unknown', 'reason': 'route dump unavailable'}
    routes = report.get('routes') if isinstance(report, dict) else None
    if not isinstance(routes, list) or any(
            not isinstance(row, dict) or not isinstance(row.get('method'), str)
            or not isinstance(row.get('path'), str) for row in routes):
        return {'status': 'unknown', 'reason': 'invalid route dump'}
    return {'status': 'complete', 'routes': routes}
