"""Repair scheduling primitives; diagnostics never substitute for acceptance."""
from functools import wraps
from contextlib import contextmanager
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
        # Pipe EOF and waiting for the leader do not prove descendants have
        # finished: their descriptors can close before SIGKILL reaches exit/Z.
        # Observe only this session's group; never signal other process groups.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            running = False
            try:
                with os.scandir('/proc') as entries:
                    for entry in entries:
                        if not entry.name.isdigit():
                            continue
                        try:
                            with open(entry.path + '/stat') as record:
                                fields = record.read().rsplit(')', 1)[1].split()
                            if int(fields[2]) == process.pid and fields[0] not in {'Z', 'X'}:
                                running = True
                                break
                        except (OSError, ValueError, IndexError):
                            continue
            except OSError:
                break  # /proc is unavailable on non-Linux hosts
            if not running:
                break
            time.sleep(0.01)


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


@contextmanager
def repair_deadline(flow, deadline):
    """All repair segments share a cutoff; acceptance keeps the node window."""
    previous = getattr(flow, '_node_deadline', None)
    flow._node_deadline = min(previous, deadline) if previous is not None else deadline
    try:
        yield
    finally:
        flow._node_deadline = previous


def startup_recovery_deadline(method):
    """Sequential/deferred recovery share the active node's original deadline."""
    @wraps(method)
    def scoped(flow, *args, **kwargs):
        previous = getattr(flow, '_node_deadline', None)
        deadline = getattr(flow, '_startup_recovery_deadline', None)
        if deadline is None:
            deadline = time.monotonic() + min(720, max(0, seconds_available(flow)))
            flow._startup_recovery_deadline = deadline
        flow._node_deadline = min(previous, deadline) if previous is not None else deadline
        try:
            if seconds_available(flow) <= 0:
                return False
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
