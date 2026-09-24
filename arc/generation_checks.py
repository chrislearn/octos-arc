"""Bounded generation-batch checks. Never install dependencies or start servers."""
import hashlib
import json
import os
import re
import posixpath
import signal
import subprocess
import time
from pathlib import Path


# Previous shipped request helper also resolved to raw JSON (204 => null).
# Recognize that exact revision in evolution apps without assuming that an
# application-owned adapter named requestJson has the same return contract.
LEGACY_RAW_REQUEST_SHA256 = 'd88375d1a8519a79ba19d5cb9191f63fd0b77d447c258dceeee407f3d02e393b'


def raw_request_adapter(source: str) -> bool:
    current = (Path(__file__).parent / 'blueprints/frontend-request.js').read_text()
    return source == current or hashlib.sha256(source.encode()).hexdigest() == LEGACY_RAW_REQUEST_SHA256


def adapter_fingerprint(root: Path) -> dict:
    """Identify adapter source and bundled blueprints, without environment secrets."""
    files = list(root.glob('*.py'))
    files += [p for p in (root / 'blueprints').rglob('*') if p.is_file()]
    digest = hashlib.sha256()
    count = 0
    for path in sorted(files):
        if path.is_symlink():
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        count += 1
    return {'scope': 'adapter_python_and_blueprints', 'sha256': digest.hexdigest(), 'files': count}


def helper_import_errors(sources, changed):
    """Check only literal named CJS imports from unchanged bundled helpers.

    No application modules are executed. Customized modules and dynamic imports
    are intentionally left to the compiler/runtime instead of guessed exports.
    """
    contracts = {'store': {'read', 'write', 'update', 'migrate'},
                 'collection': {'collection'}, 'errors': {'HttpError'},
                 'query': {'optionalBoolean', 'matchesFlags'}}
    known = {}
    for name, exports in contracts.items():
        path = 'backend/lib/' + name + '.js'
        template = Path(__file__).parent / 'blueprints' / (name + '.js')
        if path in sources and template.is_file() and sources[path] == template.read_text():
            known[path] = exports
    errors = []
    for path in sorted(changed):
        if not path.startswith('backend/') or not path.endswith(('.js', '.cjs')):
            continue
        source = sources.get(path, '')
        # Skip declarations quoted in comments/documentation/string literals.
        opaque = [m.span() for m in re.finditer(
            r'''//[^\n]*|/\*[\s\S]*?\*/|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|`(?:\\[\s\S]|[^`\\])*`''', source)]
        for match in re.finditer(r'''(?m)^\s*(?:const|let|var)\s*\{([^{}\n]+)\}\s*=\s*require\(\s*['"](\.[^'"]+)['"]\s*\)\s*;?\s*$''', source):
            start = match.start() + len(match.group()) - len(match.group().lstrip())
            if any(left <= start < right for left, right in opaque):
                continue
            fields, rel = match.groups()
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel))
            if not target.endswith('.js'):
                target += '.js'
            if target not in known:
                continue
            fields = [field.strip().split(':', 1)[0].strip() for field in fields.split(',') if field.strip()]
            if not all(re.fullmatch(r'[A-Za-z_$][\w$]*', field) for field in fields):
                continue
            missing = sorted(set(fields) - known[target])
            if missing:
                errors.append(f'{path}: {target} does not export {", ".join(missing)}; '
                              f'available: {", ".join(sorted(known[target]))}. Fix the caller; do not invent helper APIs.')
    return errors


def missing_local_import_errors(sources, changed):
    """Report explicit relative code imports absent from the generated tree.

    Restrict this to imports with a source extension. Extensionless imports may
    resolve through index files, and assets/query imports may use bundler
    plugins, so those remain advisory compiler checks.
    """
    errors = []
    for path in sorted(changed):
        if not path.startswith('frontend/') or not path.endswith(('.js', '.jsx', '.ts', '.tsx')):
            continue
        source = sources.get(path, '')
        for rel in re.findall(r'''(?m)^\s*import\s+(?:[^;\n]*?\s+from\s+)?['"](\.[^'"\n]+)['"]''', source):
            if '?' in rel or '#' in rel or not rel.endswith(('.js', '.jsx', '.ts', '.tsx')):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel))
            if target not in sources:
                errors.append(f'{path}: relative import {rel} resolves to missing {target}. '
                              'Fix the path or generate the module before the next batch.')
    return errors[:8]


def _bounded_run(command, cwd, timeout):
    """A timed-out npm build must not leave its compiler descendants running."""
    with subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, errors='replace', start_new_session=True) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            raise
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def route_link_warnings(sources, changed):
    """Flag dynamic in-app links with no matching React Router route.

    This is deliberately advisory: a router may be assembled dynamically. It
    catches the common case where a generated list links to a detail page that
    was written but never registered in the route table.
    """
    route_paths = set()
    for path, source in sources.items():
        if path.startswith('frontend/') and path.endswith(('.jsx', '.tsx')):
            route_paths.update(re.findall(r'''<Route\b[^>]*\bpath\s*=\s*['"]([^'"\n]+)['"]''', source))
    if not route_paths:
        return []
    warnings = []
    for path in sorted(changed):
        if not path.startswith('frontend/') or not path.endswith(('.jsx', '.tsx')):
            continue
        source = sources.get(path, '')
        # Only inspect JSX Link destinations and navigate() template literals.
        # The dynamic value's name need not match the route parameter's name.
        destinations = re.findall(r'''\bto\s*=\s*\{\s*`([^`]+)`''', source)
        destinations += re.findall(r'''\bnavigate\s*\(\s*`([^`]+)`''', source)
        for destination in destinations:
            for segment in re.findall(r'/([A-Za-z][A-Za-z0-9_-]*)/\$\{[^}]+\}', destination):
                if any(re.search(r'/' + re.escape(segment) + r'/(?:[:*][A-Za-z][\w-]*|\*)'
                                 r'(?:/|$)', route) for route in route_paths):
                    continue
                warning = (f'ROUTE_LINK (heuristic): {path} links to a dynamic /{segment}/… page, '
                           f'but no React Router path contains /{segment}/:param or /{segment}/*path. '
                           'Register the detail route or verify that another router handles the link.')
                if warning not in warnings:
                    warnings.append(warning)
    return warnings[:4]


def api_call_warnings(sources, changed):
    """Point out literal frontend API calls with no registered Express path."""
    routes = []
    for path, source in sources.items():
        if path.startswith('backend/') and path.endswith(('.js', '.cjs')):
            routes.extend(re.findall(
                r'''\b(?:app|router)\.(?:get|post|put|patch|delete)\(\s*['"](/api/[^'"\n]+)['"]''', source))
    if not routes:
        return []

    def segments(path):
        return [part for part in path.split('?', 1)[0].strip('/').split('/') if part]

    def matches(call, route):
        requested, declared = segments(call), segments(route)
        if declared and declared[-1].startswith('*'):
            return (len(requested) >= len(declared) - 1 and
                    all(a == b or a.startswith(':') or a.startswith('*') or b == '{}'
                        for a, b in zip(declared[:-1], requested)))
        return (len(requested) == len(declared) and
                all(a == b or a.startswith(':') or a.startswith('*') or b == '{}'
                    for a, b in zip(declared, requested)))

    warnings = []
    for path in sorted(changed):
        if not path.startswith('frontend/') or not path.endswith(('.js', '.jsx', '.ts', '.tsx')):
            continue
        source = sources.get(path, '')
        for call in re.findall(r'''\b(?:requestJson|fetch)\s*\(\s*[`'"](/api/[^`'"\n]+)[`'"]''', source):
            normalized = re.sub(r'\$\{[^}]+\}', '{}', call)
            if any(matches(normalized, route) for route in routes):
                continue
            warning = (f'API_CALL (heuristic): {path} calls {call}, but no Express route has a '
                       'matching /api path. Check the route owner, HTTP method and mount prefix.')
            if warning not in warnings:
                warnings.append(warning)
    return warnings[:4]


def contract_warnings(sources, changed):
    """Bounded source hints, never proof of a bug or grounds to reject a write.

    Inspect the supplied source index, not arbitrary files or executable code.
    Aliased calls and subscriptions can escape these heuristics; require a
    behavioral check rather than prescribing a replacement implementation.
    """
    from source_index import SourceIndex
    index = SourceIndex(sources)
    affected = index.affected(set(changed))
    warnings = route_link_warnings(sources, changed) + api_call_warnings(sources, changed)
    # These contracts are known only while the bundled helpers are unchanged.
    # A generated app may deliberately replace either helper with different
    # semantics, so never guess its return type from the function name alone.
    blueprints = Path(__file__).parent / 'blueprints'
    request_path = 'frontend/src/shared/request.js'
    collection_path = 'backend/lib/collection.js'
    bundled_request = request_path in sources and raw_request_adapter(sources[request_path])
    bundled_collection = (collection_path in sources and
                          sources[collection_path] == (blueprints / 'collection.js').read_text())
    owners = {}
    routes = {}
    for path, source in sources.items():
        if path.startswith('backend/'):
            for receiver, method, route in re.findall(
                    r'''(?m)^\s*(app|router)\.(get|post|put|patch|delete)\(\s*['"]([^'"\n]+)['"]''', source):
                routes.setdefault((receiver, method, route), set()).add(path)
        if path in affected and path.startswith('frontend/'):
            for rel in re.findall(r'''(?m)^\s*import\s+(?:[^;\n]*?\s+from\s+)?['"](\.[^'"\n]+)['"]''', source):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel.split('?', 1)[0]))
                if target.endswith(('.css', '.js', '.jsx', '.ts', '.tsx')) and target not in sources:
                    if '?' not in rel and '#' not in rel and target.endswith(('.js', '.jsx', '.ts', '.tsx')):
                        continue  # check_batch reports this precise local code import as an error.
                    warnings.append(f'IMPORT_PATH (heuristic): {path} imports {rel}, resolving to {target}, '
                                    'which is absent from the source index. Check the path and generated assets '
                                    'with the compiler; custom resolver plugins may supply this module.')
    for (receiver, method, route), paths in sorted(routes.items()):
        if len(paths) > 1 and paths & affected:
            warnings.append(f'ROUTE_OWNER (heuristic): {receiver}.{method}({route!r}) appears in ' +
                            ', '.join(sorted(paths)) + '. Verify mount prefixes and registration order before '
                            'adding another handler. Distinct routers and intentional middleware chains are valid.')
    for path, source in sources.items():
        if not path.startswith('backend/'):
            continue
        for name in re.findall(r'''\bcollection\(\s*['"]([^'"\n]+)['"]\s*,\s*\{\s*initial\s*:''', source):
            owners.setdefault(name, set()).add(path)
    for name, paths in sorted(owners.items()):
        if len(paths) > 1 and paths & affected:
            warnings.append('DATA_OWNER (heuristic): collection ' + name + ' is initialized in ' +
                            ', '.join(sorted(paths)) + '. Verify one canonical owner; compare fresh-store '
                            'and existing-store behavior. Do not reset data or resurrect deleted records.')
    for path in sorted(affected):
        source = sources.get(path, '')
        if bundled_collection and path.startswith('backend/routes/') and path.endswith(('.js', '.cjs')):
            # Returning a replacement array from collection.transact does not
            # replace data.items. This caught a real "deleted: N" false success.
            for match in re.finditer(r'\.transact\s*\(\s*([A-Za-z_$][\w$]*)\s*=>\s*\{', source):
                items = re.escape(match[1])
                body = source[match.end():match.end() + 2500].split('});', 1)[0]
                if re.search(r'\breturn\s+' + items + r'\s*\.\s*filter\s*\(', body):
                    warnings.append(f'TRANSACT_RETURN (heuristic): {path} returns {match[1]}.filter(...) '
                                    'from collection.transact. The helper persists mutations to the supplied '
                                    'array, not the returned replacement. Verify persisted data after the action; '
                                    'mutate the array in place or use the collection remove API.')
                    break
        if path.startswith('backend/routes/') and path.endswith(('.js', '.cjs')):
            if (re.search(r'''\buserId\s*:\s*(?:''|"")''', source)
                    and re.search(r'\b(?:getCurrentUser|requireUser)\s*\(', source)
                    and re.search(r'\.create\s*\(', source)
                    and re.search(r'\.userId\b', source)):
                warnings.append(f'OWNER_SCOPE (heuristic): {path} creates a record with an empty userId '
                                'and also reads records by userId. Verify the signed-in creation path stores '
                                'the active owner, then fetch the created record as that user. An anonymous '
                                'record may be intentional; check both flows.')
        if not path.startswith('frontend/') or not path.endswith(('.js', '.jsx', '.ts', '.tsx')):
            continue
        if bundled_request:
            # JSON values have no Response.json() method; requestJson has
            # already parsed the body. .ok/.value can be domain fields, so
            # report those as contract questions rather than definite errors.
            for match in re.finditer(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+requestJson\s*\(', source):
                name = re.escape(match[1])
                tail = source[match.end():]
                if re.search(r'\b' + name + r'\s*\.\s*json\s*\(', tail):
                    warnings.append(f'REQUEST_JSON (heuristic): {path} calls .json() on a value from '
                                    'requestJson. This helper already returns parsed JSON (204/empty => null); '
                                    'remove the second parse and handle the returned shape.')
                    break
                if re.search(r'\b' + name + r'\s*\.\s*(?:ok|value)\b', tail):
                    warnings.append(f'REQUEST_ENVELOPE (heuristic): {path} reads .ok or .value from '
                                    'requestJson output. The helper adds no success envelope; verify the backend '
                                    'explicitly returns this field. Catch HTTP errors with error.status.')
                    break
            if re.search(r'\brequestJson\s*\([^\n;]{0,350}\)\s*\.\s*json\s*\(', source):
                warnings.append(f'REQUEST_JSON (heuristic): {path} calls .json() on the requestJson promise. '
                                'Await requestJson directly; it returns parsed JSON or rejects.')
        if re.search(r'\buse(?:Layout)?Effect\s*\(\s*async\s*(?:function\b|'
                     r'(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)', source):
            warnings.append(f'ASYNC_EFFECT (heuristic): {path} passes an async effect callback. '
                            'React expects an effect to return cleanup or nothing, not a Promise. '
                            'Start an async function inside the effect and cancel/ignore stale results.')
        if path.endswith(('.jsx', '.tsx')):
            # Native nested controls have ambiguous click/label ownership. Do
            # not guess component internals or reject a write: this is a prompt
            # for a focused interaction check, not a JSX parser.
            if re.search(r'<label\b[^>]*>(?:(?!</label>).){0,1200}<button\b', source, re.S | re.I):
                warnings.append(f'LABEL_BUTTON (heuristic): {path} renders a button inside a label. '
                                'A label query may choose the button instead of the editable field. '
                                'Associate the label with one input via htmlFor/id and place actions beside it; '
                                'verify the field can be filled and the button clicked independently.')
            if re.search(r'<button\b[^>]*>(?:(?!</button>).){0,1200}<button\b', source, re.S | re.I):
                warnings.append(f'NESTED_BUTTON (heuristic): {path} renders a button inside a button. '
                                'Browsers repair invalid interactive nesting and React hydration/click targets '
                                'may differ. Split the controls and verify accessible roles and click paths.')
            # A controlled dialog may close on pointer/focus changes before an
            # editor field is usable. This is an interaction probe, not a ban
            # on autosave: some requirements explicitly call for it.
            if re.search(r'\bonOpenChange\s*=\s*\{\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{'
                         r'[^}]{0,350}\b(?:save|commit|submit)[A-Za-z_$\w]*\s*\(', source, re.I):
                warnings.append(f'DIALOG_CLOSE_SAVE (heuristic): {path} commits from onOpenChange. '
                                'Verify the entry click leaves a usable editor mounted, focus or child-menu '
                                'changes do not commit prematurely, and explicit Cancel still discards drafts.')
            if re.search(r'\bon(?:Click|Submit|Change|Select|CheckedChange)\s*=\s*\{\s*'
                         r'(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{\s*\}\s*\}', source):
                warnings.append(f'EMPTY_HANDLER (heuristic): {path} renders an interactive handler with '
                                'an empty body. Connect the visible action to a state/request transition or '
                                'remove the action; a successful build cannot verify behavior.')
            # A nested React Router layout receives its child route through
            # Outlet, even when the JSX nesting looks like children props.
            for layout in set(re.findall(
                    r'<Route\b[^\n]{0,350}\belement=\{<([A-Z][\w$]*)\s*/>\}\s*>\s*<Route\b', source)):
                imports = re.findall(r'''\bimport\s+''' + re.escape(layout) +
                                     r'''\s+from\s+['"](\.[^'"\n]+)['"]''', source)
                targets = [dep for dep in index.dependencies.get(path, ())
                           if any(posixpath.splitext(dep)[0] == posixpath.splitext(
                               posixpath.normpath(posixpath.join(posixpath.dirname(path), rel)))[0]
                                  for rel in imports)]
                if targets and not any(re.search(r'<Outlet\b|\bcreateElement\s*\(\s*Outlet\b', sources[target])
                                       for target in targets):
                    warnings.append(f'ROUTE_OUTLET (heuristic): {path} nests routes under {layout}, '
                                    f'but its imported module {targets[0]} has no Outlet. React Router '
                                    'renders child routes through <Outlet />; verify each child page appears.')
    for path in sorted(affected):
        if not path.startswith('frontend/') or not path.endswith(('.jsx', '.tsx')):
            continue
        source = sources.get(path, '')
        # Only a concrete JSX consumer with a storage-writing dependency merits
        # this reminder. Do not flag every use of localStorage as an error.
        nearby = index.related([path])
        writes = [p for p in sorted(nearby) if re.search(
            r'\b(?:localStorage|sessionStorage)\s*\.\s*(?:setItem|removeItem|clear)\s*\(', sources[p])]
        if writes and not re.search(r'\b(?:useContext|useSyncExternalStore)\s*\(', source):
            warnings.append('REACTIVE_STATE (heuristic): ' + path + ' is near storage writes in ' +
                            ', '.join(writes) + '. Verify shared consumers update without reload after '
                            'success, restore correctly after reload, and stay unchanged on failure. '
                            'State/props/custom hooks may already handle this; inspect before editing.')
    return [warning[:900] for warning in warnings[:6]]


def check_batch(root: Path, changed, budget=30, sources=None):
    deadline = time.monotonic() + budget
    errors = helper_import_errors(sources or {}, changed) + missing_local_import_errors(sources or {}, changed)
    checked, deferred = [], []

    def run(command, cwd, label):
        left = deadline - time.monotonic()
        if left < 1:
            deferred.append(label + ': check budget exhausted')
            return
        try:
            result = _bounded_run(command, cwd=cwd, timeout=left)
            checked.append(label)
            if result.returncode:
                errors.append(label + ':\n' + (result.stdout + result.stderr)[-2500:])
        except subprocess.TimeoutExpired:
            deferred.append(label + ': check timed out; not a source error')
        except OSError as exc:
            deferred.append(label + ': ' + str(exc))

    configs = {}
    for part in ('frontend', 'backend'):
        path = root / part / 'package.json'
        if not path.is_file():
            deferred.append(part + ': manifest not generated yet')
            continue
        try:
            config = json.loads(path.read_text())
            if not isinstance(config, dict):
                raise ValueError('expected an object')
            if not isinstance(config.get('scripts', {}), dict):
                raise ValueError('scripts must be an object')
            configs[part] = config
        except (ValueError, OSError) as exc:
            errors.append(part + '/package.json: ' + str(exc))
    for rel in sorted(changed):
        path = root / rel
        if path.is_file() and rel.startswith('backend/') and path.suffix in {'.js', '.mjs', '.cjs'}:
            run(['node', '--check', str(path.resolve())], root, 'syntax ' + rel)
    frontend = root / 'frontend'
    config = configs.get('frontend', {})
    if any(p.startswith('frontend/') for p in changed) and config.get('scripts', {}).get('build'):
        stamp = frontend / 'node_modules/.arc-manifest-sha256'
        lock = frontend / 'package-lock.json'
        digest = hashlib.sha256((frontend / 'package.json').read_bytes() + b'\0' +
                                (lock.read_bytes() if lock.is_file() else b'')).hexdigest()
        dependencies = any(config.get(k) for k in ('dependencies', 'devDependencies', 'optionalDependencies'))
        ready = not dependencies or stamp.is_file() and stamp.read_text().strip() == digest
        if ready and not errors:
            run(['npm', 'run', 'build'], frontend, 'frontend build')
        else:
            deferred.append('frontend build: dependencies not verified or syntax errors pending; full acceptance still required')
    return {'errors': errors, 'checked': checked, 'deferred': deferred,
            'warnings': contract_warnings(sources or {}, changed)}
