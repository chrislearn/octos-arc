"""A bounded lease shared by the upstream collector and stdio turn waiter."""
import threading
import time


class ProgressDeadline:
    def __init__(self, timeout, extension=120, idle=120, clock=time.monotonic):
        self.clock = clock
        self.base = clock() + max(0, timeout)
        self.hard = self.base + max(0, extension)
        self.idle = max(1, idle)
        self.last = None
        self.closed = False
        self._lock = threading.Lock()

    def progress(self):
        with self._lock:
            now = self.clock()
            # Late/stale chunks must not resurrect an expired turn.
            if not self.closed and now < self._deadline():
                self.last = now

    def _deadline(self):
        return min(self.hard, max(self.base, self.last + self.idle if self.last is not None else self.base))

    def remaining(self):
        with self._lock:
            return 0 if self.closed else max(0, self._deadline() - self.clock())

    def close(self):
        with self._lock:
            self.closed = True
