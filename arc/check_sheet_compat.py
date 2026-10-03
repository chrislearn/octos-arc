#!/usr/bin/env python3
"""Run isolated Sheet option-click probes against an already started app."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from acceptance import find_playwright_root, playwright_candidates
from compatibility_checks import probe_started_app


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
    result = probe_started_app(root, suite, args.base_url, print, timeout_ms=args.timeout_ms,
                               wall_timeout=max(120, args.timeout_ms // 1000 * 8))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['status'] == 'unavailable':
        return 2
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
