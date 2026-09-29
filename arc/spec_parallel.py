"""Bounded, ordered model fan-out for tool-free derived-spec requests.

Workers may only return text. The Flow thread owns every generated file,
review ledger, status transition, and protected-tree snapshot.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from collections import deque
import json
import time
from typing import Callable, Iterable, Iterator


@dataclass(frozen=True)
class SpecRequest:
    prompt: str
    timeout: int
    label: str
    system: str
    reservation: int
    deadline: float = float("inf")


@dataclass
class SpecReply:
    ok: bool
    text: str
    tokens: int = 0
    requests: int = 0
    usage_lines: tuple[str, ...] = ()
    ledger_lines: tuple[str, ...] = ()
    elapsed: float = 0.0


class OrderedSpecRequests:
    """Keep at most ``workers`` requests in flight; publish in source order.

    Admission reserves the estimated upper bound before dispatch. A rejected
    request and every later request is returned as None, so the caller may use
    its existing serial path. The coordinator calls account before yielding a
    completed reply, while all writes stay on the coordinator thread.
    """

    def __init__(self, workers: int, execute: Callable[[SpecRequest], SpecReply],
                 admissible: Callable[[SpecRequest, int, int], bool], account: Callable[[SpecRequest, SpecReply], None],
                 on_submit: Callable[[SpecRequest], None] | None = None,
                 reservation_changed: Callable[[int, int], None] | None = None):
        self.workers = max(1, workers)
        self.execute = execute
        self.admissible = admissible
        self.account = account
        self.on_submit = on_submit or (lambda _job: None)
        self.reservation_changed = reservation_changed or (lambda _tokens, _turns: None)
        self.reserved = 0
        self.active = 0

    def ordered(self, requests: Iterable[SpecRequest]) -> Iterator[SpecReply | None]:
        jobs = iter(requests)
        pending = deque()
        exhausted = False
        capacity = 1  # populate the provider's common prefix before fan-out
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="arc-spec") as executor:
            def fill() -> None:
                nonlocal exhausted
                while len(pending) < capacity and not exhausted:
                    try:
                        job = next(jobs)
                    except StopIteration:
                        exhausted = True
                        break
                    if not self.admissible(job, self.reserved + job.reservation, len(pending) + 1):
                        pending.append((job, None))
                        exhausted = True
                        break
                    self.on_submit(job)
                    self.reserved += job.reservation
                    self.active += 1
                    self.reservation_changed(self.reserved, self.active)
                    pending.append((job, executor.submit(self.execute, job)))

            fill()
            try:
                while pending:
                    job, future = pending.popleft()
                    if future is None:
                        yield None
                        break
                    reply = self._finish(job, future)
                    capacity = self.workers
                    fill()
                    yield reply
            finally:
                # A deadline may stop the caller before it consumes prefetched
                # work. Every sent request still enters the global token ledger.
                while pending:
                    job, future = pending.popleft()
                    if future is not None:
                        self._finish(job, future)

    def _finish(self, job, future) -> SpecReply:
        try:
            reply = future.result()
        except Exception as exc:  # a worker failure never grants a spec
            reply = SpecReply(False, f"isolated spec worker failed: {exc}"[:1000])
        self.reserved -= job.reservation
        self.active -= 1
        self.account(job, reply)
        self.reservation_changed(self.reserved, self.active)
        return reply


def reservation_tokens(prompt: str, requests_per_turn: int = 3, output_cap: int = 32768) -> int:
    """Conservative input plus advertised output for every possible retry."""
    return requests_per_turn * (len(prompt.encode("utf-8")) + 8192 + output_cap)


def append_worker_records(main_proxy, reply: SpecReply) -> None:
    """Bring private-proxy usage into the run-wide guard and audit log."""
    with main_proxy._lock:
        main_proxy.total_tokens += reply.tokens
        main_proxy.total_requests += reply.requests
        if main_proxy.log_path:
            with main_proxy.log_path.open("a", encoding="utf-8") as stream:
                for line in reply.usage_lines:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    row["parallel_spec_worker"] = True
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            ledger = main_proxy.log_path.parent / "request-ledger.jsonl"
            with ledger.open("a", encoding="utf-8") as stream:
                for line in reply.ledger_lines:
                    stream.write(line.rstrip("\n") + "\n")
