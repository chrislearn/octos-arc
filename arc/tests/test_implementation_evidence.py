"""Regressions from the Qwen GitHub/Sheet completed-run audit."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from arcbench_agent_runtime.events import EventClient
from generation_checks import cross_layer_advisories, missing_hook_return_errors
from implementation_evidence import initial_status
from main import Flow


class ImplementationEvidenceTests(unittest.TestCase):
    def test_refused_or_incomplete_reply_never_becomes_source_written(self):
        for outcome in ("guard_refused", "incomplete_blocks", "no_blocks"):
            with self.subTest(outcome=outcome):
                flow = Flow.__new__(Flow)
                flow.events = Mock()
                flow.alias_states = False
                flow.generation_state = {}
                flow.implementation_status = {}
                flow.implementation_evidence = {}
                flow.test_state = {}
                flow.derived_as_specs = True
                flow.app_source_digest = Mock(return_value="unchanged-source")
                flow.metric = Mock()
                flow.mark("implementation_started", "REQ-6-6")
                status = initial_status(ok=outcome != "no_blocks", outcome=outcome,
                                        changed=False, refused=outcome == "guard_refused")
                flow.record_implementation_evidence("REQ-6-6", status,
                                                    outcome=outcome, changed=False,
                                                    refused=outcome == "guard_refused")
                flow.mark("implementation_done", "REQ-6-6")
                self.assertEqual(flow.generation_state["REQ-6-6"], "attempted_with_risk")
                self.assertEqual(flow.implementation_status["REQ-6-6"], "contract_incomplete" if
                                 outcome != "guard_refused" else "partial_or_rejected")
                flow.events.mark_implementation_done.assert_called_once_with("REQ-6-6", None)
                flow.events.mark_implementation_failed.assert_not_called()

    def test_external_attempt_event_does_not_promote_unattributed_leaf(self):
        flow = Flow.__new__(Flow)
        flow.events = Mock()
        flow.alias_states = False
        flow.generation_state = {}
        flow.implementation_status = {}
        flow.implementation_evidence = {}
        flow.test_state = {}
        flow.mark("implementation_started", "REQ-1")
        flow.mark("implementation_done", "REQ-1", "turn ended")
        self.assertEqual(flow.implementation_status["REQ-1"], "attempted")
        self.assertEqual(flow.generation_state["REQ-1"], "attempted_with_risk")
        flow.events.mark_implementation_done.assert_called_once_with("REQ-1", "turn ended")

    def test_failure_does_not_erase_partial_evidence(self):
        flow = Flow.__new__(Flow)
        flow.events = Mock()
        flow.alias_states = False
        flow.generation_state = {}
        flow.implementation_status = {"REQ-1": "partial_or_rejected"}
        flow.implementation_evidence = {}
        flow.test_state = {}
        flow.mark("implementation_failed", "REQ-1")
        self.assertEqual(flow.implementation_status["REQ-1"], "partial_or_rejected")

    def test_sdk_completed_event_projects_to_platform_implemented(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner-events.jsonl"
            events = EventClient(SimpleNamespace(runner_events_path=path))
            writer = Mock()
            events.set_requirement_state_writer(writer)
            events.mark_implementation_done("REQ-1", "attempt ended; internal status=contract_incomplete")
            row = json.loads(path.read_text().splitlines()[0])
            self.assertEqual((row["phase"], row["status"]), ("implement", "completed"))
            writer.assert_called_once_with("REQ-1", "IMPLEMENTED", "implement")

    def test_shared_wave_is_not_attributed_as_leaf_source_write(self):
        flow = Flow.__new__(Flow)
        flow.events = Mock()
        flow.alias_states = False
        flow.generation_state = {}
        flow.implementation_status = {}
        flow.implementation_evidence = {}
        flow.test_state = {}
        flow.derived_as_specs = True
        flow.app_source_digest = Mock(return_value="wave-source")
        flow.metric = Mock()
        flow.mark("implementation_started", "REQ-5-2-1")
        flow.record_implementation_evidence("REQ-5-2-1", "implemented_unverified",
                                            outcome="whole_app_wave_1", changed=False)
        flow.mark("implementation_done", "REQ-5-2-1")
        self.assertEqual(flow.generation_state["REQ-5-2-1"], "attempted_with_risk")
        self.assertEqual(flow.implementation_status["REQ-5-2-1"], "implemented_unverified")

    def test_source_paths_remain_auditable_after_acceptance_promotion(self):
        flow = Flow.__new__(Flow)
        flow.events = Mock()
        flow.alias_states = False
        flow.generation_state = {}
        flow.implementation_status = {}
        flow.implementation_evidence = {}
        flow.test_state = {}
        flow.derived_as_specs = False
        flow.app_source_digest = Mock(return_value="source")
        flow.metric = Mock()
        flow.record_implementation_evidence("REQ-1", "implemented_unverified",
                                            outcome="complete_blocks", changed=True,
                                            changed_paths=["frontend/src/Page.jsx"])
        flow.mark("test_passed", "REQ-1")
        self.assertEqual(flow.implementation_status["REQ-1"], "behavior_verified")
        self.assertEqual(flow.implementation_evidence["REQ-1"]["changed_paths"],
                         ["frontend/src/Page.jsx"])

    def test_missing_delete_operation_on_literal_hook_return(self):
        sources = {
            "frontend/src/hooks/useWorkbook.js":
                "export function useWorkbook(id) { const remove = async () => {}; "
                "return { workbook: id, remove }; }",
            "frontend/src/pages/EditorPage.jsx":
                "import { useWorkbook } from '../hooks/useWorkbook.js';\n"
                "export default function EditorPage() {\n"
                "  const { workbook, deleteWorksheet } = useWorkbook('w');\n"
                "  return <button onClick={() => deleteWorksheet('s')}>{workbook}</button>;\n}",
        }
        changed = ["frontend/src/pages/EditorPage.jsx"]
        errors = missing_hook_return_errors(sources, changed)
        self.assertEqual(len(errors), 1)
        self.assertIn("deleteWorksheet", errors[0])
        sources["frontend/src/hooks/useWorkbook.js"] = sources["frontend/src/hooks/useWorkbook.js"].replace(
            "return { workbook: id, remove }", "return { workbook: id, deleteWorksheet: remove }")
        self.assertEqual(missing_hook_return_errors(sources, changed), [])

    def test_nested_callback_return_does_not_define_hook_contract(self):
        sources = {
            "frontend/src/hooks/useThing.js":
                "export function useThing() { const helper = () => { return { phantom: true }; }; "
                "return { actual: helper }; }",
            "frontend/src/Thing.jsx":
                "import {useThing} from './hooks/useThing.js';\n"
                "export function Thing() { const { phantom } = useThing(); return <p>{phantom}</p>; }",
        }
        errors = missing_hook_return_errors(sources, ["frontend/src/Thing.jsx"])
        self.assertEqual(len(errors), 1)
        self.assertIn("phantom", errors[0])

    def test_reports_public_number_and_member_shape_drift_as_advisories(self):
        sources = {
            "backend/routes/pulls.js":
                "app.post('/api/repos/:owner/:repo/pulls', (req,res) => { "
                "const pr = {id: crypto.randomUUID(), number: 2}; res.json(pr); });",
            "backend/routes/pulls_detail.js":
                "app.post('/api/repos/:owner/:repo/pulls/:id/reviews', (req,res) => { "
                "const id = req.params.id; const number = parseInt(id, 10); res.json(number); });",
            "frontend/src/Review.jsx":
                "requestJson(`/api/repos/${owner}/${repo}/pulls/${pullRequest.id}/reviews`)",
            "backend/routes/orgs.js": "const org = {members: [req.userId]};",
            "backend/routes/repos.js": "org.members.some(m => m.user_id === req.userId);",
        }
        warnings = cross_layer_advisories(sources, sources)
        self.assertTrue(any("NUMERIC_ROUTE_ID" in item for item in warnings))
        self.assertTrue(any("MEMBER_SHAPE" in item for item in warnings))
        self.assertEqual(cross_layer_advisories(sources, ["frontend/src/Unrelated.jsx"]), [])

    def test_quality_summary_keeps_smoke_separate_from_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = Flow.__new__(Flow)
            flow.output_dir = Path(directory)
            flow.app_source_digest = Mock(return_value="source")
            flow.derived_case_reviews = {
                ("A", "entry"): {"node_id": "A", "status": "approved_smoke_only"},
                ("B", "edit"): {"node_id": "B", "status": "approved_behavior"},
            }
            flow.trusted_derived_case = Mock(side_effect=lambda node, title: node == "B")
            flow.quality_observations = {}
            flow.phase_plan = None
            flow.generation_state = {}
            flow.implementation_status = {}
            flow.implementation_evidence = {}
            flow.test_verdict = {}
            flow.test_state = {}
            flow.write_quality_summary(startable=True, node_ids=["A", "B"])
            result = json.loads((flow.output_dir / ".arc/quality-summary.json").read_text())
            self.assertEqual(result["derived_behavior"]["approved_leaf_count"], 1)
            self.assertEqual(result["derived_behavior"]["leaves_without_approved_behavior"], ["A"])


if __name__ == "__main__":
    unittest.main()
