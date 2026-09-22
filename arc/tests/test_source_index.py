from unittest import TestCase
from source_index import SourceIndex
from source_index import failure_groups
from source_index import select_repair_groups
from types import SimpleNamespace
import tempfile
from pathlib import Path
from unittest.mock import Mock
import main
import json
from llm_proxy import compact_repeated_reads


class SourceIndexTests(TestCase):
    def test_direct_callers_and_dependencies(self):
        idx = SourceIndex({'src/App.jsx': "import Card from './Card'; <Card item={x} />",
                           'src/Card.jsx': 'export default function Card() {}',
                           'src/Other.jsx': 'const unrelated = 1;'})
        self.assertEqual(idx.related(['src/Card.jsx']), {'src/App.jsx', 'src/Card.jsx'})
        self.assertIn('Card(item)', idx.render(['src/Card.jsx']))
        self.assertNotIn('Other.jsx', idx.render(['src/Card.jsx']))
        self.assertLessEqual(len(idx.render(['src/Card.jsx'], 80)), 80)

    def test_versions_change_with_content(self):
        self.assertNotEqual(SourceIndex({'a': 'x'}).versions, SourceIndex({'a': 'y'}).versions)

    def test_transitive_callers(self):
        idx = SourceIndex({'a.js': "import x from './b.js'", 'b.js': "import x from './c.js'", 'c.js': ''})
        self.assertEqual(idx.affected({'c.js'}), {'a.js', 'b.js', 'c.js'})

    def test_generic_timeouts_do_not_merge_known_different_features(self):
        failure = SimpleNamespace(message='Timeout 30000ms exceeded', action_errors=[])
        self.assertEqual(failure_groups({'a': [failure], 'b': [failure]}, {'a': {'A.jsx'}, 'b': {'B.jsx'}}), [['a'], ['b']])

    def test_unknown_timeouts_are_not_a_shared_cause(self):
        failure = SimpleNamespace(message='Timeout at helpers.ts:122', action_errors=[])
        self.assertEqual(failure_groups({'a': [failure], 'b': [failure]}, {}), [['a'], ['b']])
        # Independent groups can still share one budgeted turn, without adding rounds.
        self.assertEqual(select_repair_groups([['a'], ['b']], {}, 1), ['a', 'b'])

    def test_concrete_shared_runtime_error_merges_features(self):
        failure = SimpleNamespace(message='TypeError: note.tags.map is not a function', action_errors=[])
        self.assertEqual(failure_groups({'a': [failure], 'b': [failure]}, {'a': {'A.jsx'}, 'b': {'B.jsx'}}), [['a', 'b']])

    def test_identical_accessibility_locator_merges_downstream_failures(self):
        first = SimpleNamespace(message='Timeout', action_errors=[
            "waiting for getByRole('button', { name: /my account/i }).first()"])
        last = SimpleNamespace(message='Timeout', action_errors=[
            "waiting for getByRole('button', { name: /my account/i }).last()"])
        self.assertEqual(
            failure_groups({'checkout': [first], 'address': [last]},
                           {'checkout': {'Checkout.jsx'}, 'address': {'Address.jsx'}}),
            [['address', 'checkout']])

    def test_different_accessibility_locators_stay_separate(self):
        account = SimpleNamespace(message='Timeout', action_errors=[
            "waiting for getByRole('button', { name: /my account/i }).first()"])
        home = SimpleNamespace(message='Timeout', action_errors=[
            "waiting for getByRole('button', { name: /home/i }).first()"])
        self.assertEqual(
            failure_groups({'account': [account], 'home': [home]}, {}),
            [['account'], ['home']])

    def test_group_coverage_fits_existing_repair_rounds(self):
        groups = [[str(i)] for i in range(7)]
        visits = {}
        self.assertEqual(select_repair_groups(groups, visits, 3), ['0', '1', '2'])
        self.assertEqual(select_repair_groups(groups, visits, 2), ['3', '4', '5', '6'])
        self.assertEqual(select_repair_groups(groups, visits, 1), [str(i) for i in range(7)])

    def test_regression_scheduler_escalates_shared_or_unknown_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('a.spec.ts', 'b.spec.ts'):
                (root / name).write_text('')
            flow = object.__new__(main.Flow)
            flow.tests_dir = root
            flow.spec_map = {'a': ['a.spec.ts'], 'b': ['b.spec.ts']}
            flow.repair_source_index = Mock(return_value=SourceIndex({'A.jsx': '', 'B.jsx': ''}))
            flow.requirement_source_targets = Mock(return_value={'a': {'A.jsx'}, 'b': {'B.jsx'}})
            flow.test_verdict = {'a': True, 'b': True}
            self.assertEqual(flow.affected_regression_specs({'A.jsx'}, ['a.spec.ts']), [])
            self.assertEqual(flow.affected_regression_specs({'backend/store.js'}, ['a.spec.ts']), ['a.spec.ts', 'b.spec.ts'])
            self.assertEqual(flow.affected_regression_specs({'unknown.js'}, []), ['a.spec.ts', 'b.spec.ts'])
            self.assertEqual(flow.affected_regression_specs(set(), []), [])
            flow.spec_map['future'] = ['future.spec.ts']
            (root / 'future.spec.ts').write_text('')
            flow.requirement_source_targets.return_value['future'] = set()
            self.assertEqual(flow.affected_regression_specs({'backend/store.js'}, ['a.spec.ts']),
                             ['a.spec.ts', 'b.spec.ts'])
            self.assertEqual(flow.affected_regression_specs({'A.jsx'}, ['a.spec.ts']), [])
            flow.test_verdict['b'] = False
            self.assertEqual(flow.affected_regression_specs({'backend/store.js'}, ['a.spec.ts']), [])
            flow.test_verdict = {'b': True}
            self.assertEqual(flow.affected_regression_specs({'backend/store.js'}, ['a.spec.ts']),
                             ['a.spec.ts', 'b.spec.ts'])

    def test_repair_memory_invalidates_on_source_or_dependency_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'frontend').mkdir()
            source = root / 'frontend/a.js'
            source.write_text('const a=1;')
            flow = object.__new__(main.Flow)
            flow.output_dir = root
            flow.last_codegen_written = ['frontend/a.js']
            prompt = '--- frontend/a.js ---\nconst a=1;\n'
            flow.remember_repair('suite repair', prompt, 'applied')
            self.assertIn('not yet measured', flow.repair_memory_context(prompt))
            (root / 'frontend/package-lock.json').write_text('{}')
            self.assertEqual(flow.repair_memory_context(prompt), '')

    def test_overlapping_read_compaction_keeps_latest_and_distinct_lines(self):
        messages = []
        for number, start, end in ((1, 2, 8), (2, 1, 10)):
            messages.extend([{'role': 'assistant', 'tool_calls': [{'id': str(number), 'function': {
                'name': 'read_file', 'arguments': json.dumps({'path': 'a.js', 'start_line': start, 'end_line': end})}}]},
                {'role': 'tool', 'tool_call_id': str(number), 'content': '\n'.join(f'{i}│ ' + 'x' * 30 for i in range(start, end + 1))}])
        result = json.loads(compact_repeated_reads(json.dumps({'messages': messages}).encode()))
        self.assertIn('omitted', result['messages'][1]['content'])
        self.assertEqual(result['messages'][3], messages[3])
