"""The codegen scheduler must isolate execution and account for every reply."""
import threading
import time
import unittest

from parallel_codegen_workers import WorkerJob, WorkerReply, run_parallel


class ParallelCodegenWorkerTests(unittest.TestCase):
    def test_three_workers_complete_out_of_order_with_coordinator_callbacks(self):
        started = {name: threading.Event() for name in "abc"}
        release = {name: threading.Event() for name in "abc"}
        callback_thread = []
        callbacks = []
        result = []
        coordinator = threading.current_thread()

        def execute(job):
            started[job.task_id].set()
            self.assertTrue(release[job.task_id].wait(2))
            return WorkerReply(job.task_id, True, job.task_id, tokens=1, requests=1)

        def run():
            result.extend(run_parallel(
                [WorkerJob(name, name, 3) for name in "abc"], execute,
                on_complete=lambda job, reply: (
                    callback_thread.append(threading.current_thread()),
                    callbacks.append((job.task_id, reply.tokens)))))

        thread = threading.Thread(target=run)
        thread.start()
        try:
            for event in started.values():
                self.assertTrue(event.wait(2))
            for name in "bca":
                release[name].set()
                limit = time.monotonic() + 2
                while len(callbacks) < "bca".index(name) + 1 and time.monotonic() < limit:
                    time.sleep(0.001)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([reply.task_id for reply in result], list("bca"))
            self.assertEqual(callbacks, [(name, 1) for name in "bca"])
            self.assertTrue(all(item is thread for item in callback_thread))
            self.assertIsNot(thread, coordinator)
        finally:
            for event in release.values():
                event.set()
            thread.join(2)

    def test_cap_is_three_even_when_more_workers_are_requested(self):
        active = 0
        peak = 0
        lock = threading.Lock()
        first_wave = threading.Event()
        release = threading.Event()

        def execute(job):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 3:
                    first_wave.set()
            self.assertTrue(release.wait(2))
            with lock:
                active -= 1
            return WorkerReply(job.task_id, True, "ok")

        result = []
        thread = threading.Thread(target=lambda: result.extend(run_parallel(
            [WorkerJob(str(i), "", 3) for i in range(6)], execute, max_workers=20)))
        thread.start()
        try:
            self.assertTrue(first_wave.wait(2))
            self.assertEqual(peak, 3)
        finally:
            release.set()
            thread.join(2)
        self.assertEqual(len(result), 6)
        self.assertTrue(all(reply.ok for reply in result))

    def test_failures_and_callback_errors_do_not_drop_other_replies(self):
        accounted = []

        def execute(job):
            if job.task_id == "raise":
                raise RuntimeError("model unavailable")
            return WorkerReply(job.task_id, True, "ok", tokens=7, requests=1,
                               usage_records=("usage",), ledger_records=("ledger",))

        def account(job, reply):
            accounted.append((job.task_id, reply.tokens))
            if job.task_id == "callback":
                raise RuntimeError("ledger unavailable")

        replies = run_parallel([WorkerJob(name, "", 3) for name in
                                ("ok", "raise", "callback")], execute, on_complete=account)
        by_id = {reply.task_id: reply for reply in replies}
        self.assertEqual(set(by_id), {"ok", "raise", "callback"})
        self.assertEqual(set(accounted), {("ok", 7), ("raise", 0), ("callback", 7)})
        self.assertTrue(by_id["ok"].ok)
        self.assertFalse(by_id["raise"].ok)
        self.assertIn("model unavailable", by_id["raise"].reason)
        self.assertFalse(by_id["callback"].ok)
        self.assertEqual(by_id["callback"].tokens, 7)
        self.assertEqual(by_id["callback"].usage_records, ("usage",))
        self.assertIn("completion accounting failed", by_id["callback"].reason)

    def test_bad_task_ids_and_replies_fail_closed(self):
        job = WorkerJob("a", "", 3)
        with self.assertRaises(ValueError):
            run_parallel([job, job], lambda item: WorkerReply(item.task_id, True, ""))

        replies = run_parallel([job], lambda item: WorkerReply("other", True, "",
                                tokens=5, requests=1, usage_records=("usage",)))
        self.assertFalse(replies[0].ok)
        self.assertEqual(replies[0].task_id, "a")
        self.assertEqual(replies[0].tokens, 5)
        self.assertEqual(replies[0].usage_records, ("usage",))

    def test_late_reply_is_rejected_after_usage_is_preserved(self):
        reply, = run_parallel(
            [WorkerJob("late", "", 1e-9)],
            lambda job: WorkerReply(job.task_id, True, "candidate", tokens=17,
                                    requests=1, ledger_records=("request",)))
        self.assertFalse(reply.ok)
        self.assertIn("exceeded", reply.reason)
        self.assertEqual(reply.tokens, 17)
        self.assertEqual(reply.ledger_records, ("request",))
