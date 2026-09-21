import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

from acceptance import RunSummary, TestOutcome
from generation_checks import helper_import_errors
from llm_proxy import reserve_edit_budget
import main
import test_whole_app_v5 as whole_tests


class StartupRecoveryTests(TestCase):
    setUp = whole_tests.WholeAppTests.setUp

    def test_codegen_rejects_invalid_helper_import_before_any_file_write(self):
        f = self.flow
        library = self.root / 'backend/lib'
        library.mkdir(parents=True)
        (library / 'store.js').write_text((main.BUNDLE_DIR / 'blueprints/store.js').read_text())
        f.text_turn = Mock(return_value=(True,
            "<<<FILE backend/routes/a.js>>>\nconst {loadTable} = require('../lib/store');\n<<<END FILE>>>\n"
            "<<<FILE frontend/src/new.js>>>\nconst value = 1;\n<<<END FILE>>>"))
        ok, reason = f.codegen_turn('implement new feature', 30, 'A implement', force_files=True)
        self.assertFalse(ok)
        self.assertIn('does not export loadTable', reason)
        self.assertEqual(f.last_codegen_written, [])
        self.assertFalse((self.root / 'frontend/src/new.js').exists())

    def test_functional_failure_after_recovery_resumes_without_claiming_pass(self):
        f = self.flow
        f._unresolved_startup_error = 'TypeError: missing export'
        f.whole_app_startup_repair = Mock(return_value=True)
        f.time_up = lambda: False
        f.record_tests = Mock()
        f.metric = Mock()
        f.run_specs = Mock(return_value=RunSummary(passed=0, total=1, results=[
            TestOutcome('A', False, 'failed', 1, file='A.spec.ts', message='missing control')]))
        self.assertTrue(f.recover_sequential_startup('A'))
        f.run_specs.assert_called_once_with(['A.spec.ts'])
        self.assertFalse(f.test_verdict['A'])
        self.assertEqual(f._unresolved_startup_error, '')
        f.record_tests.assert_called_once_with('A', ['A.spec.ts'], f.run_specs.return_value)

    def test_incomplete_load_never_resumes_and_repairs_are_bounded(self):
        f = self.flow
        f._unresolved_startup_error = 'SyntaxError'
        f.whole_app_startup_repair = Mock(return_value=True)
        f.time_up = lambda: False
        f.metric = Mock()
        f.run_specs = Mock(return_value=RunSummary(error='still cannot load'))
        self.assertFalse(f.recover_sequential_startup('A'))
        self.assertEqual(f.whole_app_startup_repair.call_count, 2)
        self.assertNotIn('A', f.test_verdict)

    def test_no_write_means_no_duplicate_measurement(self):
        f = self.flow
        f._unresolved_startup_error = 'SyntaxError'
        f.whole_app_startup_repair = Mock(return_value=False)
        f.run_specs = Mock()
        self.assertFalse(f.recover_sequential_startup('A'))
        f.run_specs.assert_not_called()


class HelperContractTests(TestCase):
    def test_pristine_export_and_alias_checks_without_executing_app(self):
        sources = {'backend/lib/store.js': (main.BUNDLE_DIR / 'blueprints/store.js').read_text(),
                   'backend/routes/a.js': "const {loadTable: load, read} = require('../lib/store');"}
        errors = helper_import_errors(sources, ['backend/routes/a.js'])
        self.assertEqual(len(errors), 1)
        self.assertIn('does not export loadTable', errors[0])
        sources['backend/routes/a.js'] = "const {read: load} = require('../lib/store.js');"
        self.assertEqual(helper_import_errors(sources, sources), [])
        sources['backend/routes/a.js'] = "const {loadTable} = require('../lib/store');"
        sources['backend/lib/store.js'] = 'module.exports = {loadTable};'
        self.assertEqual(helper_import_errors(sources, sources), [])

    def test_uncertain_syntax_is_left_to_runtime(self):
        sources = {'backend/lib/store.js': (main.BUNDLE_DIR / 'blueprints/store.js').read_text(),
                   'backend/routes/a.js': "const {read = fallback} = require('../lib/store');"}
        self.assertEqual(helper_import_errors(sources, sources), [])
        for source in ("/*\nconst {bogus} = require('../lib/store');\n*/", "const doc = `\nconst {bogus} = require('../lib/store');\n`;", "// const {bogus} = require('../lib/store');"):
            sources['backend/routes/a.js'] = source
            self.assertEqual(helper_import_errors(sources, sources), [])


class RepairBudgetTests(TestCase):
    def test_midpoint_notice_keeps_tools_and_does_not_accumulate(self):
        data = {'messages': [{'role': 'user', 'content': 'fix'}],
                'tools': [{'type': 'function', 'function': {'name': 'edit_file'}}]}
        body = json.dumps(data).encode()
        self.assertEqual(reserve_edit_budget(body, 1, 8), body)
        result = json.loads(reserve_edit_budget(body, 4, 8))
        self.assertEqual(result['tools'], data['tools'])
        self.assertIn('4 upstream requests remain', result['messages'][-1]['content'])
        result = json.loads(reserve_edit_budget(json.dumps(result).encode(), 5, 8))
        self.assertEqual(len(result['messages']), 2)
        self.assertIn('3 upstream requests remain', result['messages'][-1]['content'])
        self.assertIn('Do not guess', result['messages'][-1]['content'])
