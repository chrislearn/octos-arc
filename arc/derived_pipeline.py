"""Private, bounded derived-test preparation during application generation.

The worker publishes immutable snapshots. Only the Flow thread may validate
and install them into the protected test suite.
"""
from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable, Iterable


class DerivedSpecPipeline:
    def __init__(self, batches: Iterable[list[dict]], run_batch: Callable[[list[dict]], dict]):
        self._ready: Queue[dict] = Queue()
        self._stop = Event()
        self._batches = list(batches)
        self._run_batch = run_batch
        self._thread = Thread(target=self._run, name="arc-derived-spec-pipeline", daemon=True)
        self._thread.start()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def _run(self) -> None:
        for batch in self._batches:
            if self.stopping:
                break
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

    def close(self, timeout: float = 0.0) -> None:
        self._stop.set()
        self._thread.join(max(0.0, timeout))
