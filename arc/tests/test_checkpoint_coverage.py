"""Generic checkpoint coverage, bounded repairs and diagnostic evidence."""
import unittest
from unittest.mock import Mock, patch
from acceptance import RunSummary, TestOutcome, startup_error_digest
from generation_checks import contract_warnings
import test_main_helpers as helpers


def observed(specs, failing=()):
    rows = [TestOutcome(s, s not in failing, 'failed' if s in failing else 'passed', 1,
                        file=s, message='missing control' if s in failing else '') for s in specs]
    return RunSummary(passed=sum(r.ok for r in rows), total=len(rows), results=rows)


class CoverageTests(unittest.TestCase):
    def flow(self):
        f = helpers.CheckpointRepairTests()._flow([])
        f.metric = Mock()
        f.remember_delivery_checkpoint = Mock()
        f.head = Mock(return_value='snapshot')
        return f

    def test_failed_backlog_is_revisited_and_planned_features_are_excluded(self):
        f = self.flow()
        f.test_verdict['REQ-2'] = False
        f.spec_map['REQ-3'] = ['REQ-3.spec.ts']
        f.run_specs = Mock(side_effect=lambda specs, **kw: observed(specs))
        with patch.dict('os.environ', {'OCTOS_ARC_REGRESSION_CHECKPOINT': '2'}):
            f.regression_checkpoint(2, 8)
        self.assertEqual(f.run_specs.call_args.args[0], ['REQ-1.spec.ts', 'REQ-2.spec.ts'])
        self.assertTrue(f.test_verdict['REQ-2'])
        self.assertNotIn('REQ-3', f.test_verdict)
        f.metric.assert_any_call('checkpoint_coverage', checkpoint=2, checked_specs=2,
                                total_specs=3, unobserved_specs=1,
                                backlog_selected=['REQ-2'], backlog_remaining=0)

    def test_incomplete_checkpoint_does_not_certify_or_repair(self):
        f = self.flow()
        f.run_specs = Mock(return_value=observed(['REQ-1.spec.ts']))
        f.repair_regressions = Mock()
        with patch.dict('os.environ', {'OCTOS_ARC_REGRESSION_CHECKPOINT': '2'}):
            f.regression_checkpoint(2, 8)
        f.repair_regressions.assert_not_called()
        f.remember_delivery_checkpoint.assert_not_called()

    def test_broad_repairs_rotate_focus_but_verify_whole_checkpoint(self):
        f = self.flow()
        ids = [f'R{i}' for i in range(6)]
        verified = {n: [n + '.spec.ts'] for n in ids}
        f.spec_map = verified
        specs = [n + '.spec.ts' for n in ids]
        summary = observed(specs, specs)
        grouped = {n: [row] for n, row in zip(ids, summary.results)}
        f.suite_repair_turn = Mock()
        f.last_repair_changed = True
        f.run_specs = Mock(return_value=summary)
        with patch.dict('os.environ', {'OCTOS_ARC_CHECKPOINT_REPAIR_NODES': '3'}):
            f.repair_regressions(8, specs, verified, set(), summary, grouped, 1)
        self.assertEqual([c.args[1] for c in f.suite_repair_turn.call_args_list], [ids[:3], ids[3:]])
        self.assertTrue(all(c.args[0] == specs for c in f.run_specs.call_args_list))

    def test_compiler_location_survives_long_build_prefix(self):
        error = 'npm building...\n' * 100 + 'src/pages/Page.jsx:42:8: ERROR: Unexpected token\ncode excerpt'
        digest = startup_error_digest(error, 300)
        self.assertIn('Page.jsx:42:8', digest)
        self.assertIn('Unexpected token', digest)

    def test_cross_file_hints_do_not_reject_valid_router_chains(self):
        sources = {'backend/routes/a.js': "app.get('/item', handler);",
                   'backend/routes/b.js': "app.get('/item', middleware);",
                   'frontend/pages/Page.jsx': "import './page.css';",
                   'frontend/components/page.css': 'body {}'}
        hints = contract_warnings(sources, sources)
        self.assertTrue(any('IMPORT_PATH' in w and 'frontend/pages/page.css' in w for w in hints))
        self.assertTrue(any('ROUTE_OWNER' in w and 'middleware chains are valid' in w for w in hints))
        sources['frontend/pages/page.css'] = 'body {}'
        self.assertFalse(any('IMPORT_PATH' in w for w in contract_warnings(sources, sources)))

    def test_initial_implementation_changes_trigger_affected_regression(self):
        import test_resumable_recovery as fixtures
        from types import SimpleNamespace
        import time
        fixtures.RecoveryControlTests.setUp(self)
        f = self.flow
        f.mark = Mock()
        f.codegen_mode = Mock(return_value=False)
        f.repair_source_index = Mock(return_value=SimpleNamespace(versions={'frontend/shared.js': 'new'}))
        f.affected_regression_specs = Mock(return_value=['B.spec.ts'])
        f.test_verdict = {'B': True}
        f.run_specs = Mock(side_effect=[observed(['A.spec.ts']), observed(['B.spec.ts'], ['B.spec.ts'])])
        verdict = f.acceptance_loop('A', ['A.spec.ts'], time.time() + 300,
                                    source_versions={'frontend/shared.js': 'old'})
        self.assertFalse(verdict)
        self.assertFalse(f.test_verdict['B'])
        self.assertEqual(f.run_specs.call_count, 2)
        f.affected_regression_specs.assert_called_once_with({'frontend/shared.js'}, ['A.spec.ts'])

    def test_failed_new_feature_still_checks_previously_passing_behavior(self):
        import test_resumable_recovery as fixtures
        from types import SimpleNamespace
        import time
        fixtures.RecoveryControlTests.setUp(self)
        f = self.flow
        f.repair_rounds = 0
        f.mark = Mock()
        f.codegen_mode = Mock(return_value=False)
        f.repair_source_index = Mock(return_value=SimpleNamespace(versions={'frontend/shared.js': 'new'}))
        f.affected_regression_specs = Mock(return_value=['B.spec.ts'])
        f.spec_map = {'A': ['A.spec.ts'], 'B': ['B.spec.ts']}
        f.test_verdict = {'B': True}
        f.run_specs = Mock(side_effect=[observed(['A.spec.ts'], ['A.spec.ts']),
                                        observed(['B.spec.ts'], ['B.spec.ts'])])
        self.assertFalse(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 300,
                                           source_versions={'frontend/shared.js': 'old'}))
        self.assertFalse(f.test_verdict['B'])
        self.assertEqual(f.run_specs.call_count, 2)
        self.assertTrue(any('Previously passing behavior regressed' in note or
                            'Related regression checks' in note for note in f.pending_corrections))

    def test_failed_shared_edit_bounds_immediate_regression_probe(self):
        import test_resumable_recovery as fixtures
        from types import SimpleNamespace
        import time
        fixtures.RecoveryControlTests.setUp(self)
        f = self.flow
        f.repair_rounds = 0
        f.codegen_mode = Mock(return_value=False)
        f.repair_source_index = Mock(return_value=SimpleNamespace(versions={'frontend/App.jsx': 'new'}))
        prior = [f'B{i}.spec.ts' for i in range(12)]
        f.affected_regression_specs = Mock(return_value=prior + ['A.spec.ts'])
        f.spec_map = {'A': ['A.spec.ts'], **{f'B{i}': [spec] for i, spec in enumerate(prior)}}
        f.test_verdict = {f'B{i}': True for i in range(12)}
        f.run_specs = Mock(side_effect=lambda specs, **kw: observed(specs, ['A.spec.ts']))
        self.assertFalse(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 300,
                                           source_versions={'frontend/App.jsx': 'old'}))
        self.assertEqual(len(f.run_specs.call_args_list[1].args[0]), 8)
        self.assertNotIn('A.spec.ts', f.run_specs.call_args_list[1].args[0])

    def test_backlog_does_not_grow_the_permanent_regression_set(self):
        f = self.flow()
        for i in range(3, 8):
            f.spec_map[f'REQ-{i}'] = [f'REQ-{i}.spec.ts']
            f.test_verdict[f'REQ-{i}'] = False
        f.run_specs = Mock(side_effect=lambda specs, **kw: observed(specs, [s for s in specs if s not in {'REQ-1.spec.ts', 'REQ-2.spec.ts'}]))
        with patch.dict('os.environ', {'OCTOS_ARC_CHECKPOINT_BACKLOG': '2',
                                      'OCTOS_ARC_CHECKPOINT_REPAIRS': '0'}):
            f.regression_checkpoint(4, 20)
            f.regression_checkpoint(8, 20)
        calls = [set(c.args[0]) for c in f.run_specs.call_args_list]
        self.assertEqual([len(s) for s in calls], [4, 4])
        self.assertNotEqual(calls[0], calls[1])
        self.assertFalse(f.checkpoint_regressions)

    def test_source_fingerprint_tracks_code_but_not_local_configuration(self):
        import tempfile
        from pathlib import Path
        from generation_checks import adapter_fingerprint
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'main.py').write_text('print(1)')
            first = adapter_fingerprint(root)
            (root / '.env').write_text('SECRET=not-source')
            self.assertEqual(first, adapter_fingerprint(root))
            (root / 'main.py').write_text('print(2)')
            self.assertNotEqual(first['sha256'], adapter_fingerprint(root)['sha256'])

    def test_connection_refusal_does_not_claim_route_handler_exception(self):
        import http.client
        from acceptance import robustness_probe
        connection = Mock()
        connection.request.side_effect = ConnectionRefusedError()
        process = Mock()
        process.poll.return_value = None
        with patch.object(http.client, 'HTTPConnection', return_value=connection), patch('acceptance.time.sleep'):
            error = robustness_probe(12345, process)
        self.assertIn('listener readiness', error)
        self.assertIn('12345', error)
        self.assertNotIn('return 404', error)

    def test_incomplete_post_repair_report_cannot_trigger_score_rollback(self):
        f = self.flow()
        f.spec_map = {n: [n + '.spec.ts'] for n in ('A', 'B', 'C')}
        f.test_verdict = dict.fromkeys(f.spec_map, True)
        specs = [p for paths in f.spec_map.values() for p in paths]
        f.healthy_checkpoint = {'sha': 'healthy', 'summary': RunSummary(passed=20, total=20),
                                'verified': f.spec_map}
        f.restore_app = Mock()
        f.suite_repair_turn = Mock()
        f.last_repair_changed = True
        f.run_specs = Mock(side_effect=[observed(specs, specs), observed(['A.spec.ts'])])
        with patch.dict('os.environ', {'OCTOS_ARC_REGRESSION_CHECKPOINT': '2'}):
            f.regression_checkpoint(2, 8)
        f.restore_app.assert_not_called()
        f.remember_delivery_checkpoint.assert_not_called()
        self.assertEqual(f.test_verdict, dict.fromkeys(f.spec_map))
