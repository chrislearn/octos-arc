"""Repair scheduling primitives; diagnostics never substitute for acceptance."""
from functools import wraps
import time
import os
import signal
import subprocess


def run_owned_process(command, *, cwd, env, timeout):
    """Build/test cancellation kills its owned process group, including browsers."""
    process = subprocess.Popen(command, cwd=cwd, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    def stop():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        stop()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # A descendant escaping the owned group must not hold cleanup open.
            process.stdout.close()
            process.stderr.close()


def isolated_node_deadline(method):
    """Do not leak a completed node's deadline into final/full-suite acceptance."""
    @wraps(method)
    def scoped(flow, *args, **kwargs):
        previous = getattr(flow, '_node_deadline', None)
        try:
            return method(flow, *args, **kwargs)
        finally:
            flow._node_deadline = previous
    return scoped


def seconds_available(flow):
    try:
        remaining = flow.remaining()
    except AttributeError:
        # Bare Flow test/diagnostic instances may have only a caller allowance.
        remaining = float('inf')
    deadline = getattr(flow, '_node_deadline', None)
    return min(remaining, deadline - time.monotonic()) if deadline is not None else remaining


def case_key(row):
    # Failure source locations move with edits; titles + immutable spec own identity.
    return (row.spec_path or row.file, row.title, row.spec_line)


def progress_snapshot(summary):
    rows = {}
    for row in summary.results:
        key = case_key(row)
        if key in rows:
            return {}  # ambiguous identity cannot prove monotonic case progress
        rows[key] = (row.ok, tuple(getattr(row, 'completed_steps', ())))
    return rows


def measured_progress(previous, current):
    """Require the same measured cases, no lost pass/step, and a strict gain.

    Only the parser's explicitly completed prefix is eligible. Missing traces,
    changed error text, source lines and total step counts cannot earn a round.
    """
    if not previous or previous.keys() != current.keys():
        return 'unknown'
    gained = False
    for key, (old_ok, old_steps) in previous.items():
        new_ok, new_steps = current[key]
        if old_ok and not new_ok:
            return 'regression'
        if not old_ok and new_ok:
            gained = True
        elif not old_ok and not new_ok and old_steps:
            if new_steps[:len(old_steps)] != old_steps:
                return 'unknown'
            gained |= len(new_steps) > len(old_steps)
    return 'advanced' if gained else 'unchanged'
