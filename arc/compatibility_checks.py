"""Separate browser compatibility observations; never acceptance verdicts."""
from __future__ import annotations

import socket
import tempfile
import time
from pathlib import Path

from acceptance import AcceptanceRunner, AppServer, acceptance_work_dir
from verify_app import copy_application


def probe_started_app(root: Path, suite: Path, base_url: str, log, *,
                      timeout_ms: int = 20000, wall_timeout: int = 120,
                      report_dir: Path | None = None) -> dict:
    runner = AcceptanceRunner(root, suite, acceptance_work_dir(root), log,
                              timeout_ms=timeout_ms, workers=1)
    if report_dir is not None:
        runner.artifact_dir = report_dir / 'evidence'
    summary = runner.run(['visible-options.spec.ts'], base_url,
                         wall_timeout=max(1, wall_timeout), workers=1)
    launch = [row.message for row in summary.results if 'browserType.launch:' in (row.message or '')]
    infrastructure_error = launch[0].splitlines()[0] if launch and len(launch) == summary.total else None
    unavailable = (summary.error or summary.partial or summary.killed or summary.load_errors
                   or summary.total != 4 or len(summary.results) != 4 or summary.runtime_uncertain
                   or launch and len(launch) == summary.total
                   or any(row.status not in {'passed', 'failed', 'timedOut'} for row in summary.results))
    return {'status': 'unavailable' if unavailable else 'passed' if summary.all_passed else 'observed_failures',
            'passed': summary.passed, 'total': summary.total,
            'error': summary.error or (launch[0].splitlines()[0] if launch else None),
            'infrastructure_error': infrastructure_error,
            'cases': [{'name': row.title, 'ok': row.ok, 'status': row.status,
                       'first_error': (row.message or '')[:2000]} for row in summary.results],
            'artifacts': summary.artifact_dirs, 'work_dir': str(runner.work_dir),
            'authority': 'compatibility_observation_only'}


def probe_isolated_app(app: Path, root: Path, suite: Path, report_dir: Path, log, *, budget: int = 180) -> dict:
    """Build/start a private copy under one wall budget, including npm install.

    Relative writes and ARC_DATA_DIR are isolated. As with verify_app, arbitrary
    external databases/absolute paths in generated code cannot be isolated here.
    """
    deadline = time.monotonic() + budget
    with tempfile.TemporaryDirectory(prefix='octos-compatibility-') as directory:
        copy = Path(directory) / 'app'
        copy_application(app, copy)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        server = AppServer(copy, port, log, env_extra={'ARC_DATA_DIR': str(Path(directory) / 'data')})
        server.deadline = deadline
        try:
            error = server.build() or server.start()
            left = int(server.time_left(budget))
            if error or left <= 0:
                return {'status': 'unavailable', 'error': error or 'compatibility time budget exhausted',
                        'authority': 'compatibility_observation_only', 'data_isolation': 'private_copy'}
            result = probe_started_app(root, suite, f'http://127.0.0.1:{port}', log,
                                       timeout_ms=20000, wall_timeout=left, report_dir=report_dir)
            result['data_isolation'] = 'private_copy'
            return result
        finally:
            server.stop()


def advisory_text(result: dict) -> str:
    if result.get('status') != 'observed_failures':
        return ''
    lines = ['Separate Sheet compatibility observations (not official acceptance or a business oracle). '
             'Verify these interactions against the requirements and current source before editing; '
             'keep legitimate product behavior and protected tests unchanged.']
    for row in result.get('cases', []):
        if not row['ok']:
            lines.append(row['name'] + ':\n' + row['first_error'][:650])
    return '\n'.join(lines)
