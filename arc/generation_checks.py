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


def contract_warnings(sources, changed):
    """Bounded source hints, never proof of a bug or grounds to reject a write.

    Inspect the supplied source index, not arbitrary files or executable code.
    Aliased calls and subscriptions can escape these heuristics; require a
    behavioral check rather than prescribing a replacement implementation.
    """
    from source_index import SourceIndex
    index = SourceIndex(sources)
    affected = index.affected(set(changed))
    warnings = []
    owners = {}
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
    errors, checked, deferred = helper_import_errors(sources or {}, changed), [], []

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
