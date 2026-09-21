"""Bounded generation-batch checks. Never install dependencies or start servers."""
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path


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


def check_batch(root: Path, changed, budget=30):
    deadline = time.monotonic() + budget
    errors, checked, deferred = [], [], []

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
    return {'errors': errors, 'checked': checked, 'deferred': deferred}
