"""Private, bounded derived-test preparation during application generation.

The worker publishes immutable snapshots. Only the Flow thread may validate
and install them into the protected test suite.
"""
from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Lock, Thread
import time
from typing import Callable, Iterable


class DerivedSpecPipeline:
    def __init__(self, batches: Iterable[list[dict]], run_batch: Callable[[list[dict]], dict]):
        self._ready: Queue[dict] = Queue()
        self._stop = Event()
        self._batch_lock = Lock()
        self._started_ids: set[str] = set()
        self._resume = Event()
        self._resume.set()
        self._batches = list(batches)
        self._run_batch = run_batch
        self._thread = Thread(target=self._run, name="arc-derived-spec-pipeline", daemon=True)
        self._thread.start()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    @property
    def started_ids(self) -> set[str]:
        with self._batch_lock:
            return set(self._started_ids)

    def _run(self) -> None:
        for batch in self._batches:
            if not self.wait_until_resumed(float('inf')):
                break
            with self._batch_lock:
                if self._stop.is_set():
                    break
                self._started_ids.update(str(node.get('id')) for node in batch)
            try:
                result = self._run_batch(batch)
            except Exception as exc:
                result = {"error": str(exc)[:300], "node_ids": [str(node.get("id")) for node in batch]}
            self._ready.put(result)

    def poll_ready(self) -> list[dict]:
        ready = []
        while True:
            try:
                ready.append(self._ready.get_nowait())
            except Empty:
                return ready

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def wait_until_resumed(self, deadline: float) -> bool:
        """Do not start another model stage while code health is degraded."""
        while not self.stopping and time.monotonic() < deadline:
            if self._resume.wait(min(0.25, max(0, deadline - time.monotonic()))):
                return not self.stopping
        return False

    def wait(self, timeout: float) -> bool:
        self._thread.join(max(0.0, timeout))
        return not self._thread.is_alive()

    def close(self, timeout: float = 0.0) -> None:
        with self._batch_lock:
            self._stop.set()
        self._resume.set()
        self._thread.join(max(0.0, timeout))
