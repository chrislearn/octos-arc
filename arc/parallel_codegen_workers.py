"""Bounded, isolated code generation requests for a coordinator-owned workspace.

This module only schedules requests and returns text.  The caller supplies an
``execute`` function that uses a private model client for each job.  In
particular, workers never receive the coordinator's mutable Flow or a write
handle to its workspace.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from queue import Queue
import time
from typing import Callable, Iterable


@dataclass(frozen=True)
class WorkerJob:
    task_id: str
    prompt: str
    timeout: float
    system: str = ""
    reservation: int = 0
    label: str = ""


@dataclass(frozen=True)
class WorkerReply:
    task_id: str
    ok: bool
    text: str
    tokens: int = 0
    requests: int = 0
    usage_records: tuple[str, ...] = ()
    ledger_records: tuple[str, ...] = ()
    elapsed: float = 0.0
    reason: str = ""


def _execute_one(job: WorkerJob, execute: Callable[[WorkerJob], WorkerReply]) -> WorkerReply:
    started = time.monotonic()
    try:
        reply = execute(job)
    except Exception as exc:
        return WorkerReply(job.task_id, False, "", elapsed=time.monotonic() - started,
                           reason=f"worker failed: {type(exc).__name__}: {exc}"[:1000])

    elapsed = time.monotonic() - started
    if not isinstance(reply, WorkerReply):
        return WorkerReply(job.task_id, False, "", elapsed=elapsed,
                           reason="worker returned an invalid reply")
    if reply.task_id != job.task_id:
        return WorkerReply(job.task_id, False, "", tokens=reply.tokens,
                           requests=reply.requests, usage_records=reply.usage_records,
                           ledger_records=reply.ledger_records, elapsed=elapsed,
                           reason=f"worker replied for {reply.task_id!r} instead of {job.task_id!r}")
    if elapsed > job.timeout:
        return replace(reply, ok=False, elapsed=elapsed,
                       reason=reply.reason or f"worker exceeded {job.timeout:g}s timeout")
    return replace(reply, elapsed=elapsed)


def run_parallel(
    jobs: Iterable[WorkerJob],
    execute: Callable[[WorkerJob], WorkerReply],
    *,
    max_workers: int = 3,
    on_complete: Callable[[WorkerJob, WorkerReply], None] | None = None,
) -> list[WorkerReply]:
    """Run at most three jobs concurrently and collect every submitted reply.

    Replies and ``on_complete`` calls follow completion order, not task order.
    The callback runs on the coordinator thread and is called exactly once for
    each submitted job, including failed jobs.  A callback failure becomes a
    failed reply while the remaining jobs are still collected.

    ``job.timeout`` is a deadline for the *execute* implementation to enforce
    on its model call.  Python threads cannot safely interrupt that call: an
    overlong call is marked failed after it returns so its usage can still be
    accounted for by the coordinator.
    """
    pending = tuple(jobs)
    if len({job.task_id for job in pending}) != len(pending):
        raise ValueError("parallel codegen task IDs must be unique")
    if any(job.timeout <= 0 for job in pending):
        raise ValueError("parallel codegen timeouts must be positive")
    if not pending:
        return []

    completed: Queue[tuple[WorkerJob, object]] = Queue()
    replies: list[WorkerReply] = []
    with ThreadPoolExecutor(max_workers=max(1, min(3, max_workers)),
                            thread_name_prefix="arc-codegen") as pool:
        for job in pending:
            future = pool.submit(_execute_one, job, execute)
            future.add_done_callback(lambda done, item=job: completed.put((item, done)))

        for _ in pending:
            job, future = completed.get()
            # _execute_one catches ordinary worker exceptions.  This final
            # guard still accounts for a future that fails outside that path.
            try:
                reply = future.result()
            except Exception as exc:
                reply = WorkerReply(job.task_id, False, "",
                                    reason=f"worker future failed: {type(exc).__name__}: {exc}"[:1000])
            if on_complete is not None:
                try:
                    on_complete(job, reply)
                except Exception as exc:
                    reply = replace(reply, ok=False,
                                    reason=f"completion accounting failed: {type(exc).__name__}: {exc}"[:1000])
            replies.append(reply)
    return replies
