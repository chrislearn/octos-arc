"""Bounded source registration evidence, never proof of runtime reachability.

A missing registration is blocking only in a closed, supported literal table.
Dynamic routers and mounts require runtime evidence. No application code is run.
"""
from __future__ import annotations

import re


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
