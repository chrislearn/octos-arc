"""Large new test unions must leave room to repair without weakening verdicts."""
import unittest
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from flow_policy import measurement_seconds
from measurement_timing import compose_window
from runtime_diagnostics import application_failures, diagnose
import test_two_run_repair_windows as repair_fixtures


class MeasurementForecast(unittest.TestCase):
    def setUp(self):
        fixture = repair_fixtures.MeasurementHistory(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow = fixture.flow

    def record(self, name, count, seconds, grader_like=False):
        f = self.flow
        (f.tests_dir / name).write_text('\n'.join(
            f"test('case {i}',()=>{{}});" for i in range(count)) + '\ntest.setTimeout(60_000);')
        summary = RunSummary(total=count, passed=0, results=[TestOutcome(
            f'case {i}', False, 'failed', 1000, file=name) for i in range(count)])
        f._run_specs = Mock(return_value=summary)
        with patch('main.time.monotonic', side_effect=[1000.0, 1000.0 + seconds]):
            self.assertIs(f.run_specs([name], grader_like=grader_like), summary)
        return summary

    def test_59_case_union_reuses_52_case_measurement_and_admits_repair(self):
        f = self.flow
        self.record('related.spec.ts', 52, 144, grader_like=True)
        self.record('target.spec.ts', 7, 105.755)
        before = list(f._acceptance_timings)
        reserved = f.node_measurement_reserve(['target.spec.ts'], ['related.spec.ts'])
        self.assertGreater(reserved, 300)  # Pays both target and regression.
        self.assertLess(reserved, 900)  # The captured node had 2645s left.
        self.assertGreater(2645 - reserved, 60)
        self.assertEqual(measurement_seconds(f.tests_dir, ['related.spec.ts', 'target.spec.ts']), 4308)
        self.assertEqual(f._acceptance_timings, before)  # Forecast is not a new measurement.
        forecast = [c.kwargs for c in f.metric.call_args_list if c.args[0] == 'measurement_forecast'][-1]
        self.assertEqual(forecast['measured_specs'], ['related.spec.ts'])
        self.assertEqual(forecast['estimated_specs'], ['target.spec.ts'])

    def test_shared_helper_edit_invalidates_exact_and_composed_samples(self):
        f = self.flow
        helper = f.tests_dir / 'helpers.ts'; helper.write_text('export const delay = 1;')
        self.record('A.spec.ts', 1, 20)
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 40)
        helper.write_text('export const delay = 60000;')
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 75)
        last = [c.kwargs for c in f.metric.call_args_list if c.args[0] == 'measurement_forecast'][-1]
        self.assertEqual(last['basis'], 'cold_start')

    def test_partial_measurements_never_train_even_when_fast(self):
        f = self.flow
        result = self.record('A.spec.ts', 1, 80)
        f._run_specs.return_value = RunSummary(total=1, passed=1, results=result.results,
                                             error='acceptance time budget exhausted', partial=True)
        with patch('main.time.monotonic', side_effect=[1000.0, 1001.0]):
            f.run_specs(['A.spec.ts'])
        self.assertEqual(len(f._acceptance_timings), 1)
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 115)

    def test_overlapping_subscopes_are_not_counted_twice(self):
        scopes = {name: name for name in ['A', 'B', 'C']}
        def row(names, seconds):
            return {'spec_scopes': {n: n for n in names}, 'timing_mode': {}, 'seconds': seconds}
        window, covered, missing = compose_window(scopes,
            [row(['A', 'B'], 80), row(['A'], 40), row(['B'], 60), row(['C'], 30)],
            {}, None, 10000, 1)
        self.assertEqual(window, 167.5)
        self.assertEqual(covered, ['A', 'B', 'C'])
        self.assertEqual(missing, [])

    def test_unsupported_injection_is_harness_evidence_and_never_an_app_exception(self):
        summary = RunSummary(total=1, results=[TestOutcome('rollback', False, 'failed', 10,
            file='A.spec.ts', message='HARNESS_UNSUPPORTED: no injected failure was observed')])
        self.assertEqual(diagnose(summary)[0]['owner'], 'harness')
        self.assertEqual(application_failures(summary), [])
        self.assertFalse(summary.all_passed)
