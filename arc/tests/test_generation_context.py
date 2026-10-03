import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import main
from acceptance import RunSummary
from compatibility_checks import advisory_text, probe_isolated_app, probe_started_app
from source_index import SourceIndex


class ToolSpecContextTests(TestCase):
    def test_large_support_preserves_spec_and_discloses_unquoted_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = "import * as h from './helpers';\ntest('persists', async () => { await h.save(); });"
            helper = 'export async function save() { const payload = "' + 'x' * 5000 + '"; }'
            (root / 'REQ-1.spec.ts').write_text(spec)
            (root / 'helpers.ts').write_text(helper)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            text = main.inline_spec_text(root, ['REQ-1.spec.ts', 'helpers.ts'], 900)
            self.assertIn(spec, text)
            self.assertIn('Not fully quoted', text)
            self.assertIn('helpers.ts', text)
            self.assertLessEqual(len(text), 900)
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})

    def test_oversized_spec_keeps_complete_cases_and_setup_in_original_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = "test('first', async () => { expect('first').toBe('first'); });\n"
            setup = 'const value = "later setup";\n'
            second = "test('large', async () => { expect('" + 'x' * 5000 + "').toBe(value); });\n"
            (root / 'REQ-1.spec.ts').write_text(first + setup + second)
            text = main.inline_spec_text(root, ['REQ-1.spec.ts'], 900)
            self.assertIn(first + setup, text)
            self.assertNotIn("test('large'", text)
            self.assertIn('selected complete top-level cases', text)
            self.assertIn('Not fully quoted', text)
            self.assertLessEqual(len(text), 900)

    def test_uncertain_or_nested_registration_is_not_cut_into_incomplete_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'REQ-1.spec.ts').write_text("test.describe('group', () => { test('big', () => {" + 'x' * 3000 + '}); });')
            (root / 'REQ-2.spec.ts').write_text("test('small', () => { expect(1).toBe(1); });")
            text = main.inline_spec_text(root, ['REQ-1.spec.ts', 'REQ-2.spec.ts'], 900)
            self.assertNotIn("test.describe('group'", text)
            self.assertIn("test('small'", text)
            self.assertIn('REQ-1.spec.ts', text)

    def test_reachable_helpers_keep_transitive_support_without_unrelated_large_function(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'REQ-1.spec.ts').write_text("test('save', async () => { await save(); });")
            (root / 'helpers.ts').write_text("import { persist } from './storage';\nexport function save() { return persist(); }\nexport function unrelated() { return '" + 'x' * 4000 + "'; }")
            (root / 'storage.ts').write_text('export function persist() { return 1; }')
            text = main.inline_spec_text(root, ['REQ-1.spec.ts', 'helpers.ts', 'storage.ts'], 1500)
            self.assertIn('function persist()', text)
            self.assertIn('function save()', text)
            self.assertNotIn('function unrelated()', text)
            self.assertIn('reachable helper declarations', text)


class ApiSourceContextTests(TestCase):
    def sources(self):
        return {'frontend/src/App.jsx': "import UI from './UI';\n<Routes><Route path='/edit' element={<UI />} /></Routes>",
                'frontend/src/UI.jsx': "import {requestJson} from './request';\nrequestJson(`/api/records/${id}`, {method:'PATCH'});",
                'frontend/src/request.js': '',
                'backend/server.js': "require('./routes/records');",
                'backend/routes/records.js': "const store = require('../lib/store'); app.patch('/api/records/:id', handler);",
                'backend/lib/store.js': 'exports.store = {};',
                'backend/routes/read.js': "app.get('/api/records/:id', read);",
                'backend/routes/unrelated.js': "app.patch('/api/other/:id', other);"}

    def test_api_matching_follows_method_and_route_parameters(self):
        index = SourceIndex(self.sources())
        self.assertEqual(index.api_owners({'frontend/src/UI.jsx'}), {'backend/routes/records.js'})
        context = index.contract_context([], index.api_owners({'frontend/src/UI.jsx'}))
        self.assertIn('backend/lib/store.js', context)

    def test_external_computed_commented_and_mounted_calls_stay_unknown(self):
        sources = self.sources()
        sources['frontend/src/UI.jsx'] = '''fetch('https://elsewhere/api/records/1'); fetch(url);
// requestJson('/api/records/1', {method:'PATCH'});
fetch('/api/mounted/1');'''
        sources['backend/routes/mounted.js'] = "router.get('/api/mounted/:id', handler);"
        self.assertEqual(SourceIndex(sources).api_owners({'frontend/src/UI.jsx'}), set())

    def test_get_without_options_and_unknown_method_choose_possible_owners(self):
        sources = self.sources()
        sources['frontend/src/UI.jsx'] = "fetch('/api/records/1');"
        self.assertEqual(SourceIndex(sources).api_owners({'frontend/src/UI.jsx'}), {'backend/routes/read.js'})
        sources['frontend/src/UI.jsx'] = "fetch('/api/records/1', options);"
        self.assertEqual(SourceIndex(sources).api_owners({'frontend/src/UI.jsx'}),
                         {'backend/routes/read.js', 'backend/routes/records.js'})

    def test_method_in_a_later_callback_does_not_change_a_get_request(self):
        sources = self.sources()
        sources['frontend/src/UI.jsx'] = "fetch('/api/records/1').then(() => ({method:'PATCH'}));"
        self.assertEqual(SourceIndex(sources).api_owners({'frontend/src/UI.jsx'}), {'backend/routes/read.js'})

    def test_route_owner_and_store_outrank_unrelated_sources_without_becoming_mandatory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rel, source in self.sources().items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            rows = main.scored_sources(root, "await page.goto('/edit');")
            priorities = {str(row[3]): row[0] for row in rows}
            self.assertEqual(priorities['backend/routes/records.js'], 3.25)
            self.assertEqual(priorities['backend/lib/store.js'], 3.25)
            self.assertLess(priorities['backend/lib/store.js'], priorities['backend/routes/unrelated.js'])
            flow = object.__new__(main.Flow)
            required = flow.required_source_context("page.goto('/edit')", sources=self.sources())
            self.assertIn('frontend/src/UI.jsx', required)
            self.assertNotIn('backend/routes/records.js', required)


class CompatibilityIntegrationTests(TestCase):
    def flow(self, root, seconds=2000):
        flow = object.__new__(main.Flow)
        flow.output_dir = root
        flow.frozen_suite = {'name': 'hackathon--sheet'}
        flow.runner = SimpleNamespace(root=root)
        flow.app_source_digest = Mock(return_value='current')
        flow.final_measurement_reserve = Mock(return_value=100)
        flow.final_rehearsal_reserve = Mock(return_value=100)
        flow.remaining = Mock(return_value=seconds)
        flow.wound_down = Mock(return_value=False)
        flow.metric = Mock()
        flow.test_verdict = {'REQ-1': True}
        return flow

    def test_automatic_probe_is_once_per_run_and_does_not_change_acceptance_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            flow = self.flow(root)
            with patch('compatibility_checks.probe_isolated_app', return_value={'status': 'observed_failures', 'passed': 0, 'total': 4}) as run:
                flow.check_sheet_compatibility()
                flow.check_sheet_compatibility()
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs['budget'], 180)
            self.assertEqual(flow.test_verdict, {'REQ-1': True})
            report = json.loads((root / '.arc/compatibility/summary.json').read_text())
            self.assertEqual(report['source_hash'], 'current')
            self.assertEqual(report['authority'], 'compatibility_observation_only')

    def test_budget_and_task_admission_do_not_launch_a_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('compatibility_checks.probe_isolated_app') as run:
                flow = self.flow(root, seconds=250)
                flow.check_sheet_compatibility()
                self.assertEqual(flow._compatibility_result['status'], 'deferred_budget')
                flow = self.flow(root)
                flow.frozen_suite = {'name': 'hackathon--github'}
                flow.check_sheet_compatibility()
                self.assertFalse(hasattr(flow, '_compatibility_attempted'))
                run.assert_not_called()

    def test_missing_browser_and_incomplete_collection_are_unavailable(self):
        for results in [[SimpleNamespace(message='browserType.launch: missing executable', status='failed', title='x', ok=False)] * 4,
                        [SimpleNamespace(message='', status='passed', title='x', ok=True)] * 3]:
            summary = RunSummary(results=results)
            with patch('compatibility_checks.AcceptanceRunner') as runner:
                runner.return_value.run.return_value = summary
                result = probe_started_app(Path('/tmp'), Path('/tmp'), 'http://localhost', Mock())
            self.assertEqual(result['status'], 'unavailable')
            self.assertEqual(advisory_text(result), '')

    def test_isolated_start_failure_stops_server_and_preserves_source_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'store.json'
            data.write_text('{"count":7}')
            with patch('compatibility_checks.AppServer') as server:
                server.return_value.build.return_value = 'build failed'
                server.return_value.time_left.return_value = 10
                result = probe_isolated_app(root, root, root, root / 'report', Mock(), budget=30)
            self.assertEqual(result['status'], 'unavailable')
            server.return_value.stop.assert_called_once()
            self.assertEqual(data.read_text(), '{"count":7}')
            self.assertNotEqual(server.call_args.args[0], root)

    def test_stale_compatibility_is_not_fed_into_repair(self):
        flow = object.__new__(main.Flow)
        flow.requirement_nodes = {}
        flow._compatibility_result = {'source_hash': 'old', 'status': 'observed_failures',
                                     'cases': [{'name': 'sort', 'ok': False, 'first_error': 'old failure'}]}
        flow.app_source_digest = Mock(return_value='new')
        fields = dict(node_id='REQ-1', passed=0, total=1, failures='', test_location='', corrections='', slow='', port=3000, sources='')
        self.assertNotIn('old failure', flow.app_repair_prompt(**fields))
        flow.app_source_digest.return_value = 'old'
        self.assertIn('old failure', flow.app_repair_prompt(**fields))
