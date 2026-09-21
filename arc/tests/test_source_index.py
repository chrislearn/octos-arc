from unittest import TestCase
from source_index import SourceIndex


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
