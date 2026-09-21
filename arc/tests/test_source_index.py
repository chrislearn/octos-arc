from unittest import TestCase
from source_index import SourceIndex
from source_index import failure_groups
from types import SimpleNamespace
import tempfile
from pathlib import Path
from unittest.mock import Mock
import main


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

    def test_concrete_shared_runtime_error_merges_features(self):
        failure = SimpleNamespace(message='TypeError: note.tags.map is not a function', action_errors=[])
        self.assertEqual(failure_groups({'a': [failure], 'b': [failure]}, {'a': {'A.jsx'}, 'b': {'B.jsx'}}), [['a', 'b']])

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
            self.assertEqual(flow.affected_regression_specs({'A.jsx'}, ['a.spec.ts']), [])
            self.assertEqual(flow.affected_regression_specs({'backend/store.js'}, ['a.spec.ts']), ['a.spec.ts', 'b.spec.ts'])
            self.assertEqual(flow.affected_regression_specs({'unknown.js'}, []), ['a.spec.ts', 'b.spec.ts'])
            self.assertEqual(flow.affected_regression_specs(set(), []), [])
