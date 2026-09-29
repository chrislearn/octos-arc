"""Concurrent model text may overlap; official spec writes stay ordered."""
import argparse
import json
import os
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from main import Flow, LlmProxy, OctosDriver
from obligation_planning import prepare_obligations
from spec_parallel import OrderedSpecRequests, SpecReply, SpecRequest


def job(name):
    return SpecRequest(name, 30, "derived scenario review", "audit", 100)


class OrderedRequestsTests(unittest.TestCase):
    def test_real_worker_wrapper_uses_private_kernel_proxy_and_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            (config / "config.json").write_text('{"provider":"openai","model":"test-model"}')
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.llm_proxy = LlmProxy("http://localhost:1/v1", "low")
            flow.driver = OctosDriver("octos", root,
                                      {"OCTOS_CONFIG_DIR": str(config), "_ARC_MODEL": "test-model"},
                                      root / "data", 1, root / "events.jsonl")
            flow.remaining = Mock(return_value=10000)
            flow.final_phase_reserve = Mock(return_value=0)
            flow.review_budget_spent = Mock(return_value=False)
            flow.metric = Mock()
            workspaces = []
            proxy_urls = []
            seen_reservations = []
            barrier = threading.Barrier(2, timeout=3)
            def fake_run(driver, prompt, _timeout, monitor=None):
                self.assertTrue(driver.tools_disabled)
                self.assertNotEqual(driver.cwd, root)
                self.assertNotEqual(driver.data_dir, root / "data")
                workspaces.append(driver.cwd)
                proxy_urls.append(driver.env["_ARC_BASE_URL"])
                seen_reservations.append(flow.llm_proxy.external_reserved_tokens)
                if prompt != "A":
                    barrier.wait()
                return True, prompt
            with patch.dict(os.environ, {"OCTOS_ARC_SPEC_PARALLEL_WORKERS": "2"}), \
                    patch.object(OctosDriver, "run", fake_run):
                pool = flow.isolated_spec_requests(3)
                self.assertIsNotNone(pool)
                self.assertEqual([reply.text for reply in pool.ordered(map(job, "ABC"))], list("ABC"))
            self.assertEqual(len(set(workspaces)), 3)
            self.assertEqual(len(set(proxy_urls)), 3)
            self.assertTrue(all(amount > 0 for amount in seen_reservations))
            self.assertEqual(flow.llm_proxy.external_reserved_tokens, 0)
            self.assertEqual(flow.llm_proxy.external_reserved_turns, 0)
            self.assertEqual(flow.review_turn_count, 3)
            flow.llm_proxy.server.server_close()

    def test_main_proxy_absolute_guard_includes_worker_reservations(self):
        proxy = LlmProxy("http://localhost:1/v1", "low")
        try:
            proxy.begin_turn(3)
            proxy.max_total_tokens_abs = 100
            proxy.total_tokens = 40
            proxy.external_reserved_tokens = 60
            status, payload, _headers = proxy._request_upstream(
                "POST", "/chat/completions", b'{"model":"test","messages":[]}', {})
            self.assertEqual(status, 402)
            self.assertIn(b"local_token_budget_exhausted", payload)
            self.assertEqual(proxy.total_requests, 0)
        finally:
            proxy.server.server_close()

    def test_warm_prefix_then_two_requests_overlap_and_commit_in_order(self):
        barrier = threading.Barrier(2, timeout=2)
        started = []
        committed = []
        def execute(request):
            started.append(request.prompt)
            if request.prompt != "A":
                barrier.wait()
            return SpecReply(True, request.prompt, tokens=10)
        pool = OrderedSpecRequests(2, execute, lambda _job, reserved, _count: reserved <= 200,
                                   lambda request, reply: committed.append((request.prompt, reply.text)))
        self.assertEqual([reply.text for reply in pool.ordered(map(job, "ABC"))], list("ABC"))
        self.assertEqual(committed, [("A", "A"), ("B", "B"), ("C", "C")])
        self.assertEqual(started[0], "A")

    def test_early_close_accounts_all_prefetched_requests(self):
        accounted = []
        pool = OrderedSpecRequests(2, lambda request: SpecReply(True, request.prompt, tokens=7),
                                   lambda *_args: True,
                                   lambda request, _reply: accounted.append(request.prompt))
        results = pool.ordered(map(job, "ABCD"))
        self.assertEqual(next(results).text, "A")
        results.close()
        self.assertEqual(accounted, list("ABC"))

    def test_reservation_rejects_following_request(self):
        used = 0
        def account(_request, reply):
            nonlocal used
            used += reply.tokens
        pool = OrderedSpecRequests(2, lambda request: SpecReply(True, request.prompt, tokens=100),
                                   lambda _job, reserved, _count: used + reserved <= 150, account)
        self.assertEqual([reply.text if reply else None for reply in pool.ordered(map(job, "AB"))], ["A", None])


class ScenarioCommitTests(unittest.TestCase):
    def test_obligation_extractions_overlap_and_independent_reviews_stay_ordered(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"OCTOS_ARC_OBLIGATION_BATCH_LEAVES": "1"}):
            root = Path(directory)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            nodes = [{"id": name, "description": f"The saved {name} record remains visible after refresh."}
                     for name in "ABC"]
            flow.requirement_tree = {"id": "ROOT", "description": "Every saved record remains visible after refresh.",
                                     "children": nodes}
            flow.derived_nodes = nodes
            flow.remaining = Mock(return_value=10000)
            flow.final_phase_reserve = Mock(return_value=0)
            flow.wound_down = Mock(return_value=False)
            flow.review_budget_spent = Mock(return_value=False)
            flow.derived_preflight_tokens_spent = Mock(return_value=False)
            flow.metric = Mock()
            barrier = threading.Barrier(2, timeout=2)
            def reply_for(prompt):
                ancestry = json.loads(prompt.split("LEAF ANCESTRY (every listed source needs coverage):\n")[1].split("\nIndependently review")[0])
                name = next(iter(ancestry))
                obligations = [{"requirement_id": owner, "applies_to": [name],
                                "quote": flow.requirement_tree["description"] if owner == "ROOT" else nodes[ord(name)-65]["description"],
                                "branch": "success", "outcome": "The saved record remains visible after refresh."}
                               for owner in ("ROOT", name)]
                return json.dumps({"obligations": obligations, "gaps": []})
            def execute(request):
                name = next(iter(json.loads(request.prompt.split(
                    "LEAF ANCESTRY (every listed source needs coverage):\n")[1])))
                if name != "A":
                    barrier.wait()
                return SpecReply(True, reply_for(request.prompt), tokens=100)
            flow.text_turn = Mock(side_effect=lambda prompt, *_args, **_kwargs: (True, reply_for(prompt)))
            def make_pool(_count, *, allowed):
                return OrderedSpecRequests(2, execute, lambda request, _reserved, _count: allowed(request),
                                           lambda request, _reply: flow.note_turn(request.label))
            flow.isolated_spec_requests = make_pool
            prepare_obligations(flow, nodes)
            self.assertEqual(flow.text_turn.call_count, 3)
            self.assertEqual([flow.derived_obligation_status[name]["status"] for name in "ABC"],
                             ["reviewed"] * 3)
            self.assertEqual({row["applies_to"][0] for row in flow.derived_obligations}, set("ABC"))

    def test_parallel_proposals_write_separate_leaf_files_in_dispatch_order(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"OCTOS_ARC_DERIVED_LLM_BATCH": "1"}):
            root = Path(directory)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            nodes = []
            for name in "ABC":
                nodes.append({"id": name, "name": name, "type": "ATOMIC",
                              "description": f"Feature {name} shows Done {name}.",
                              "scenarios": [{"name": f"{name}: Scenario 1", "steps": [
                                  {"keyword": "WHEN", "content": f"The visitor opens {name} somehow and clicks “Open {name}”."},
                                  {"keyword": "THEN", "content": f"The page shows “Done {name}”."}]}]})
            flow.requirement_tree = {"id": "ROOT", "children": nodes}
            flow.prepare_derived_tests(nodes)
            flow.remaining = Mock(return_value=10000)
            flow.final_phase_reserve = Mock(return_value=0)
            flow.text_turn = Mock(side_effect=AssertionError("unexpected serial model request"))
            active = 0
            max_active = 0
            lock = threading.Lock()
            def execute(request):
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                match = re.search(r"### \[[^\]]+\] ([ABC]): Scenario 1", request.prompt)
                self.assertIsNotNone(match)
                name = match.group(1)
                time.sleep(0.03 if name == "B" else 0.01)
                with lock:
                    active -= 1
                reply = {"scenarios": [{"title": f"{name}: Scenario 1", "signed_in": False,
                                        "confidence": 0.9, "steps": [
                                            {"op": "click", "target": f"Open {name}"},
                                            {"op": "expect_visible", "target": f"Done {name}"}]}]}
                return SpecReply(True, json.dumps(reply), tokens=100, elapsed=0.03)
            def make_pool(_count, *, on_submit, allowed):
                return OrderedSpecRequests(2, execute, lambda request, _reserved, _count: allowed(request),
                                           lambda request, _reply: flow.note_turn(request.label), on_submit)
            flow.isolated_spec_requests = make_pool
            flow.augment_derived_tests(nodes)
            self.assertEqual(max_active, 2)
            self.assertEqual(flow.derived_review_requests, 3)
            self.assertEqual(flow.text_turn.call_count, 0)
            self.assertEqual([row["status"] for row in json.loads(
                (flow.derived_tests_dir / "review/plan.json").read_text())["targets"]],
                ["accepted"] * 3)
            for name in "ABC":
                self.assertIn(f"{name}: Scenario 1 [model]", (flow.derived_tests_dir / f"{name}.spec.ts").read_text())

    def test_audit_requests_overlap_but_stale_file_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"OCTOS_ARC_DERIVED_CASE_REVIEW_BATCH": "1"}):
            root = Path(directory)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_tests_dir = root / "derived-tests"
            flow.derived_tests_dir.mkdir()
            flow.derived_nodes = [{"id": name, "description": f"Show {name}."} for name in "ABC"]
            flow.requirement_tree = {"id": "ROOT", "children": flow.derived_nodes}
            flow.derived_case_reviews = {}
            flow.wound_down = Mock(return_value=False)
            flow.review_budget_spent = Mock(return_value=False)
            flow.remaining = Mock(return_value=10000)
            flow.final_phase_reserve = Mock(return_value=0)
            flow.metric = Mock()
            flow.text_turn = Mock(side_effect=AssertionError("unexpected serial audit"))
            flow.llm_proxy = LlmProxy("http://localhost:1/v1", "low")
            flow.driver = OctosDriver("octos", root, {}, root / "data", 1, root / "events.jsonl")
            rows = []
            for name in "ABC":
                source = f"test('{name}', () => {{}});"
                (flow.derived_tests_dir / f"{name}.spec.ts").write_text(source)
                from derived_case_review import sha
                rows.append({"id": f"case-{name}", "node_id": name, "title": name,
                             "status": "unreviewed", "requirement": f"Show {name}.", "case": "assert state",
                             "outcome": f"Show {name}.", "file": f"{name}.spec.ts", "file_hash": sha(source)})
            barrier = threading.Barrier(2, timeout=2)
            def execute(request):
                match = re.search(r'"id": "case-([ABC])"', request.prompt)
                self.assertIsNotNone(match)
                name = match.group(1)
                if name != "A":
                    barrier.wait()
                if name == "C":
                    (flow.derived_tests_dir / "C.spec.ts").write_text("changed during audit")
                return SpecReply(True, json.dumps([{"id": f"case-{name}", "status": "needs_correction",
                                                   "reason": "Missing state assertion"}]), tokens=10)
            def make_pool(_count, *, on_submit, allowed):
                return OrderedSpecRequests(2, execute, lambda request, _reserved, _count: allowed(request),
                                           lambda request, _reply: flow.note_turn(request.label), on_submit)
            flow.isolated_spec_requests = make_pool
            with patch("main.collect_cases", return_value=rows):
                flow.review_derived_cases(set("ABC"))
            self.assertEqual(flow.derived_case_review_requests, 3)
            self.assertEqual(flow.text_turn.call_count, 0)
            self.assertEqual([row["review_request"] for row in rows], [1, 2, 3])
            self.assertEqual([row["status"] for row in rows],
                             ["needs_correction", "needs_correction", "unreviewed"])
            self.assertIn("stale_audit_input", (flow.derived_tests_dir / "review/audit-3.txt").read_text())
            flow.llm_proxy.server.server_close()


if __name__ == "__main__":
    unittest.main()
