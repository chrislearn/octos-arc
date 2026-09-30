"""Observable lifecycle follows admitted spec work and real child progress."""
import os
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_whole_app_v5 as fixtures


class DesignProgressTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.DerivedSpecsAsAcceptanceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow = fixture.flow
        self.nodes = fixture._derived()
        self.flow.prepare_derived_tests(self.nodes)
        self.flow.adopt_derived_specs(["A", "B", "C"])
        self.flow.final_phase_reserve = Mock(return_value=0)
        self.flow.text_turn = Mock(return_value=(False, "provider unavailable"))

    def started(self):
        return [call.args[0] for call in self.flow.events.mark_design_started.call_args_list]

    def test_generation_announces_only_admitted_chunk_before_model_call(self):
        def reply(*args, **kwargs):
            self.assertEqual(self.started(), ["A"])
            self.flow.events.mark_design_done.assert_not_called()
            return False, "provider unavailable"
        self.flow.text_turn.side_effect = reply
        with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_LLM_BATCH": "1",
                                     "OCTOS_ARC_DERIVED_LLM_REQUESTS": "1"}):
            self.flow.augment_derived_tests(self.nodes)
        self.flow.text_turn.assert_called_once()
        self.assertEqual(self.started(), ["A"])
        self.flow.mark_designed(self.nodes)
        self.flow.events.mark_design_done.assert_not_called()

    def test_zero_budget_does_not_announce_work(self):
        with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_LLM_REQUESTS": "0"}):
            self.flow.augment_derived_tests(self.nodes)
        self.assertEqual(self.started(), [])
        self.flow.text_turn.assert_not_called()

    def test_context_rejection_does_not_announce_work(self):
        self.flow.codegen_context_chars = Mock(return_value=1)
        self.flow.augment_derived_tests(self.nodes)
        self.assertEqual(self.started(), [])
        self.flow.text_turn.assert_not_called()

    def test_wound_down_does_not_announce_work(self):
        self.flow.wound_down.return_value = True
        self.flow.augment_derived_tests(self.nodes)
        self.assertEqual(self.started(), [])
        self.flow.text_turn.assert_not_called()

    def test_audit_announces_only_admitted_case_before_model_call(self):
        def reply(*args, **kwargs):
            self.assertEqual(self.started(), ["A"])
            return False, "provider unavailable"
        self.flow.text_turn.side_effect = reply
        with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_CASE_REVIEW_REQUESTS": "1"}):
            self.flow.review_derived_cases({"A", "B", "C"})
        self.flow.text_turn.assert_called_once()
        self.assertEqual(self.started(), ["A"])
        self.flow.events.mark_design_done.assert_not_called()

    def test_design_done_requires_started_and_independent_readiness(self):
        flow = self.flow
        flow.start_derived_designs(["A", "B"], "generating")
        flow.derived_review_needed = Mock(side_effect=lambda node: node == "B")
        flow.mark_designed(self.nodes)
        self.assertEqual([c.args[0] for c in flow.events.mark_design_done.call_args_list], ["A"])
        flow.mark("design_done", "B", "global design ended")
        flow.mark_designed(self.nodes)
        self.assertEqual(flow.events.mark_design_done.call_count, 1)
        flow.derived_review_needed = Mock(return_value=False)
        flow.finish_derived_designs(["B"])
        self.assertEqual([c.args[0] for c in flow.events.mark_design_done.call_args_list], ["A", "B"])
        self.assertEqual(self.started(), ["A", "B"])

    def test_unreviewed_real_specs_never_mark_designed(self):
        self.flow.start_derived_designs(["A", "B", "C"], "auditing")
        self.flow.finish_derived_designs(["A", "B", "C"])
        self.flow.events.mark_design_done.assert_not_called()

    def test_parent_and_ancestor_track_real_child_progress(self):
        flow = self.flow
        flow.folder_children = {"GROUP": ["A", "B"], "ROOT": ["A", "B", "C"]}
        flow.start_derived_designs(["A"], "generating")
        self.assertEqual(self.started(), ["A", "GROUP", "ROOT"])
        flow.derived_review_needed = Mock(return_value=False)
        flow.finish_derived_designs(["A"])
        self.assertEqual([c.args[0] for c in flow.events.mark_design_done.call_args_list], ["A"])
        flow.start_derived_designs(["B"], "generating")
        flow.finish_derived_designs(["B"])
        self.assertEqual([c.args[0] for c in flow.events.mark_design_done.call_args_list], ["A", "B", "GROUP"])
        flow.mark("implementation_started", "A")
        flow.start_derived_designs(["C"], "generating")
        flow.finish_derived_designs(["C"])
        self.assertEqual(flow._folder_states["ROOT"], "implementation_started")
        self.assertEqual(self.started().count("ROOT"), 1)

    def test_late_spec_work_does_not_rewind_implementation_or_test_state(self):
        flow = self.flow
        flow.folder_children = {"ROOT": ["A"]}
        flow.mark("implementation_started", "A")
        flow.mark("test_passed", "A")
        flow.events.reset_mock()
        flow.start_derived_designs(["A"], "late correction")
        flow._derived_design_ready = {"A"}
        flow.mark("design_done", "A")
        flow.events.assert_not_called()
        self.assertEqual(flow.events.method_calls, [])
        self.assertEqual(flow._node_lifecycle["A"], "test_passed")
        self.assertEqual(flow._folder_states["ROOT"], "test_passed")

    def test_final_folder_verdict_does_not_fabricate_phase_history(self):
        flow = self.flow
        flow.folder_children = {"ROOT": ["A", "B", "C"]}
        flow.test_verdict = {"A": True, "B": False}
        flow.mark_folders()
        flow.mark_folders()
        self.assertEqual([c[0] for c in flow.events.method_calls], ["mark_test_failed"])
        flow.test_verdict = dict.fromkeys(["A", "B", "C"], True)
        flow.mark_folders()
        flow.events.mark_test_passed.assert_called_once()

    def test_finalization_is_idempotent_after_implementation_without_test(self):
        flow = self.flow
        flow.folder_children = {"ROOT": ["A"]}
        flow.mark("implementation_started", "A")
        flow.mark("implementation_done", "A")
        flow.events.reset_mock()
        flow.mark_folders()
        flow.mark_folders()
        self.assertEqual([c[0] for c in flow.events.method_calls], ["mark_test_failed"])

    def test_global_and_codegen_design_events_cannot_admit_unstarted_specs(self):
        flow = self.flow
        flow.mark_designed(self.nodes)
        flow.mark("design_started", "A", "covered by whole-application design")
        flow.mark("design_done", "A", "covered by whole-application design")
        self.assertEqual(flow.events.method_calls, [])
        flow.mark("implementation_started", "A")
        self.assertEqual([c[0] for c in flow.events.method_calls], ["mark_implementation_started"])

    def test_real_event_client_flushes_leaf_and_parent_before_generation(self):
        from arcbench_agent_runtime.events import EventClient
        flow = self.flow
        event_path = flow.output_dir / "events.jsonl"
        flow.events = EventClient(SimpleNamespace(runner_events_path=event_path))
        written = {}
        flow.events.set_requirement_state_writer(lambda node, state, phase: written.update({node: state}))
        flow.folder_children = {"ROOT": ["A", "B", "C"]}
        def reply(*args, **kwargs):
            self.assertEqual(written, {"A": "DESIGNING", "ROOT": "DESIGNING"})
            rows = [json.loads(line) for line in event_path.read_text().splitlines()]
            self.assertEqual([(r["node_id"], r["phase"], r["status"]) for r in rows],
                             [("A", "design", "running"), ("ROOT", "design", "running")])
            return False, "unavailable"
        flow.text_turn.side_effect = reply
        with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_LLM_BATCH": "1",
                                     "OCTOS_ARC_DERIVED_LLM_REQUESTS": "1"}):
            flow.augment_derived_tests(self.nodes)
        flow.text_turn.assert_called_once()

    def test_official_specs_keep_design_lifecycle_and_parent_updates(self):
        flow = self.flow
        flow.derived_as_specs = False
        flow.folder_children = {"ROOT": ["A", "B", "C"]}
        flow.mark_designed(self.nodes)
        self.assertEqual(self.started(), ["A", "ROOT", "B", "C"])
        self.assertEqual([c.args[0] for c in flow.events.mark_design_done.call_args_list], ["A", "B", "C", "ROOT"])
        flow.mark_designed(self.nodes)
        self.assertEqual(flow.events.mark_design_done.call_count, 4)


if __name__ == "__main__":
    unittest.main()
