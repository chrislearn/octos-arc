#!/usr/bin/env python3
"""Compile every REQ helper closure and test disposable copies; no model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.request


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, cwd, log, env=None):
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}')


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def verify(args):
    sys.path.insert(0, str(args.repo / 'arc'))
    import main
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'node_modules').symlink_to(args.projects / 'node_modules', target_is_directory=True)
    all_rows, suites, protected = [], {}, {}
    for name in ('hackathon--github', 'hackathon--sheet'):
        source = args.repo / 'arc/derived-tests' / name
        project = args.projects / name
        helper = (source / 'helpers.ts').read_text()
        protected[str(source / 'helpers.ts')] = sha(source / 'helpers.ts')
        tests = args.output / 'derived-tests' / name
        tests.mkdir(parents=True)
        baseline = args.output / 'baseline' / name
        baseline.mkdir(parents=True)
        shutil.copy2(source / 'helpers.ts', baseline / 'helpers.ts')
        for spec in sorted(source.glob('REQ-*.spec.ts')):
            closure = tests / spec.name.removesuffix('.spec.ts')
            closure.mkdir()
            protected[str(spec)] = sha(spec)
            shutil.copy2(spec, closure / spec.name)
            shutil.copy2(spec, baseline / spec.name)
            trimmed = main.trim_helper_to_references(helper, set(main._IDENT.findall(spec.read_text())))
            (closure / 'helpers.ts').write_text(trimmed)
            assert sha(closure / spec.name) == sha(spec)
            all_rows.append({'suite': name, 'node': closure.name, 'original_chars': len(helper),
                             'rendered_chars': len(trimmed), 'saved_chars': len(helper) - len(trimmed),
                             'spec_sha256': sha(spec), 'helper_sha256': sha(closure / 'helpers.ts')})
        # Establish that the original source and every closure both type-check.
        config = {'compilerOptions': {'target': 'ES2022', 'module': 'CommonJS',
                  'moduleResolution': 'Node', 'noEmit': True, 'skipLibCheck': True,
                  'types': ['node'], 'typeRoots': [str(args.ts_root / 'node_modules/@types')]},
                  'include': [str(tests / '**/*.ts'), str(baseline / '*.ts')]}
        tsconfig = args.output / f'{name}-tsconfig.json'
        tsconfig.write_text(json.dumps(config))
        run(['node', str(args.ts_root / 'node_modules/typescript/lib/tsc.js'), '-p', str(tsconfig)],
            args.output, args.output / f'{name}-typecheck.log')
        # Keep every executable project/source/spec byte intact; only the
        # disposable prompt closure is substituted in the temporary test tree.
        app = args.output / 'apps' / name
        shutil.copytree(project, app, ignore=shutil.ignore_patterns(
            'node_modules', 'data', 'evidence', 'test-results', 'playwright-report', 'derived-tests'))
        (app / 'derived-tests').mkdir()
        shutil.copy2(project / 'derived-tests/fixtures.json', app / 'derived-tests/fixtures.json')
        assert not list(app.rglob('INTEGRATION-*.spec.ts'))
        port = free_port()
        env = {**os.environ, 'PORT': str(port), 'DATA_FILE': str(args.output / f'{name}-store.json')}
        report = args.output / f'{name}-playwright.json'
        browser = args.browser or Path('/home/chris/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome')
        pwconfig = args.output / f'{name}-playwright.config.cjs'
        pwconfig.write_text('module.exports=' + json.dumps({
            'testDir': str(tests), 'workers': 1, 'fullyParallel': False, 'timeout': 70000,
            'expect': {'timeout': 2500}, 'outputDir': str(args.output / 'test-results' / name),
            'reporter': [['line'], ['json', {'outputFile': str(report)}]],
            'use': {'baseURL': f'http://127.0.0.1:{port}', 'headless': True,
                    'launchOptions': {'executablePath': str(browser)}}}) + ';\n')
        with (args.output / f'{name}-server.log').open('w') as log:
            server = subprocess.Popen(['node', 'server.mjs'], cwd=app, env=env, stdout=log, stderr=log)
            try:
                for _ in range(150):
                    if server.poll() is not None:
                        raise RuntimeError('Disposable server exited')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError('Disposable server readiness timed out')
                run(['node', str(args.projects / 'node_modules/@playwright/test/cli.js'),
                     'test', '--config', str(pwconfig)], args.output,
                    args.output / f'{name}-playwright.log', env)
            finally:
                server.terminate()
                try: server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
        stats = json.loads(report.read_text())['stats']
        assert stats['unexpected'] == stats['flaky'] == stats['skipped'] == 0, stats
        rows = [row for row in all_rows if row['suite'] == name]
        suites[name] = {'typecheck': 'passed', 'runtime': stats,
                        'node_specs': len(rows), 'helper_original_chars': len(helper),
                        'helper_rendered_chars_median': statistics.median(row['rendered_chars'] for row in rows)}
        print(name, stats, flush=True)
    assert all(sha(Path(path)) == original for path, original in protected.items())
    result = {'schema': 'octos.arc.performance-implementation-verification.v1',
              'model_requests_started': 0, 'specs_and_helpers_unchanged': True,
              'integration_executed': False, 'suites': suites, 'helper_closures': all_rows,
              'protected_source_sha256': protected}
    (args.output / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--projects', type=Path, required=True)
    parser.add_argument('--ts-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New disposable directory')
    parser.add_argument('--browser', type=Path)
    args = parser.parse_args()
    verify(args)
