"""Authoritative pipeline regression tests; no model or product self-tests."""
import argparse
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from acceptance import AcceptanceRunner, RunSummary, TestOutcome
from layered_tests import (ApplicationSnapshot, GateBlocked, LayeredState, LayeredTests,
                           compile_basic, compile_entry_contract, dependency_files, digest, helper_excerpt, publish_initial)
from main import Flow
from obligation_planning import prepare_obligations
from scenario_review import compact_source_references
from scenario_tests import HELPERS, suite_fixtures


def measurement(rows, ok=True):
    results = [TestOutcome(row['title'], ok, 'passed' if ok else 'failed', 1,
                           file=Path(row['file']).name, spec_path=row['file'],
                           spec_line=row.get('line'), message='' if ok else 'wrong business outcome') for row in rows]
    return RunSummary(total=len(results), passed=sum(r.ok for r in results), results=results)


class DiscoveryRunner:
    def discover_cases(self, paths):
        rows = []
        for rel in paths:
            source = (self.tests_dir / rel).read_text()
            rows += [{'file': rel, 'title': m[1], 'line': None}
                     for m in re.finditer(r"test\('([^']+)'", source)]
        return rows, ''


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'app'
        self.root.mkdir()
        self.req = Path(self.tmp.name) / 'task'
        self.req.mkdir()
        self.nodes = [{'id': f'REQ-{i}', 'type': 'ATOMIC',
                       'description': f'The home page has a button named “Open {i}”.',
                       'scenarios': [], 'dependencies': []} for i in (1, 2)]
        self.tree = {'id': 'ROOT', 'description': 'Records remain visible.', 'children': self.nodes}
        self.flow = Flow(argparse.Namespace(web_port=3000), self.root, self.req)
        self.flow.requirement_tree = self.tree
        self.flow.derived_as_specs = True
        self.flow.tests_dir = self.flow.derived_tests_dir = self.root / 'derived-tests'
        self.flow.tests_dir.mkdir()
        self.flow.basic_tests_dir = self.root / '.arc/basic-tests'
        self.flow.basic_tests_dir.mkdir(parents=True)
        (self.flow.basic_tests_dir / 'helpers.ts').write_bytes(HELPERS.read_bytes())
        self.flow.runner = DiscoveryRunner()
        self.flow.runner.tests_dir = self.flow.tests_dir
        for name, value in {'remaining': 10000, 'time_up': False, 'wound_down': False,
                            'final_measurement_reserve': 30, 'codegen_mode': False,
                            'node_start_budget_available': True, 'admit_node': True,
                            'derived_review_needed': False}.items():
            setattr(self.flow, name, Mock(return_value=value))
        self.flow.metric = Mock()
        self.flow.commit = Mock()
        self.flow.start_background_specs = Mock()
        self.flow.poll_background_specs = Mock()
        self.flow.repair_requirements = Mock(return_value='Authoritative original requirements')
        self.flow.text_turn = Mock(return_value=(True, '{"decision":"KEEP","reason":"preserve the healthy version"}'))
        self.flow.sources_text = Mock(return_value='Application source')
        self.flow.driver = None
        self.flow.repair_rounds = 0
        self.flow.node_timeout = 60
        self.flow.test_verdict = {}
        self.layer = LayeredTests(self.flow, self.nodes)
        self.flow.layered = self.layer
        self.layer.static_check = Mock(return_value='')
        self.flow.run_specs = Mock(side_effect=self.run_specs)
        (self.root / 'backend').mkdir()
        (self.root / 'backend/app.js').write_text('good application')
        (self.root / 'package.json').write_text('{"working":true}')

    def run_specs(self, specs, **kwargs):
        if getattr(self.flow, '_layered_execution_level', None) == 'basic':
            rows = [case for node in self.layer.state.data['nodes'].values()
                    for case in node.get('cases', []) if case['file'] in specs]
        else:
            rows = [row for row in self.layer.state.data['cases'].values() if row['file'] in specs
                    and (self.layer.active_case_ids is None or row['id'] in self.layer.active_case_ids)
                    and self.layer.state.data['stops'].get(row['id'], {}).get('state') != 'disputed']
        return measurement(rows)

    def candidate(self, node):
        key = node['id']
        source, error = compile_basic(node, suite_fixtures(self.nodes), '')
        self.assertFalse(error)
        rel = key + '.spec.ts'
        (self.flow.basic_tests_dir / rel).write_text(source)
        candidate = dict(node_id=key, file=rel, source=source, sources={key: node['description']},
                         fixtures='fixture', helper=HELPERS.read_text(), helper_hash=digest(HELPERS.read_bytes()),
                         input_hash=digest(source))
        self.layer.basic_candidates[key] = candidate
        decision = dict(status='approved_basic', requirement_quote=node['description'],
                        test_quote=f"await h.expectRole(page, 'button', 'Open {key[-1]}');", reason='Exact entry contract')
        return dict(node_id=key, status='approved_basic', input_hash=candidate['input_hash'], decision=decision)

    def freeze(self, complete=False):
        for node in self.nodes:
            self.layer.install_basic(self.candidate(node))
            self.assertEqual(self.layer.state.data['nodes'][node['id']]['basic'], 'frozen')
            if complete:
                self.layer.state.data['nodes'][node['id']].update(code_done=True, basic='passed')
        self.layer.state.data['phase'] = 'business' if complete else 'code'
        self.layer.safe = ApplicationSnapshot(self.flow)
        self.layer.state.save()

    def business_case(self, title='business result', scenario='S1', branch='success'):
        rel = 'REQ-1.spec.ts'
        (self.flow.tests_dir / rel).write_text("import { test } from '@playwright/test';\n" + f"test('{title}', async () => {{}});\n")
        key = self.layer.state.identity('REQ-1', scenario)
        row = dict(id=key, node_id='REQ-1', title=title, scenario=scenario, file=rel, line=None, status='pending',
                   dependencies={name: digest(raw) for name, raw in dependency_files(self.flow.tests_dir, rel).items()})
        self.layer.state.data['cases'][key] = row
        return key, row

    def test_approval_cannot_freeze_a_changed_candidate_or_helper(self):
        for file in ('REQ-1.spec.ts', 'helpers.ts'):
            with self.subTest(file=file):
                reply = self.candidate(self.nodes[0])
                (self.flow.basic_tests_dir / file).write_text('changed after independent review')
                self.layer.install_basic(reply)
                self.assertEqual(self.layer.state.data['nodes']['REQ-1']['basic'], 'blocked')
                (self.flow.basic_tests_dir / 'helpers.ts').write_bytes(HELPERS.read_bytes())

    def test_review_rejects_missing_exact_assertion_without_application_evidence(self):
        self.candidate(self.nodes[0])
        self.flow.text_turn = Mock(return_value=(True, json.dumps(dict(status='approved_basic',
            requirement_quote=self.nodes[0]['description'], test_quote='invented assertion', reason='Fine'))))
        result = self.layer.review_basic('REQ-1')
        self.assertEqual(result['status'], 'rejected')
        self.assertNotIn('good application', self.flow.text_turn.call_args.args[0])

    def test_basic_gate_prevents_the_next_node_when_review_is_rejected(self):
        self.candidate(self.nodes[0])
        self.layer.state.data['nodes']['REQ-1'].update(basic='rejected', reason='unproved setup')
        self.flow.node_cycle = Mock()
        with self.assertRaises(GateBlocked):
            self.layer.implement(self.tree, self.nodes, set())
        self.assertEqual(self.flow.node_cycle.call_count, 1)
        self.assertEqual(self.flow.node_cycle.call_args.args[0]['id'], 'REQ-1')
        self.flow.run_specs.assert_not_called()

    def test_current_pass_cannot_hide_a_prior_basic_regression(self):
        self.freeze()
        self.layer.gate('REQ-1')
        def regress(specs, **kwargs):
            rows = [case for row in self.layer.state.data['nodes'].values()
                    for case in row['cases'] if case['file'] in specs]
            report = measurement(rows)
            if json.loads((self.root / 'package.json').read_text())['working'] is False:
                report.results[0].ok = False
                report.results[0].status = 'failed'
                report.passed -= 1
            return report
        self.flow.run_specs.side_effect = regress
        (self.root / 'package.json').write_text('{"working":false}')
        with self.assertRaises(GateBlocked):
            self.layer.gate('REQ-2')
        self.assertFalse(self.layer.state.data['nodes']['REQ-2']['code_done'])
        self.assertEqual(json.loads((self.root / 'package.json').read_text()), {'working': True})
        self.assertEqual(self.flow.run_specs.call_args_list[-2].args[0], ['REQ-1.spec.ts', 'REQ-2.spec.ts'])
        self.assertEqual(self.flow.run_specs.call_args.args[0], ['REQ-1.spec.ts'])  # restore was remeasured

    def test_rejected_basic_publication_restores_and_remeasures_the_prior_safe_application(self):
        self.freeze()
        self.layer.gate('REQ-1')
        (self.root / 'package.json').write_text('unusable candidate configuration')
        self.layer.state.data['nodes']['REQ-2'].update(basic='rejected', reason='unproven entry fixture')
        with self.assertRaises(GateBlocked):
            self.layer.gate('REQ-2')
        self.assertEqual((self.root / 'package.json').read_text(), '{"working":true}')
        self.assertEqual(self.flow.run_specs.call_args.args[0], ['REQ-1.spec.ts'])
        self.assertFalse(self.layer.state.data['nodes']['REQ-2']['code_done'])

    def test_business_cannot_execute_before_all_basic_gates_or_in_audit_bypass(self):
        self.freeze()
        _, row = self.business_case()
        self.assertEqual(self.layer.selected([row['file']])[0], 0)
        with self.assertRaises(GateBlocked):
            self.layer.execute_business()
        self.flow.run_specs = Flow.run_specs.__get__(self.flow)
        self.flow.app_server = Mock()
        self.assertIn('forbidden', self.flow.run_specs([row['file']], audit_candidate=True).error)
        self.assertIn('no frozen', self.flow.run_specs([row['file']]).error)
        self.flow.app_server.assert_not_called()

    def test_empty_duplicate_skipped_or_incomplete_measurements_never_pass(self):
        self.freeze()
        specs = self.layer.basic_specs('REQ-1')
        row = self.layer.state.data['nodes']['REQ-1']['cases'][0]
        for report in (RunSummary(), measurement([row, row]), RunSummary(total=1, passed=1),
                       RunSummary(total=1, results=[TestOutcome(row['title'], False, 'skipped', 1, file=row['file'])])):
            self.assertFalse(self.layer.complete(report, specs))

    def test_dispute_is_terminal_without_adjudication_or_further_execution(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        def run(specs, **kwargs):
            return self.run_specs(specs, **kwargs) if getattr(self.flow, '_layered_execution_level', None) == 'basic' else measurement([row], False)
        self.flow.run_specs.side_effect = run
        self.flow.turn = Mock(return_value=(True, '<<<TEST_DISPUTE>>>' + json.dumps(
            {'case_ids': [key], 'reason': 'The original requirement forbids this expected transition.'}) + '<<<END TEST_DISPUTE>>>'))
        self.flow.review_failed_derived_spec_with_model = Mock()
        self.layer.execute_business()
        self.layer.execute_business()
        self.assertEqual(self.flow.turn.call_count, 1)
        self.assertEqual(row['status'], 'disputed')
        self.assertEqual(self.layer.state.data['stops'][key]['attempts'], 1)
        self.flow.review_failed_derived_spec_with_model.assert_not_called()
        before = self.flow.run_specs.call_count
        self.layer.business_producer_done = True
        self.layer.final_verify()
        self.assertEqual(self.flow.run_specs.call_count, before + 1)  # basics only
        self.assertFalse(self.flow.test_verdict['REQ-1'])
        restarted = LayeredState(self.root, self.tree, ['REQ-1', 'REQ-2'])
        self.assertFalse(restarted.begin_repair([key]))

    def test_structured_codegen_preserves_the_programmer_dispute_protocol(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        self.layer.state.begin_repair([key])
        self.flow.codegen_mode = Mock(return_value=True)
        self.flow.use_structured_edits = Mock(return_value=True)
        self.flow.llm_proxy = SimpleNamespace()
        self.flow.repair_memory_context = Mock(return_value='')
        self.flow.turn = Mock(return_value=(True, '<<<TEST_DISPUTE>>>' + json.dumps(
            {'case_ids': [key], 'reason': 'Original requirement forbids this expectation.'}) + '<<<END TEST_DISPUTE>>>'))
        self.layer.repair('REQ-1', measurement([row], False), [key])
        self.assertEqual(self.layer.state.data['stops'][key]['state'], 'disputed')
        self.assertEqual(self.flow.turn.call_count, 1)
        self.assertEqual(self.flow.turn.call_args.kwargs['request_budget'], 1)

    def test_accepted_failure_gets_only_two_repairs_and_checked_source_is_kept(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        def run(specs, **kwargs):
            return self.run_specs(specs, **kwargs) if getattr(self.flow, '_layered_execution_level', None) == 'basic' else measurement([row], False)
        self.flow.run_specs.side_effect = run
        def repair(*args, **kwargs):
            (self.root / 'backend/app.js').write_text('safe proposed repair')
            return True, '<<<KEEP CODE>>>'
        self.flow.turn = Mock(side_effect=repair)
        self.layer.execute_business()
        self.assertEqual(self.flow.turn.call_count, 2)
        self.assertEqual(row['status'], 'repair_exhausted')
        self.assertEqual(self.layer.state.data['stops'][key]['attempts'], 2)
        self.assertIn('FROZEN TEST EVIDENCE', self.flow.turn.call_args.args[0])
        self.assertEqual(self.flow.turn.call_args.kwargs['request_budget'], 1)
        self.layer.business_producer_done = True
        self.layer.final_verify()
        self.layer.final_verify()  # no repeat on unchanged evidence
        self.assertEqual(self.flow.turn.call_count, 2)
        self.assertEqual((self.root / 'backend/app.js').read_text(), 'safe proposed repair')
        self.assertFalse(self.flow.test_verdict['REQ-1'])

    def test_unsafe_business_edit_restores_root_configuration_and_removes_added_code(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        self.assertTrue(self.layer.state.begin_repair([key]))
        self.flow.snapshot_protected()
        def repair(*args, **kwargs):
            (self.root / 'package.json').write_text('invalid json')
            (self.root / 'new-shared.js').write_text('bad added file')
            self.flow.restore_protected()  # normal author post-turn restoration
            return True, '<<<KEEP CODE>>>'
        self.flow.turn = Mock(side_effect=repair)
        self.layer.static_check = lambda: 'invalid root configuration' if (self.root / 'package.json').read_text() == 'invalid json' else ''
        self.layer.repair('REQ-1', measurement([row], False), [key])
        self.assertEqual((self.root / 'package.json').read_text(), '{"working":true}')
        self.assertFalse((self.root / 'new-shared.js').exists())
        self.assertEqual(row['retention'], 'rollback')
        persisted = json.loads(self.layer.state.path.read_text())
        self.assertEqual(persisted['stops'][key]['attempts'], 1)
        self.assertEqual(self.flow.run_specs.call_count, 1)  # candidate static rejection; rollback actually measured

    def test_application_rollback_cannot_revoke_a_dispute_or_new_authoritative_test(self):
        self.freeze(complete=True)
        before = ApplicationSnapshot(self.flow)
        key, row = self.business_case()
        self.layer.state.dispute(key, 'incorrect source interpretation')
        (self.root / 'backend/app.js').write_text('bad repair')
        (self.root / 'design/analysis').mkdir(parents=True)
        (self.root / 'design/analysis/review.json').write_text('{}')
        before.restore()
        self.assertEqual(json.loads(self.layer.state.path.read_text())['stops'][key]['state'], 'disputed')
        self.assertTrue((self.flow.tests_dir / row['file']).is_file())
        self.assertTrue((self.root / 'design/analysis/review.json').is_file())

    def test_snapshot_excludes_exact_authority_paths_but_keeps_nested_application_design(self):
        frontend = self.root / 'frontend'
        (frontend / 'src/design').mkdir(parents=True)
        style = frontend / 'src/design/theme.js'
        style.write_text('safe theme')
        self.flow.tests_dir = frontend / 'tests'
        self.flow.tests_dir.mkdir()
        test = self.flow.tests_dir / 'immutable.spec.ts'
        test.write_text('authority')
        before = ApplicationSnapshot(self.flow)
        self.assertIn('frontend/src/design/theme.js', before.files)
        self.assertNotIn('frontend/tests/immutable.spec.ts', before.files)
        style.write_text('unsafe theme')
        test.write_text('new authority evidence')
        before.restore()
        self.assertEqual(style.read_text(), 'safe theme')
        self.assertEqual(test.read_text(), 'new authority evidence')

    def test_unsafe_symlink_is_rejected_and_rollback_never_follows_it(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        self.layer.state.begin_repair([key])
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'private.js').write_text('must not change')
        self.layer.static_check = LayeredTests.static_check.__get__(self.layer)
        def edit(*args, **kwargs):
            (self.root / 'backend/app.js').unlink()
            (self.root / 'backend/app.js').symlink_to(outside / 'private.js')
            (self.root / 'shared').symlink_to(outside, target_is_directory=True)
            return True, '<<<KEEP CODE>>>'
        self.flow.turn = Mock(side_effect=edit)
        with patch('generation_checks.check_batch', return_value=dict(errors=[], checked=['syntax'],
                deferred=[], readiness='syntax_checked', warnings=[])):
            self.layer.repair('REQ-1', measurement([row], False), [key])
        self.assertEqual((outside / 'private.js').read_text(), 'must not change')
        self.assertEqual((self.root / 'backend/app.js').read_text(), 'good application')
        self.assertFalse((self.root / 'shared').is_symlink())
        self.assertEqual(row['retention'], 'rollback')

    def test_basic_runner_switch_cannot_change_application_source_identity(self):
        self.flow.derived_as_specs = False
        self.layer.authority_directories.clear()  # real Flow attaches official tests after coordinator construction
        self.freeze(complete=True)
        before = self.flow.app_source_digest()
        real_run = self.flow.run_specs
        def run(*args, **kwargs):
            self.assertEqual(self.flow.app_source_digest(), before)
            return real_run(*args, **kwargs)
        self.flow.run_specs = Mock(side_effect=run)
        self.layer.run_basic()
        self.assertEqual(self.layer.verified_basic_source, before)

    def test_unavailable_static_checker_is_never_promoted_to_a_pass(self):
        self.layer.static_check = LayeredTests.static_check.__get__(self.layer)
        incomplete = dict(errors=[], checked=[], deferred=['Babel parser unavailable'],
                          readiness='syntax_checked', warnings=[])
        with patch('generation_checks.check_batch', return_value=incomplete), patch(
                'runtime_diagnostics.ensure_binding_tools', return_value={'status': 'unavailable'}) as prepare:
            self.assertIn('incomplete', self.layer.static_check())
            self.assertIn('incomplete', self.layer.static_check())
        self.assertEqual(prepare.call_count, 2)

    def test_transient_static_dependency_failure_gets_one_bounded_retry(self):
        self.layer.static_check = LayeredTests.static_check.__get__(self.layer)
        incomplete = dict(errors=[], checked=[], deferred=['Babel parser unavailable'], readiness='syntax_checked', warnings=[])
        clean = dict(errors=[], checked=['syntax'], deferred=[], readiness='syntax_checked', warnings=[])
        with patch('generation_checks.check_batch', side_effect=[incomplete, clean]), patch(
                'runtime_diagnostics.ensure_binding_tools', side_effect=[{'status': 'unavailable'}, {'status': 'ready'}]) as prepare, patch('layered_tests.time.sleep'):
            self.assertEqual(self.layer.static_check(), '')
        self.assertEqual(prepare.call_count, 2)

    def test_incomplete_static_tooling_never_requests_a_behavior_repair(self):
        self.freeze()
        self.flow.repair_rounds = 3
        self.layer.static_incomplete = True
        self.layer.run_basic = Mock(return_value=RunSummary(error='static checker unavailable'))
        self.layer.repair = Mock()
        with self.assertRaises(GateBlocked):
            self.layer.gate('REQ-1')
        self.layer.repair.assert_not_called()

    def test_idle_business_publication_does_not_copy_or_save_control(self):
        self.flow.snapshot_protected = Mock()
        self.layer.state.on_save = Mock()
        for _ in range(100):
            self.layer.publish_business()
            self.layer.state.save()
        self.flow.snapshot_protected.assert_not_called()
        self.layer.state.on_save.assert_not_called()

    def test_business_publication_requires_explicit_file_ownership(self):
        self.freeze(complete=True)
        self.flow.trusted_derived_case = Mock(return_value=True)
        self.flow.derived_case_reviews = {('REQ-1', 'inferred title'): {'status': 'approved_behavior'}}
        self.layer.publish_business()
        self.assertFalse(self.layer.state.data['cases'])

    def test_one_immutable_business_file_is_discovered_once_for_multiple_case_publications(self):
        self.freeze(complete=True)
        self.flow.trusted_derived_case = Mock(return_value=True)
        titles = ['first [case 1]', 'second [case 1]']
        rel = 'REQ-1.spec.ts'
        (self.flow.tests_dir / rel).write_text("import {test} from '@playwright/test';\n" + '\n'.join(
            f"test('{title}',async()=>{{}});" for title in titles))
        self.flow.derived_case_reviews = {('REQ-1', title): dict(status='approved_behavior',
            scenario_id='S' + str(i), file=rel) for i, title in enumerate(titles)}
        self.flow.runner.discover_cases = Mock(wraps=self.flow.runner.discover_cases)
        self.layer.publish_business()
        for _ in range(100):
            self.layer.publish_business()
        self.assertEqual(len(self.layer.state.data['cases']), 2)
        self.flow.runner.discover_cases.assert_called_once()

    def test_published_success_cannot_hide_an_approved_but_unloadable_case(self):
        self.freeze(complete=True)
        self.flow.trusted_derived_case = Mock(return_value=True)
        rel = 'REQ-1.spec.ts'
        (self.flow.tests_dir / rel).write_text("import {test} from '@playwright/test';\ntest('present',async()=>{});\n")
        self.flow.derived_case_reviews = {('REQ-1', title): dict(status='approved_behavior',
            scenario_id=title, file=rel) for title in ('present', 'missing')}
        self.layer.publish_business()
        self.layer.business_producer_done = True
        self.layer.final_verify()
        self.assertEqual(len(self.layer.state.data['cases']), 1)
        self.assertEqual(len(self.layer.state.data['publication_gaps']), 1)
        self.assertFalse(self.flow.test_verdict['REQ-1'])

    def test_malformed_dispute_records_do_not_abort_or_stop_other_cases(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        for body in ([], {'case_ids': [dict(bad=True)], 'reason': 'wrong'},
                     {'case_ids': key, 'reason': 'wrong'}, {'case_ids': [key], 'reason': 42}):
            self.flow.turn = Mock(return_value=(True, '<<<TEST_DISPUTE>>>' + json.dumps(body) + '<<<END TEST_DISPUTE>>>'))
            self.layer.repair('REQ-1', measurement([row], False), [])
        self.assertFalse(self.layer.state.data['stops'])

    def test_pending_business_cases_share_one_build_start_measurement(self):
        self.freeze(complete=True)
        _, first = self.business_case('first case', 'S1')
        _, second = self.business_case('second case', 'S2')
        source = "import {test} from '@playwright/test';\ntest('first case', async()=>{});\ntest('second case', async()=>{});\n"
        path = self.flow.tests_dir / first['file']
        path.write_text(source)
        for row in (first, second):
            row['dependencies'] = {row['file']: digest(path.read_bytes())}
        self.layer.execute_business()
        self.assertEqual([first['status'], second['status']], ['passed', 'passed'])
        self.assertEqual(self.flow.run_specs.call_count, 1)

    def test_author_decides_rollback_only_after_two_observed_failed_repairs(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        failures = []
        def run(specs, **kwargs):
            if getattr(self.flow, '_layered_execution_level', None) == 'basic':
                return self.run_specs(specs, **kwargs)
            failures.append((self.root / 'backend/app.js').read_text())
            return measurement([row], False)
        self.flow.run_specs.side_effect = run
        def edit(*args, **kwargs):
            (self.root / 'backend/app.js').write_text('repair ' + str(self.flow.turn.call_count))
            return True, 'fix proposed'
        self.flow.turn = Mock(side_effect=edit)
        def decide(*args, **kwargs):
            self.assertEqual(self.flow.turn.call_count, 2)
            self.assertEqual(failures, ['good application', 'repair 1', 'repair 2'])
            return True, '{"decision":"ROLLBACK","reason":"the second repair adds no benefit"}'
        self.flow.text_turn = Mock(side_effect=decide)
        self.layer.execute_business()
        self.assertEqual((self.root / 'backend/app.js').read_text(), 'repair 1')
        self.assertEqual(row['retention'], 'rollback')
        self.assertEqual(self.flow.text_turn.call_count, 1)
        self.assertEqual(self.layer.state.data['stops'][key]['decision'], 'ROLLBACK')
        row['status'] = 'pending'
        self.layer.execute_business()
        self.assertEqual(self.flow.turn.call_count, 2)
        self.assertEqual(self.flow.text_turn.call_count, 1)

    def test_missing_entry_is_completed_compiled_and_independently_audited(self):
        candidate = self.candidate(self.nodes[0])
        original = self.layer.basic_candidates['REQ-1']
        self.layer.basic_candidates['REQ-1'] = {**original, 'source': '', 'gap': 'entry not mechanically known'}
        self.layer.state.data['nodes']['REQ-1']['basic'] = 'pending'
        contract = {'navigation': [], 'assertion': {'kind': 'role', 'role': 'button', 'name': 'Open 1',
                                                   'quote': self.nodes[0]['description']}}
        self.flow.text_turn = Mock(side_effect=[(True, json.dumps(contract)), (True, json.dumps(candidate['decision']))])
        result = self.layer.review_basic('REQ-1')
        self.assertEqual(result['status'], 'approved_basic')
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.layer.install_basic(result)
        self.assertEqual(self.layer.state.data['nodes']['REQ-1']['basic'], 'frozen')
        self.assertIn('entry contract', (self.flow.basic_tests_dir / original['file']).read_text())
        self.assertNotIn('good application', self.flow.text_turn.call_args_list[0].args[0])

    def test_entry_completion_cannot_turn_an_inherited_home_rule_into_every_nodes_gate(self):
        contract = {'assertion': {'kind': 'home', 'quote': 'Open the application and display the home page.'}}
        with self.assertRaises(ValueError):
            compile_entry_contract('REQ-1', contract, {'ROOT': contract['assertion']['quote'],
                                                     'REQ-1': 'Searching notes filters the visible entries.'})

    def test_entry_completion_rejects_arbitrary_code_and_unquoted_literals(self):
        for body in ([], {'navigation': [{'kind': 'script', 'name': 'Open 1', 'quote': self.nodes[0]['description']}],
                         'assertion': {'kind': 'role', 'role': 'button', 'name': 'Open 1', 'quote': self.nodes[0]['description']}},
                     {'assertion': {'kind': 'reachable', 'name': 'invented target', 'quote': self.nodes[0]['description']}}):
            with self.assertRaises(ValueError):
                compile_entry_contract('REQ-1', body, {'REQ-1': self.nodes[0]['description']})

    def test_blocked_run_preserves_and_rehearses_only_a_safe_partial_application(self):
        self.freeze()
        self.layer.gate('REQ-1')
        (self.root / 'backend/app.js').write_text('broken unfinished second node')
        self.flow.rehearsal = Mock(return_value=True)
        self.assertTrue(self.layer.deliver_blocked('REQ-2: no frozen contract'))
        self.assertEqual((self.root / 'backend/app.js').read_text(), 'good application')
        self.assertFalse(self.layer.state.data['nodes']['REQ-2']['code_done'])
        self.assertEqual(self.flow.run_specs.call_args.args[0], ['REQ-1.spec.ts'])
        self.flow.rehearsal.assert_called_once_with(repair_on_failure=False, restore_on_failure=False)

    def test_run_rehearses_partial_delivery_before_cleaning_up_its_test_runtime(self):
        self.freeze()
        self.layer.gate('REQ-1')
        flow = self.flow
        events = Mock()
        runtime = SimpleNamespace(events=events, traceability=Mock(), git=Mock())
        flow.rehearsal = Mock(return_value=True)
        for name in ('classify_tree', 'maybe_probe', 'setup_playwright', 'start_llm_proxy', 'prepare_build',
                     'prime_generation_dependencies', 'write_preview_ready', 'cleanup_playwright', 'stop_llm_proxy'):
            setattr(flow, name, Mock())
        flow.resolve_seed_conflicts = Mock(return_value=self.tree)
        flow.implement_sequential = Mock(side_effect=GateBlocked('REQ-2: basic rejected'))
        self.layer.prepare = Mock()
        sequence = []
        flow.write_quality_summary = Mock(side_effect=lambda **kw: sequence.append(('measured', kw['startable'])))
        flow.postflight = Mock(side_effect=lambda: sequence.append(('cleanup', None)))
        with patch('main.AgentRuntime.from_env', return_value=runtime), patch('main.load_requirement_tree', return_value=self.tree), \
                patch('main.previous_requirement_records', return_value={}), patch('main.locate_acceptance_tests', return_value=flow.tests_dir), \
                patch('layered_tests.LayeredTests', return_value=self.layer), patch('main.build_octos_env', return_value={}), \
                patch('main.write_profile_defaults'), patch('main._port_watchdog'), patch('main._reap_stray_processes'), \
                patch('main._postflight_structure_check'), patch('main._free_web_port'), patch.dict('os.environ', {'OCTOS_ARC_DRYRUN': '1'}):
            self.assertEqual(flow.run(), 0)
        self.assertEqual(sequence, [('measured', True), ('cleanup', None)])
        flow.write_preview_ready.assert_called_once()
        events.mark_run_failed.assert_not_called()
        events.mark_run_completed.assert_called_once()
        self.assertIsNone(flow.test_verdict['REQ-2'])

    def test_cached_partial_initial_design_is_completed_and_reviewed_before_publication(self):
        flow = self.flow
        original = {'data_model': {}, 'routes': [], 'pages': [{'path': '/', 'purpose': 'Home', 'requirements': ['REQ-1']}],
                    'modules': [], 'contracts': [], 'domain_contracts': [], 'commands': [], 'notes': ''}
        completed = {**original, 'pages': [{'path': '/', 'purpose': 'Home', 'requirements': ['REQ-1', 'REQ-2']}]}
        directory = self.root / '.arc/design'
        directory.mkdir(parents=True)
        (directory / 'app.meta.json').write_text('{}')
        flow.stored_app_design = Mock(return_value=original)
        flow._initial_design_required = True
        flow.recover_category_design = Mock(return_value=completed)
        def review(tree, design):
            flow._design_semantics_reviewed = True
            return design
        flow.review_domain_design = Mock(side_effect=review)
        design = flow.app_design(self.tree, self.nodes)
        self.assertEqual(design, completed)
        flow.recover_category_design.assert_called_once_with(self.tree, self.nodes, accepted=original)
        flow.review_domain_design.assert_called_once_with(self.tree, completed)
        self.assertFalse(flow._design_blocked)
        self.assertEqual(json.loads((directory / 'app.json').read_text()), completed)

    def test_static_gate_rejects_root_json_and_incomplete_checks(self):
        self.layer.static_check = LayeredTests.static_check.__get__(self.layer)
        clean = dict(errors=[], checked=['syntax'], deferred=[], readiness='syntax_checked', warnings=[])
        (self.root / 'package.json').write_text('{bad json')
        with patch('generation_checks.check_batch', return_value=clean):
            self.assertIn('invalid JSON', self.layer.static_check())
        (self.root / 'package.json').write_text('{}')
        with patch('generation_checks.check_batch', return_value=dict(errors=[], checked=[],
                deferred=['backend bindings: unavailable'], readiness='syntax_checked', warnings=[])):
            self.assertIn('incomplete', self.layer.static_check())

    def test_basic_publication_is_independent_of_a_paused_business_pipeline(self):
        reply = self.candidate(self.nodes[0])
        self.flow._derived_background_pipeline = SimpleNamespace(stopping=False, pause=Mock())
        self.flow._derived_background_pipeline.pause()
        self.layer.install_basic(reply)
        self.assertEqual(self.layer.state.data['nodes']['REQ-1']['basic'], 'frozen')
        self.layer.cancelled = True
        other = self.candidate(self.nodes[1])
        self.layer.install_basic(other)
        self.assertEqual(self.layer.state.data['nodes']['REQ-2']['basic'], 'pending')

    def test_new_frozen_business_case_is_consumed_before_producer_finishes(self):
        self.freeze(complete=True)
        self.flow._background_spec_scheduled_ids = {'REQ-1', 'REQ-2'}
        pipeline = SimpleNamespace(resume=Mock(), close=Mock(), wait=Mock(side_effect=[False, True]))
        self.flow._derived_background_pipeline = pipeline
        self.layer.business_started = True
        self.layer.publish_business = Mock()
        polls = []
        def poll():
            polls.append(1)
            if len(polls) == 2:
                self.business_case('late frozen business test')
        self.flow.poll_background_specs.side_effect = poll
        self.layer.business()
        self.assertTrue(self.layer.business_producer_done)
        self.assertEqual(next(iter(self.layer.state.data['cases'].values()))['status'], 'passed')
        self.assertTrue(any(call.args[0] == ['REQ-1.spec.ts'] for call in self.flow.run_specs.call_args_list))
        pipeline.close.assert_called()

    def test_business_title_file_and_helper_changes_cannot_reset_a_published_stop(self):
        self.freeze(complete=True)
        self.flow.trusted_derived_case = Mock(return_value=True)
        first = 'Original [case 1]'
        source = "import {test} from '@playwright/test';\nimport './helper';\n"
        (self.flow.tests_dir / 'REQ-1.spec.ts').write_text(source + f"test('{first}', async () => {{}});\n")
        (self.flow.tests_dir / 'helper.ts').write_text('export const value = 1;')
        self.flow.derived_case_reviews = {('REQ-1', first): dict(status='approved_behavior', scenario_id='S1', file='REQ-1.spec.ts')}
        self.layer.publish_business()
        key = next(iter(self.layer.state.data['cases']))
        self.layer.state.begin_repair([key]); self.layer.state.begin_repair([key])
        self.layer.state.dispute(key, 'wrong expected outcome')
        renamed = 'Renamed [case 1]'
        (self.flow.tests_dir / 'renamed.spec.ts').write_text(source + f"test('{renamed}', async () => {{}});\n")
        (self.flow.tests_dir / 'helper.ts').write_text('export const value = 2;')
        self.flow.derived_case_reviews = {('REQ-1', renamed): dict(status='approved_behavior', scenario_id='S1', file='renamed.spec.ts')}
        self.layer.publish_business()
        self.assertEqual(list(self.layer.state.data['cases']), [key])
        self.assertFalse(self.layer.state.begin_repair([key]))
        self.assertTrue(self.layer.dependencies_intact(self.layer.state.data['cases'][key]))

    def test_resumed_and_private_producers_do_not_review_a_stopped_scenario(self):
        self.freeze(complete=True)
        key, row = self.business_case()
        self.layer.state.dispute(key, 'wrong expected transition')
        resumed = LayeredTests(self.flow, self.nodes)
        self.flow.layered = resumed
        self.assertIn(('REQ-1', 'S1'), self.flow.terminal_derived_scenarios())
        private = Flow(argparse.Namespace(web_port=3000), self.root, self.req)
        private._terminal_derived_scenarios = self.flow.terminal_derived_scenarios
        self.assertIn(('REQ-1', 'S1'), private.terminal_derived_scenarios())
        self.flow.planned_derived_scenarios = Mock(return_value=[dict(id='S1', node_id='REQ-1', title='Scenario')])
        self.flow.derived_case_reviews = {}
        candidate = dict(node_id='REQ-1', scenario_id='S1', title='Scenario [case 1]', file='REQ-1.spec.ts',
                         id='candidate', case_hash='case', file_hash='file', requirements_hash='source',
                         status='unreviewed', requirement='Records remain visible.', case='await h.expectValue();')
        self.flow.text_turn = Mock(return_value=(False, 'must not be requested'))
        with patch('main.collect_cases', return_value=[candidate]), patch('main.audit_generated_suite', return_value=[]):
            self.flow.review_derived_cases({'REQ-1'})
        self.flow.text_turn.assert_not_called()
        self.assertEqual(candidate['status'], 'unverified_gap')

    def test_official_discovery_uses_actual_nested_dynamic_and_shared_cases(self):
        self.freeze(complete=True)
        self.flow.derived_as_specs = False
        self.flow.spec_map = {'REQ-1': ['official.spec.ts'], 'REQ-2': [], None: ['shared.spec.ts']}
        for name in ('official.spec.ts', 'shared.spec.ts'):
            (self.flow.tests_dir / name).write_text('/* runtime-defined official cases */')
        self.flow.runner.discover_cases = Mock(side_effect=lambda specs: ([{
            'file': specs[0], 'title': 'dynamic title "α"', 'line': 5}], ''))
        self.layer.business_started = True
        self.layer.business()
        self.assertTrue(self.flow.test_verdict['REQ-1'])
        self.assertTrue(self.flow.test_verdict['REQ-2'])  # shared regression is assigned to all nodes
        self.assertEqual(len(self.layer.state.data['cases']), 2)


class PureSafetyTests(unittest.TestCase):
    def test_explicit_home_entry_can_freeze_without_inventing_a_named_control(self):
        node = {'id': 'A', 'description': 'Open the application and display the home page.'}
        source, error = compile_basic(node, suite_fixtures([node]), '')
        self.assertFalse(error)
        self.assertIn('await h.openHome(page)', source)
        self.assertIn("expect(page.locator('body')).toBeVisible()", source)
        self.assertNotIn('expectRole', source)

    def test_corrupt_repair_counter_blocks_resume_instead_of_resetting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = LayeredState(Path(tmp), {'id': 'A'}, ['A'])
            key = state.identity('A', 'S1')
            state.begin_repair([key]); state.begin_repair([key])
            state.data['stops'][key]['state'] = 'repair_exhausted'
            state.save()
            recovered = LayeredState(Path(tmp), {'id': 'A'}, ['A'])
            self.assertFalse(recovered.begin_repair([key]))
            for invalid in (-1, '2', None, True, 3):
                state.data['stops'][key]['attempts'] = invalid
                state.save()
                with self.assertRaises(ValueError):
                    LayeredState(Path(tmp), {'id': 'A'}, ['A'])

    def test_helper_evidence_keeps_globals_and_transitive_function_references(self):
        source = '''import type {Page} from '@playwright/test';
const ROLE = 'button';
type Role = string;
function indirect(page: Page) { return page.getByRole(ROLE); }
export async function expectRole(page: Page) { const lookup = indirect; return lookup(page); }
export function unrelated(page: Page) { return page.getByText('other'); }
'''
        excerpt = helper_excerpt(source, 'await h.expectRole(page);')
        self.assertIn("const ROLE = 'button';", excerpt)
        self.assertIn('type Role = string;', excerpt)
        self.assertIn('function indirect', excerpt)
        self.assertIn('import type', excerpt)
        self.assertNotIn('function unrelated', excerpt)
        self.assertEqual(helper_excerpt(source, 'await h.unknown(page);'), source)

    def test_basic_api_uses_only_a_literal_source_endpoint_and_imports_expect(self):
        for description, grounded in (('GET /health returns 200.', True), ('GET /items/:id returns 200.', False)):
            node = {'id': 'A', 'description': description}
            source, gap = compile_basic(node, suite_fixtures([node]), '')
            self.assertEqual(bool(source), grounded)
            if source:
                self.assertIn('import { test, expect }', source)
                self.assertIn("page.request.get('/health')", source)
            else:
                self.assertTrue(gap)

    def test_unknown_actor_and_business_setup_do_not_become_basic_entry(self):
        for given in ('The team maintainer is signed in.', 'Scenario setup: A1 = 10.'):
            node = {'id': 'A', 'description': 'The page has a button named “Save”.', 'scenarios': [
                {'name': 'role operation', 'steps': [{'keyword': 'GIVEN', 'content': given}]}]}
            source, gap = compile_basic(node, suite_fixtures([node]), '')
            if 'maintainer' in given:
                self.assertFalse(source)
                self.assertTrue(gap)

    def test_dependency_closure_includes_side_effect_imports_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.spec.ts').write_text("import './setup';\nimport {h} from './helpers';")
            (root / 'setup.ts').write_text("import './constants';")
            (root / 'helpers.ts').write_text('export const h = 1;')
            (root / 'constants.ts').write_text('export const secret = 1;')
            self.assertEqual(set(dependency_files(root, 'a.spec.ts')), {'a.spec.ts', 'setup.ts', 'helpers.ts', 'constants.ts'})
            (root / 'setup.ts').write_text("import '../outside';")
            with self.assertRaises(ValueError):
                dependency_files(root, 'a.spec.ts')

    def test_exact_source_compression_is_lossless_including_negative_rules(self):
        value = 'Only owners may delete records; after rejection saved state remains unchanged. ' * 8
        original = value + '\nOther independent branch.\n' + value
        compact = compact_source_references(original, [{'description': value}])
        body, table = compact.split('\nEXACT SOURCE TABLE (expand references before interpreting evidence):\n')
        for marker, source in json.loads(table).items():
            body = body.replace(marker, source)
        self.assertEqual(body, original)
        self.assertLess(len(compact), len(original))

    def test_snapshot_copies_original_sources_contracts_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, req = Path(tmp) / 'app', Path(tmp) / 'task'
            root.mkdir(); req.mkdir()
            leaf = {'id': 'A', 'description': 'Records remain visible.'}
            tree = {'id': 'ROOT', 'children': [leaf]}
            (req / 'requirements.yaml').write_text('full authoritative requirements')
            (req / 'reference').mkdir()
            (req / 'reference/manifest.json').write_text('{"original":"manifest"}')
            flow = Flow(argparse.Namespace(web_port=3000), root, req)
            flow.app_design_doc = {'data_model': {'records': {'id': 'string'}}, 'pages': [
                {'path': '/', 'purpose': 'Home', 'requirements': ['A']}], 'obligations': []}
            destination = publish_initial(flow, tree, [leaf])
            manifest = json.loads((destination / 'manifest.json').read_text())
            self.assertEqual(manifest['status'], 'complete')
            self.assertEqual((destination / 'original-requirements/requirements.yaml').read_text(), 'full authoritative requirements')
            index = json.loads((destination / 'test-planning-index.json').read_text())
            self.assertTrue(index['sources'])
            self.assertEqual(index['ancestry']['A'], ['ROOT', 'A'])
            self.assertEqual(publish_initial(flow, tree, [leaf]), destination)
            (destination / 'extra-untracked.json').write_text('{}')
            with self.assertRaises(GateBlocked):
                publish_initial(flow, tree, [leaf])

    def test_partial_initial_design_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = {'id': 'A', 'description': 'Records remain visible.'}
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.app_design_doc = {'pages': [{'path': '/', 'purpose': 'Home', 'requirements': []}]}
            with self.assertRaises(GateBlocked):
                publish_initial(flow, leaf, [leaf])
            self.assertFalse((root / 'design/initial').exists())

    def test_initial_obligations_skip_only_complete_same_version_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = {'id': 'A', 'description': 'If saving fails, the saved item remains unchanged.'}
            tree = {'id': 'ROOT', 'description': 'Records remain visible.', 'children': [leaf]}
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.requirement_tree = tree
            for name, value in {'remaining': 10000, 'final_phase_reserve': 0, 'wound_down': False,
                                'review_budget_spent': False, 'derived_preflight_tokens_spent': False,
                                'codegen_context_chars': 100000}.items():
                setattr(flow, name, Mock(return_value=value))
            flow.metric = flow.snapshot_protected = flow.start_derived_designs = Mock()
            flow.initial_test_planning_index = {'requirements_hash': digest(tree), 'obligations': [
                {'id': owner, 'requirement_id': owner, 'quote': quote, 'outcome': quote, 'branch': branch}
                for owner, quote, branch in [('ROOT', tree['description'], 'success'), ('A', leaf['description'], 'rejection')]]}
            flow.text_turn = Mock(return_value=(False, 'provider unavailable'))
            prepare_obligations(flow, [leaf])
            self.assertEqual(flow.derived_obligation_status['A']['method'], 'reused_initial')
            flow.text_turn.assert_not_called()
            flow.derived_obligation_status = {}; flow.derived_obligations = []
            flow.initial_test_planning_index['obligations'].pop()
            prepare_obligations(flow, [leaf])
            self.assertEqual(flow.text_turn.call_count, 1)
            self.assertIn('Extract only missing outcomes', flow.text_turn.call_args.args[0])
            self.assertEqual(flow.derived_obligation_status['A']['status'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
