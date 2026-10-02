"""Cross-round review: diagnostics must not widen or break acceptance."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from repair_control import seconds_available
import test_two_run_repair_windows as windows
import test_joint_regression_repair as joint


class TimingCompatibility(unittest.TestCase):
    def setUp(self):
        fixture = windows.MeasurementHistory(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow, self.root = fixture.flow, fixture.root
        self.flow._run_specs = Mock(return_value=fixture.measured(True))

    def test_changed_runner_timeout_cannot_reuse_a_short_measurement(self):
        f = self.flow
        with patch('main.time.monotonic', side_effect=[1000.0, 1020.0]):
            f.run_specs(['A.spec.ts'])
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 40)
        f.runner.timeout_ms = 90000
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 75)

    def test_custom_runner_measurement_cannot_shrink_default_runner_window(self):
        f = self.flow
        custom = SimpleNamespace(timeout_ms=1000, workers=1)
        with patch('main.time.monotonic', side_effect=[1000.0, 1001.0]):
            f.run_specs(['A.spec.ts'], runner=custom)
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 75)

    def test_isolation_change_invalidates_multi_file_measurement(self):
        f = self.flow
        f.derived_as_specs = True
        f.derived_case_selection = Mock(return_value=(2, {}))
        (f.tests_dir / 'B.spec.ts').write_text("test('two',()=>{}); test.setTimeout(60_000);")
        f._run_specs.return_value = RunSummary(total=2, passed=2, results=[TestOutcome(
            title, True, 'passed', 1000, file=name) for title, name in
            [('one', 'A.spec.ts'), ('two', 'B.spec.ts')]])
        with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_ISOLATE': '1'}):
            with patch('main.time.monotonic', side_effect=[1000.0, 1020.0]):
                f.run_specs(['A.spec.ts', 'B.spec.ts'])
            self.assertEqual(f.node_measurement_window(['A.spec.ts', 'B.spec.ts']), 40)
        with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_ISOLATE': '0'}):
            self.assertEqual(f.node_measurement_window(['A.spec.ts', 'B.spec.ts']), 90)

    def test_selection_read_failure_does_not_override_the_actual_verdict(self):
        f = self.flow
        f.derived_as_specs = True
        f.derived_case_selection = Mock(side_effect=OSError('review metadata unavailable'))
        expected = f._run_specs.return_value
        self.assertIs(f.run_specs(['A.spec.ts']), expected)
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 75)
        self.assertFalse(getattr(f, '_acceptance_timings', []))

    def test_missing_derived_test_directory_keeps_origin_error(self):
        f = self.flow
        del f._run_specs  # Exercise real authority checks, before any browser/build.
        f.derived_as_specs = True
        f.tests_dir = None
        f.derived_tests_dir = self.root / 'generated'
        result = f.run_specs(['A.spec.ts'])
        self.assertEqual(result.error, 'generated suite origin mismatch')


class FrozenResumeDeadline(unittest.TestCase):
    def setUp(self):
        fixture = joint.JointRepairTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow = f = fixture.flow
        self.passed = fixture.target
        self.now = [1000.0]
        for attr in ('monotonic', 'time'):
            clock = patch('main.time.' + attr, side_effect=lambda: self.now[0])
            clock.start(); self.addCleanup(clock.stop)
        f._frozen_setup_dependencies = {'rename': {'csv'}}
        f._pending_frozen_acceptance = {'rename'}
        f.implementation_evidence = {'csv': {'status': 'implemented_unverified'}}
        f.remaining = Mock(return_value=600)
        f.final_phase_reserve = Mock(return_value=150)
        f.node_timeout = 120
        f.min_repair_seconds = 60
        f._node_deadline = None

    def test_real_resumed_acceptance_has_hard_node_deadline(self):
        f = self.flow
        def run(*args, **kwargs):
            self.assertEqual(seconds_available(f), 120)
            self.now[0] += 119
            return self.passed
        f.run_specs = Mock(side_effect=run)
        f.resume_frozen_acceptance([{'id': 'rename'}])
        self.assertIs(f.test_verdict['rename'], True)
        self.assertEqual(f._pending_frozen_acceptance, set())
        self.assertIsNone(f._node_deadline)

    def test_final_reserve_stops_resumption_without_dropping_pending_leaf(self):
        f = self.flow
        f.remaining.return_value = 200
        f.run_specs = Mock(return_value=self.passed)
        f.resume_frozen_acceptance([{'id': 'rename'}])
        f.run_specs.assert_not_called()
        self.assertEqual(f._pending_frozen_acceptance, {'rename'})

    def test_exception_restores_outer_deadline(self):
        f = self.flow
        f._node_deadline = 1250
        def fail(*args, **kwargs):
            self.assertEqual(f._node_deadline, 1120)
            raise RuntimeError('cancelled')
        f.run_specs = Mock(side_effect=fail)
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            f.resume_frozen_acceptance([{'id': 'rename'}])
        self.assertEqual(f._node_deadline, 1250)


if __name__ == '__main__':
    unittest.main()
