import time
from unittest import TestCase
from unittest.mock import Mock

from acceptance import RunSummary
import main as m
import test_whole_app_v5 as whole_tests


class UnknownVerdictTests(TestCase):
    setUp = whole_tests.WholeAppTests.setUp

    def test_build_error_is_unknown_and_never_triggers_full_rewrite(self):
        f = self.flow
        f.repair_rounds = 1
        f.head = lambda: 'before'
        f.snapshot_sources = Mock()
        f.record_tests = Mock()
        f.metric = Mock()
        f.repair_minimum = lambda: 0
        f.sources_text = lambda: ''
        f.repair_requirements = lambda *args: ''
        f.repair_test_location = lambda *args: ''
        repair_prompts = []
        def repair(node_id, failures, timeout, label, build_prompt):
            repair_prompts.append(build_prompt())
            return True
        f.node_repair_turn = Mock(side_effect=repair)
        f.run_specs = Mock(side_effect=[RunSummary(error='backend: data is not iterable'),
                                       RunSummary(passed=1, total=1)])
        rebuild = Mock(return_value='rewrite entire app')
        self.assertTrue(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000, rebuild))
        self.assertEqual(f._unresolved_startup_error, '')
        rebuild.assert_not_called()
        f.node_repair_turn.assert_called_once()
        self.assertIn('No functional acceptance verdict', repair_prompts[0])
        self.assertIn('data is not iterable', repair_prompts[0])
        f.record_tests.assert_called_once()
        first = f.metric.call_args_list[0].kwargs
        self.assertEqual(first['verdict'], 'unknown')
        self.assertEqual(first['total'], 0)  # never invent one failed test per spec
        self.assertEqual(first['error'], 'backend: data is not iterable')

    def test_load_errors_cannot_turn_partial_passes_into_acceptance(self):
        f = self.flow
        f.repair_rounds = 0
        f.head = lambda: 'before'
        f.record_tests = Mock()
        f.run_specs = Mock(return_value=RunSummary(passed=1, total=1, load_errors=['other spec failed to load']))
        self.assertIsNone(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000))
        self.assertEqual(f._unresolved_startup_error, 'other spec failed to load')
        f.record_tests.assert_not_called()
        f.commit.assert_not_called()

    def test_migration_shape_is_explicit_in_design_and_codegen_contracts(self):
        for prompt in (m.APP_DESIGN_PROMPT.format(outline='Generic records'), m.GENERIC_TEMPLATE_NOTE):
            self.assertIn('record array is data.items', prompt)
            self.assertIn('NOT data itself', prompt)
            self.assertIn('return undefined', prompt)
