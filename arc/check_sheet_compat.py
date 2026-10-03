#!/usr/bin/env python3
"""Run isolated Sheet option-click probes against an already started app."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from acceptance import AcceptanceRunner, acceptance_work_dir, find_playwright_root, playwright_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--playwright-root', type=Path)
    parser.add_argument('--timeout-ms', type=int, default=30000)
    args = parser.parse_args()
    suite = Path(__file__).with_name('sheet-compatibility')
    root = (find_playwright_root([args.playwright_root]) if args.playwright_root else
            find_playwright_root(playwright_candidates(Path(__file__).parent, suite, Path.cwd())))
    if root is None:
        parser.error('Pass --playwright-root pointing to a directory containing node_modules/@playwright/test')
    runner = AcceptanceRunner(root, suite, acceptance_work_dir(root), print,
                              timeout_ms=args.timeout_ms, workers=1)
    summary = runner.run(['visible-options.spec.ts'], args.base_url,
                         wall_timeout=max(120, args.timeout_ms // 1000 * 8), workers=1)
    launch_errors = [row.message for row in summary.results if 'browserType.launch:' in (row.message or '')]
    infrastructure_error = (launch_errors[0].splitlines()[0] if launch_errors and
                            len(launch_errors) == summary.total else None)
    print(json.dumps({
        'passed': summary.passed, 'total': summary.total, 'error': summary.error,
        'infrastructure_error': infrastructure_error,
        'cases': [{'name': row.title, 'ok': row.ok, 'status': row.status,
                   'first_error': (row.message or '')[:400]} for row in summary.results],
        'artifacts': summary.artifact_dirs,
        'work_dir': str(runner.work_dir),
    }, ensure_ascii=False, indent=2))
    if infrastructure_error or summary.error:
        return 2
    return 0 if summary.all_passed and summary.total == 4 else 1


if __name__ == '__main__':
    raise SystemExit(main())
