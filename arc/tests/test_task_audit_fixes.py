"""Task-neutral regression coverage for the cross-task audit."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml
import main as m
from acceptance import RunSummary, TestOutcome
from codegen import write_files
from generic_template import install_generic_template
from web_stack import recommended_capabilities


class AuditPlanningTests(unittest.TestCase):
    def test_all_task_catalogs_survive_the_wave_budget(self):
        for path in sorted((m.BUNDLE_DIR / "tasks").glob("*/requirements.yaml")):
            tree = yaml.safe_load(path.read_text())
            outline = m.tree_outline(tree, 12000)
            self.assertLessEqual(len(outline), 12000, path)
            def visit(node):
                self.assertIn(str(node["id"]) + " [", outline, path)
                for child in node.get("children") or []:
                    visit(child)
            visit(tree)

    def test_unique_scenario_outcomes_enter_design(self):
        tree = {"id": "A", "description": "Vote", "scenarios": [
            {"steps": [{"keyword": "THEN", "content": "The author gains 10 reputation."}]}]}
        self.assertIn("gains 10 reputation", m.tree_outline(tree))

    def test_design_budget_is_combined_json_safe_and_cache_stable(self):
        design = {"data_model": {"records": {"id": "string"}}, "notes": "n" * 5000,
                  "routes": [{"path": f"/api/r{i}", "method": "GET", "requirements": [f"REQ-{i}"],
                              "purpose": f"purpose {i}"} for i in range(20)],
                  "contracts": [{"requirements": ["REQ-19"], "invariants": ["save before close"]}]}
        for cap in (120, 200, 500, 1500, 6000):
            a, b = m.app_design_blocks(design, "REQ-19", cap)
            other, _ = m.app_design_blocks(design, "REQ-1", cap)
            self.assertEqual(a, other)
            self.assertLessEqual(len(a) + len(b), cap)
            for block in (a, b):
                if block:
                    json.loads(block.split("\n", 1)[1])
        self.assertIn("save before close", m.app_design_context(design, "REQ-19", 1500))

    def test_semantically_invalid_designs_are_rejected(self):
        for design in ({"routes": [{}]}, {"routes": []}, {"data_model": {"x": []}},
                       {"routes": [{"method": "FETCH", "path": "/x"}]},
                       {"routes": [{"method": ["GET"], "path": "/x"}]},
                       {"pages": [{"method": {}, "path": "/x"}]},
                       {"pages": [{"path": "/x"}, {"path": "/x"}]},
                       {"pages": [{"path": "/x", "requirements": "REQ-1"}]},
                       {"pages": [{"path": "/x"}], "contracts": [{"invariants": "text"}]}):
            self.assertIsNone(m.valid_app_design(design), design)
        self.assertIsNotNone(m.valid_app_design({"routes": [{"method": "PATCH", "path": "/api/x/:id"}]}))

    def test_capabilities_include_scenarios_but_not_explicit_exclusions(self):
        tree = {"scenarios": [{"steps": [{"content": "Preview Markdown and download a PDF"}]}]}
        self.assertIn("markdown", recommended_capabilities(tree))
        self.assertIn("documents", recommended_capabilities(tree))
        self.assertEqual(recommended_capabilities({"description":
            "No payment, carousel, rich-text editor or PDF export is needed."}), ["styling"])
        self.assertEqual(recommended_capabilities({"description": "无需支付或轮播，但需要日期选择"}),
                         ["styling", "calendar"])
        tree = {"children": [{"description": "Markdown comments"}, {"description": "Rich-text document editor"}]}
        self.assertIn("richtext", recommended_capabilities(tree))
        tree = {"description": "Markdown comments and a separate rich-text document editor"}
        self.assertIn("richtext", recommended_capabilities(tree))

    def test_identical_writes_including_charset_normalization_are_not_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {"frontend/src/index.html": "<html><head></head><body>Hello</body></html>",
                     "backend/server.js": "console.log('hello');\n"}
            self.assertEqual(set(write_files(root, files)), set(files))
            stamp = (root / "backend/server.js").stat().st_mtime_ns
            self.assertEqual(write_files(root, files), [])
            self.assertEqual((root / "backend/server.js").stat().st_mtime_ns, stamp)

    def test_grading_default_and_stress_override_are_distinct(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(m.Flow.final_workers(), 1)
            self.assertEqual(m.Flow.worker_parity_note(1), "")
            with patch.dict(os.environ, {"OCTOS_ARC_GRADER_WORKERS": "2"}):
                self.assertEqual(m.Flow.final_workers(), 2)
                with patch.dict(os.environ, {"OCTOS_ARC_FINAL_WORKERS": "4"}):
                    self.assertEqual(m.Flow.final_workers(), 4)
                    self.assertIn("expected grading concurrency is 2", m.Flow.worker_parity_note(4))


@unittest.skipUnless(shutil.which("node"), "Node required for real persistence tests")
class StoreMigrationTests(unittest.TestCase):
    def test_migrations_survive_restarts_preserve_edits_deletions_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_generic_template(root, m.BUNDLE_DIR, 3000, [])
            script = r"""
const assert = require('node:assert/strict');
const store = require('./backend/lib/store');
const {collection} = require('./backend/lib/collection');
const migrations = [{id: 'add-b', up(data) { data.items.push({id:'b', title:'B'}); }}];
const initial = [{id:'a',title:'Original'}];
let c = collection('records', {initial});
if (!store.read('records', null)) c.patch('a', {title:'Edited'});
c = collection('records', {initial, migrations});
assert.equal(c.get('a').title, 'Edited');
assert.equal(c.all().filter(x => x.id === 'b').length, 1);
c.remove('b');
assert.equal(collection('records', {initial, migrations}).get('b'), null);
const before = JSON.stringify(store.read('records'));
assert.throws(() => store.migrate('records', {}, [{id:'broken',up(data) { data.items=[]; throw Error('fail'); }}]));
assert.equal(JSON.stringify(store.read('records')), before);
assert.throws(() => store.migrate('records', {}, [{id:'async',async up(data) { data.items=[]; }}]));
assert.equal(JSON.stringify(store.read('records')), before);
assert.throws(() => store.migrate('records', {}, [migrations[0],migrations[0]]));
console.log(JSON.stringify(store.read('records')));
"""
            output = subprocess.check_output(["node", "-e", script], cwd=root, text=True)
            self.assertEqual(json.loads(output), {"items": [{"id": "a", "title": "Edited"}],
                                                 "__arcMigrations": ["add-b"]})
            # A new process must not rerun the migration, even after a deletion.
            output = subprocess.check_output(["node", "-e",
                "const c=require('./backend/lib/collection').collection('records',{migrations:["
                "{id:'add-b',up(d){d.items.push({id:'b'})}}]});console.log(JSON.stringify(c.all()));"],
                cwd=root, text=True)
            self.assertEqual(json.loads(output), [{"id": "a", "title": "Edited"}])


class SharedRepairTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
        f = self.flow
        f.tests_dir = root
        f.spec_map = {nid: [f"{nid}.spec.ts"] for nid in ("A", "B", "C")}
        f.whole_app_summary = RunSummary(passed=1, total=3, results=[
            TestOutcome(title=nid, file=f"{nid}.spec.ts", ok=nid == "C", status="failed", duration_ms=1,
                        message="ReferenceError: fetchRecord is not defined") for nid in ("A", "B", "C")])
        f.remaining = Mock(return_value=2000)
        f.wound_down = Mock(return_value=False)
        f.head = Mock(return_value="previous")
        f.app_source_digest = Mock(side_effect=["before", "after"] * 4)
        f.repair_requirements = Mock(return_value="requirements")
        f.suite_repair_turn = Mock()
        f.commit = Mock(return_value=True)
        f.whole_app_first_suite = Mock(return_value=set())
        f.restore_app = Mock()
        f.record_full_suite = Mock()

    def test_common_runtime_error_gets_one_repair_and_full_verification(self):
        f = self.flow
        self.assertEqual(f.whole_app_shared_repair([], {"A", "B"}), set())
        f.suite_repair_turn.assert_called_once()
        self.assertEqual(f.suite_repair_turn.call_args.args[1], ["A", "B"])
        f.whole_app_first_suite.assert_called_once()

    def test_timeouts_and_no_source_change_do_not_trigger_extra_suites(self):
        f = self.flow
        f.app_source_digest = Mock(return_value="unchanged")
        self.assertEqual(f.whole_app_shared_repair([], {"A", "B"}), {"A", "B"})
        f.whole_app_first_suite.assert_not_called()
        f.suite_repair_turn.reset_mock()
        for result in f.whole_app_summary.results:
            result.message = "Timeout 10000ms exceeded"
        f.whole_app_shared_repair([], {"A", "B"})
        f.suite_repair_turn.assert_not_called()

    def test_regression_or_unreliable_verdict_rolls_back(self):
        f = self.flow
        for result in (None, {"C"}):
            f.whole_app_first_suite.return_value = result
            self.assertEqual(f.whole_app_shared_repair([], {"A", "B"}), {"A", "B"})
        self.assertEqual(f.restore_app.call_count, 2)
        f.restore_app.assert_called_with("previous")

    def test_generation_retry_shares_original_deadline(self):
        f = self.flow
        f.codegen_turn = Mock(return_value=(False, "codegen reply contained no blocks"))
        with patch("main.time.monotonic", side_effect=[100, 395]):
            f.whole_app_generation_turn("prompt", 300, "test", spec_chars=0)
        f.codegen_turn.assert_called_once()  # Five seconds remain, not another 300.

    def test_startup_repair_reads_vite_relative_source(self):
        f = self.flow
        source = f.output_dir / "frontend/src/App.jsx"
        source.parent.mkdir(parents=True)
        source.write_text("export default function App(){ return <main/>; }\n")
        def repaired(*args, **kwargs):
            f.last_codegen_written = ["frontend/src/App.jsx"]
            return True, "repaired"
        f.whole_app_generation_turn = Mock(side_effect=repaired)
        self.assertTrue(f.whole_app_startup_repair("src/App.jsx:3: Cannot resolve import"))
        self.assertIn("--- frontend/src/App.jsx ---", f.whole_app_generation_turn.call_args.args[0])

    @unittest.skipUnless(shutil.which("git"), "Git required")
    def test_rollback_removes_newly_committed_app_files_only(self):
        f = self.flow
        root = f.output_dir
        def git(args, check=True):
            return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=check)
        git(["init"])
        git(["config", "user.email", "test@example.invalid"])
        git(["config", "user.name", "Test"])
        for part in ("frontend", "backend"):
            (root / part).mkdir()
            (root / part / "entry.js").write_text("original")
        git(["add", "."])
        git(["commit", "-m", "baseline"])
        baseline = git(["rev-parse", "HEAD"]).stdout.strip()
        (root / "backend/new.js").write_text("broken new module")
        (root / "backend/entry.js").write_text("regression")
        (root / "outside.txt").write_text("preserved")
        git(["add", "."])
        git(["commit", "-m", "repair"])
        f.runtime = SimpleNamespace(git=SimpleNamespace(run=git))
        m.Flow.restore_app(f, baseline)
        self.assertFalse((root / "backend/new.js").exists())
        self.assertEqual((root / "backend/entry.js").read_text(), "original")
        self.assertEqual((root / "outside.txt").read_text(), "preserved")


if __name__ == "__main__":
    unittest.main()
