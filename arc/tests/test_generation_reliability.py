"""Provider interruption, output planning and domain-neutral query contracts."""
import argparse
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main as m
from acceptance import RunSummary, TestOutcome
from flow_policy import generation_tokens


class DeliveryCheckpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.tests_dir = self.root / 'specs'
        self.flow.tests_dir.mkdir()
        for name in ('A', 'B'):
            (self.flow.tests_dir / f'{name}.spec.ts').touch()
        self.flow.spec_map = {'A': ['A.spec.ts'], 'B': ['B.spec.ts']}
        self.flow.record_tests = Mock()
        self.git = Mock()
        self.git.run.return_value = SimpleNamespace(returncode=0, stdout='')
        self.flow.runtime = SimpleNamespace(git=self.git)
        self.flow.head = Mock(return_value='verified-sha')
        self.flow.commit = Mock(return_value=True)
        self.flow.restore_app = Mock()

    def summary(self, passed=1):
        return RunSummary(passed=passed, total=2, results=[
            TestOutcome(name, i < passed, 'passed' if i < passed else 'failed', 1,
                        file=f'{name}.spec.ts') for i, name in enumerate(('A', 'B'))])

    def test_restores_measured_tree_and_verdicts_without_model_calls(self):
        f = self.flow
        f.remember_delivery_checkpoint(self.summary(), {'B': []})
        f.test_verdict = {'A': False, 'B': True, 'unmeasured': True}
        f.turn = Mock(side_effect=AssertionError('must not call model'))
        self.assertTrue(f.recover_provider_stop(m.PermanentProviderError('insufficient_quota')))
        f.restore_app.assert_called_once_with('verified-sha')
        self.assertEqual(f.test_verdict, {'A': True, 'B': False})
        self.assertIn('preserve interrupted repair', f.commit.call_args_list[-2].args[0])
        f.turn.assert_not_called()

    def test_no_snapshot_or_zero_passes_is_not_a_recovered_delivery(self):
        self.assertFalse(self.flow.recover_provider_stop(RuntimeError('quota')))
        self.flow.remember_delivery_checkpoint(self.summary(0), {'A': [], 'B': []})
        self.assertFalse(self.flow.recover_provider_stop(RuntimeError('quota')))
        self.flow.restore_app.assert_not_called()

    def test_incomplete_or_errored_suite_cannot_replace_checkpoint(self):
        f = self.flow
        f.remember_delivery_checkpoint(self.summary(), {'B': []})
        saved = f.delivery_checkpoint
        for field, value in [('error', 'build failed'), ('killed', True),
                             ('load_errors', ['missing import']), ('total', 3)]:
            summary = self.summary(2)
            setattr(summary, field, value)
            f.remember_delivery_checkpoint(summary, {})
            self.assertIs(f.delivery_checkpoint, saved)
        summary = self.summary(2)
        summary.results[1].file = 'A.spec.ts'
        f.remember_delivery_checkpoint(summary, {})
        self.assertIs(f.delivery_checkpoint, saved)
        summary = self.summary(2)
        summary.results[1].status = 'interrupted'
        f.remember_delivery_checkpoint(summary, {})
        self.assertIs(f.delivery_checkpoint, saved)

    def test_dirty_snapshot_and_failed_preservation_do_not_trigger_destructive_restore(self):
        self.git.run.return_value.stdout = ' M frontend/src/App.jsx'
        self.flow.remember_delivery_checkpoint(self.summary(), {'B': []})
        self.assertIsNone(getattr(self.flow, 'delivery_checkpoint', None))
        self.git.run.return_value.stdout = ''
        self.flow.remember_delivery_checkpoint(self.summary(), {'B': []})
        self.git.run.return_value.stdout = '?? frontend/src/partial.jsx'
        self.assertFalse(self.flow.recover_provider_stop(RuntimeError('quota')))
        self.flow.restore_app.assert_not_called()

    def test_only_strictly_better_complete_measurement_replaces_checkpoint(self):
        f = self.flow
        f.remember_delivery_checkpoint(self.summary(), {'B': []})
        f.head.return_value = 'later'
        f.remember_delivery_checkpoint(self.summary(0), {'A': [], 'B': []})
        f.remember_delivery_checkpoint(self.summary(), {'B': []})
        self.assertEqual(f.delivery_checkpoint['sha'], 'verified-sha')
        f.remember_delivery_checkpoint(self.summary(2), {})
        self.assertEqual(f.delivery_checkpoint['sha'], 'later')

    def test_real_git_preserves_partial_edits_and_removes_new_files_on_restore(self):
        def git(args, check=True):
            return subprocess.run(['git', *args], cwd=self.root, check=check,
                                  capture_output=True, text=True)
        git(['init', '-q'])
        git(['config', 'user.email', 'test@example.invalid'])
        git(['config', 'user.name', 'Test'])
        for part in ('frontend', 'backend'):
            (self.root / part).mkdir()
            (self.root / part / 'source.js').write_text('// verified')
        def commit(message):
            git(['add', '.'])
            return git(['commit', '-qm', message], check=False).returncode == 0
        f = self.flow
        f.runtime = SimpleNamespace(git=SimpleNamespace(run=git))
        f.commit = commit
        f.head = lambda: git(['rev-parse', 'HEAD']).stdout.strip()
        f.restore_app = lambda sha: m.Flow.restore_app(f, sha)
        f.remember_delivery_checkpoint(self.summary(), {'B': []})
        (self.root / 'frontend/source.js').write_text('// interrupted')
        (self.root / 'frontend/partial.jsx').write_text('// new partial module')
        self.assertTrue(f.recover_provider_stop(RuntimeError('quota')))
        self.assertEqual((self.root / 'frontend/source.js').read_text(), '// verified')
        self.assertFalse((self.root / 'frontend/partial.jsx').exists())
        self.assertEqual(git(['show', 'HEAD~1:frontend/partial.jsx']).stdout, '// new partial module')


class GenerationBudgetTests(unittest.TestCase):
    def test_routed_model_output_limit_is_respected(self):
        flow = object.__new__(m.Flow)
        flow.llm_proxy = SimpleNamespace(routes=[
            {'phases': ['design'], 'parameters': {'max_tokens': 500}},
            {'phases': ['implement'], 'parameters': {'max_completion_tokens': 8192}}])
        with patch.dict('os.environ', {'OCTOS_ARC_MAX_TOKENS': '32768',
                                      'OCTOS_ARC_CODEGEN_OUTPUT_TOKENS': '12000'}):
            self.assertEqual(flow.generation_output_budget(), 8192)

    def test_more_features_and_longer_specs_cost_more_estimated_output(self):
        nodes = [{'description': 'feature'}] * 3
        self.assertLess(generation_tokens(nodes, 100), generation_tokens(nodes * 2, 100))
        self.assertLess(generation_tokens(nodes, 100), generation_tokens(nodes, 20000))

    def test_large_output_is_split_before_first_provider_request(self):
        from test_whole_app_v5 import WholeAppTests
        case = WholeAppTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        f = case.flow
        nodes = [{'id': str(i), 'description': 'feature'} for i in range(12)]
        f.spec_map = {node['id']: [node['id'] + '.spec.ts'] for node in nodes}
        f.batch_spec_bodies = lambda ids: 'spec'
        groups = []
        def prompt(node, spec):
            groups.append(node['description'])
            return 'prompt'
        f.codegen_implement_prompt = prompt
        def generate(*args, **kwargs):
            f.last_codegen_written = ['frontend/src/App.jsx']
            return True, 'files'
        f.codegen_turn = Mock(side_effect=generate)
        with patch.dict('os.environ', {'OCTOS_ARC_MAX_TOKENS': '32768',
                                      'OCTOS_ARC_CODEGEN_OUTPUT_TOKENS': '19660',
                                      'OCTOS_ARC_WHOLE_APP_WAVE_NODES': '6'}):
            self.assertTrue(f.whole_app_codegen({'id': 'ROOT', 'children': nodes}, nodes))
        self.assertEqual(f.codegen_turn.call_count, 4)  # 3+3+3+3, no wasted 12/6 request
        self.assertEqual(f.whole_app_generated_ids, {str(i) for i in range(12)})

    def test_bad_design_gets_one_schema_retry_and_never_an_unbounded_loop(self):
        from test_app_design import AppDesignTurnTests, DESIGN, TREE
        with tempfile.TemporaryDirectory() as folder:
            flow, nodes = AppDesignTurnTests()._flow(folder, 'unused')
            flow.text_turn = Mock(side_effect=[(True, 'not JSON'), (True, json.dumps(DESIGN))])
            self.assertEqual(flow.app_design(TREE, nodes), DESIGN)
            self.assertEqual(flow.text_turn.call_count, 2)
            self.assertLessEqual(flow.text_turn.call_args.args[1], 120)

    def test_design_timeout_does_not_buy_another_turn(self):
        from test_app_design import AppDesignTurnTests, TREE
        with tempfile.TemporaryDirectory() as folder:
            flow, nodes = AppDesignTurnTests()._flow(folder, 'unused')
            flow.text_turn = Mock(return_value=(False, 'timeout'))
            self.assertIsNone(flow.app_design(TREE, nodes))
            flow.text_turn.assert_called_once()


@unittest.skipUnless(shutil.which('node'), 'Node required')
class QueryContractTests(unittest.TestCase):
    def test_absent_false_and_combined_flags_never_reset_visibility(self):
        script = r'''
const assert = require('node:assert/strict');
const {optionalBoolean, matchesFlags} = require(process.argv[1]);
assert.equal(optionalBoolean(undefined), undefined);
assert.equal(optionalBoolean('false'), false);
assert.throws(() => optionalBoolean(['true']), error => error.status === 400);
assert.throws(() => optionalBoolean(''), error => error.status === 400);
const records = [
  {id: 1, disabled: true, starred: false},
  {id: 2, disabled: false, starred: true},
  {id: 3, disabled: false, starred: false},
];
for (const disabled of [undefined, true, false]) {
  for (const starred of [undefined, true, false]) {
    const actual = records.filter(r => matchesFlags(r, {disabled, starred}));
    const expected = records.filter(r => (disabled === undefined || r.disabled === disabled)
                                     && (starred === undefined || r.starred === starred));
    assert.deepEqual(actual, expected);
  }
}
assert.deepEqual(records.filter(r => matchesFlags(r, {disabled:true})).map(r => r.id), [1]);
assert.equal(matchesFlags({}, {disabled:false}), false);
assert.throws(() => matchesFlags({}, {disabled:'false'}), TypeError);
records[0].disabled = false;
assert.equal(records.filter(r => matchesFlags(r, {disabled:false})).length, 3);
'''
        result = subprocess.run(['node', '-e', script, str(m.BUNDLE_DIR / 'blueprints/query.js')],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
