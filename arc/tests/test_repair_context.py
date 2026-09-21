from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace

from acceptance import RunSummary, TestOutcome

from repair_context import balanced_failure_evidence, diagnosed_failure_evidence, failure_triage
import test_whole_app_v5 as whole_tests


class EvidenceTests(TestCase):
    def test_triage_keeps_missing_data_and_locator_hypotheses_distinct(self):
        text = "- Feature: A\ngetByRole('button', { name: 'Edit' })\n  Page at failure:\n- link \"Edit\"\n- Feature: B\nlocator.click timed out"
        result = diagnosed_failure_evidence(text, 6000)
        self.assertIn('UI/LOCATOR', result)
        self.assertIn('missing required data', result)
        self.assertIn('same test-helper line', result)
        self.assertIn('- link "Edit"', result)
        self.assertLessEqual(len(result), 6000)

    def test_triage_is_not_a_new_verdict_and_preserves_budget(self):
        self.assertEqual(failure_triage('Unknown failure'), '')
        self.assertIn('BUILD/LOAD', failure_triage('SyntaxError: invalid token'))
        self.assertIn('HTTP', failure_triage('HTTP 404'))
        for limit in (0, 1, 4, 20, 100, 1000):
            self.assertLessEqual(len(diagnosed_failure_evidence('TypeError: bad' * 1000, limit)), limit)

    def test_every_failure_precedes_large_dom(self):
        evidence = ''.join(f'- Feature: REQ-{i}\n  Location: test-{i}:12\n  Observation: failure-{i}\n'
                           '  Page at failure:\n' + 'DOM content\n' * 1000 +
                           f'  Browser diagnostics: network-{i}\n' for i in range(5))
        result = balanced_failure_evidence(evidence)
        self.assertLessEqual(len(result), 8000)
        for i in range(5):
            self.assertIn(f'failure-{i}', result)
            self.assertIn(f'network-{i}', result)
            self.assertLess(result.index(f'failure-{i}'), result.index('DOM content'))

    def test_small_and_unstructured_and_tiny_budgets(self):
        self.assertEqual(balanced_failure_evidence('short'), 'short')
        text = 'START' + 'x' * 10000 + 'END'
        self.assertTrue(balanced_failure_evidence(text, 500).endswith('END'))
        for limit in [0, 1, 50, 500]:
            self.assertLessEqual(len(balanced_failure_evidence(text, limit)), limit)

    def test_large_number_of_failures_still_has_all_headers(self):
        text = ''.join(f'- Feature: R{i:03}\n  Observation: ' + 'x' * 1000 + '\n' for i in range(125))
        result = balanced_failure_evidence(text)
        self.assertLessEqual(len(result), 8000)
        for i in range(125):
            self.assertIn(f'- Feature: R{i:03}', result)


class RepairFlowTests(TestCase):
    setUp = whole_tests.WholeAppTests.setUp

    def test_startup_repair_uses_codegen_floor_and_reserves_measurement(self):
        f = self.flow
        f.remaining.return_value = 240
        f.repair_minimum = Mock(return_value=60)
        f.final_measurement_reserve = Mock(return_value=120)
        f.turn = Mock(return_value=(True, 'fixed'))
        self.assertTrue(f.whole_app_startup_repair('Invalid module export: missing Root'))
        f.turn.assert_called_once()
        self.assertLessEqual(f.turn.call_args.args[1], 120)
        f.turn.reset_mock()
        f.remaining.return_value = 179
        self.assertFalse(f.whole_app_startup_repair('Invalid module export: missing Root'))
        f.turn.assert_not_called()

    def test_tool_prompt_uses_index_not_source_snapshot(self):
        f = self.flow
        (self.root / 'frontend').mkdir()
        (self.root / 'frontend/a.js').write_text('const sourceMarker = 123;')
        sources = f.sources_text()
        result = f.compact_tool_repair_prompt('RULE\n' + sources + '\nFAILURE', 'FAILURE')
        self.assertNotIn('sourceMarker', result)
        self.assertIn('frontend/a.js', result)
        self.assertIn('RULE', result)
        self.assertIn('FAILURE', result)

    def test_degenerate_suite_reply_skips_identical_protocol_retry(self):
        f = self.flow
        f.suite_repair_prompt = Mock(return_value='prompt')
        def generate(*args, **kwargs):
            f.last_codegen_degenerated = True
            f.last_codegen_written = []
            f.last_codegen_refused = set()
            return False, 'incomplete_blocks'
        f.codegen_turn = Mock(side_effect=generate)
        f.turn = Mock(return_value=(True, 'fixed'))
        f.suite_repair_turn('repair', ['A'], 'failed', 600, tool_prompt='tools')
        f.codegen_turn.assert_called_once()
        f.turn.assert_called_once()

    def test_two_clean_generation_replies_restore_cap(self):
        f = self.flow
        f.codegen_degenerated = True
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(f.generation_recovery_cap(), 16384)
        for i in range(2):
            f.text_turn = Mock(return_value=(True, f'<<<FILE frontend/a{i}.js>>>\nconst x = {i};\n<<<END FILE>>>'))
            ok, reason = f.codegen_turn('prompt', 30, 'A implement')
            self.assertTrue(ok, reason)
            self.assertFalse(f.last_codegen_degenerated)
            self.assertEqual(f.codegen_degenerated, i == 0)

    def test_local_wave_split_does_not_shrink_later_groups(self):
        f = self.flow
        f.codegen_implement_prompt = Mock(return_value='prompt')
        f.generation_output_budget = Mock(side_effect=[10000] + [999999] * 20)
        f.whole_app_generation_turn = Mock()
        def generated(*args, **kwargs):
            f.last_codegen_written = ['frontend/a.js']
            return True, 'ok'
        f.whole_app_generation_turn.side_effect = generated
        with patch.dict('os.environ', {'OCTOS_ARC_WHOLE_APP_WAVE_NODES': '3'}):
            self.assertTrue(f.whole_app_waves(self.tree, self.nodes))
        groups = [call.args[0]['description'] for call in f.codegen_implement_prompt.call_args_list]
        self.assertEqual(len(groups), 2)
        self.assertIn('B', groups[-1])
        self.assertIn('C', groups[-1])

    def test_rollback_noise_is_not_repair_progress(self):
        f = self.flow
        # Three passing features regress together; restoring unchanged source
        # then fluctuates from 3/4 to 4/4. That is not an applied improvement.
        (f.tests_dir / 'D.spec.ts').write_text('test D')
        f.spec_map['D'] = ['D.spec.ts']
        names = ['A', 'B', 'C', 'D']
        scores = iter([3, 0, 4, 4])
        def measure(*args, **kwargs):
            passed = next(scores)
            return RunSummary(passed=passed, total=4, results=[
                TestOutcome(title=n, ok=i < passed, status='passed' if i < passed else 'failed',
                            duration_ms=1, file=n + '.spec.ts', message='failed')
                for i, n in enumerate(names)])
        f.runner = SimpleNamespace(root=self.root, work_dir=self.root / 'prepared')
        f.run_specs = measure
        f.head = Mock(return_value='best')
        f.restore_app = Mock()
        f.record_tests = Mock()
        f.sources_text = Mock(return_value='')
        f.corrections_text = Mock(return_value='')
        f.suite_repair_turn = Mock(return_value=('codegen', ''))
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '1'}):
            f.final_acceptance()
        f.restore_app.assert_called_once_with('best')
        self.assertFalse(f.final_suite_progress)
