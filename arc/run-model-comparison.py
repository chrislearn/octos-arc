#!/usr/bin/env python3
"""Run a frozen adapter sequentially from zero, then independently grade copies.

Credentials stay in the caller's local configuration. No task/source edits,
model fallback or template application is performed by this experiment runner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from metrics import summarize


def bounded(command, log, env, seconds):
    started = time.monotonic()
    with log.open('w') as output:
        proc = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
        try:
            code = proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            code = 124
    return {'exit_code': code, 'elapsed_seconds': round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('adapter', 'task', 'tests', 'api-config', 'binary', 'playwright', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--port', type=int, default=43520)
    parser.add_argument('--reasoning', choices=['none', 'low', 'medium', 'high'], default='low')
    parser.add_argument('--models', nargs='+', default=['deepseek-v4-flash', 'qwen3.7-plus'])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, OCTOS_BIN=str(args.binary.resolve()), OCTOS_TIME_BUDGET=str(args.seconds),
               OCTOS_ARC_MAX_TOTAL_TOKENS='2000000', OCTOS_ARC_MAX_TOTAL_TOKENS_ABS='2000000',
               OCTOS_ARC_REASONING=args.reasoning, OCTOS_ARC_IMPLEMENT_REASONING=args.reasoning,
               OCTOS_ARC_TEST_WORKERS='1', OCTOS_ARC_GRADER_WORKERS='1', OCTOS_ARC_FINAL_WORKERS='1',
               OCTOS_ARC_PLAYWRIGHT_ROOT=str(args.playwright.resolve()),
               OCTOS_ARC_STRUCTURED_EDITS='1', OCTOS_ARC_SAFE_EDIT='1', OCTOS_ARC_STREAM_GUARD='1')
    manifest = {'models': args.models, 'budget_seconds': args.seconds,
                'thinking': args.reasoning != 'none', 'reasoning': args.reasoning,
                'binary_sha256': hashlib.file_digest(args.binary.open('rb'), 'sha256').hexdigest(),
                'adapter': str(args.adapter.resolve()), 'runs': []}
    for index, model in enumerate(args.models):
        name = f'edit-protocol-{index + 1}'
        app = args.adapter / 'arc-output' / name
        if app.exists():
            raise ValueError(f'Fresh output already exists: {app}')
        folder = args.output / model
        folder.mkdir()
        print(f'Start {model}, fresh {args.task.name}, budget {args.seconds}s', flush=True)
        run = bounded([sys.executable, str(args.adapter / 'run-task-local.py'), str(args.task),
                       '--api-config', str(args.api_config), '--model', model, '--name', name,
                       '--port', str(args.port + index * 4)], folder / 'run.log', env, args.seconds)
        row = dict(model=model, app=str(app), **run)
        row['metrics'] = summarize(app)
        (folder / 'metrics.json').write_text(json.dumps(row, indent=2, ensure_ascii=False))
        for filename in ('llm-usage.jsonl', 'flow-metrics.jsonl', 'octos-events.jsonl', 'runner-events.jsonl'):
            source = app / '.arc' / filename
            if source.exists():
                shutil.copy2(source, folder / filename)
        print(f'Generation finished {model}: {run}. Independent grading next.', flush=True)
        grade = bounded([sys.executable, str(args.adapter / 'verify_app.py'), '--app', str(app),
                         '--tests', str(args.tests), '--playwright', str(args.playwright),
                         '--report-dir', str(folder / 'grade'), '--workers', '1'],
                        folder / 'grade.log', env, 1100)
        summary = folder / 'grade/summary.json'
        row['grade'] = dict(grade, summary=json.loads(summary.read_text()) if summary.exists() else None)
        manifest['runs'].append(row)
        (args.output / 'comparison.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f'Finished {model}: grade={row["grade"]["summary"] and row["grade"]["summary"]["passed"]}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
