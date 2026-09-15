import tempfile
import unittest
from pathlib import Path
from acceptance import RunSummary, TestOutcome, failure_source_context

class FailureContextTests(unittest.TestCase):
    def test_quotes_actual_helper_location_with_bounded_context(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'support').mkdir()
            (root/'support'/'helper.ts').write_text('\n'.join(f'operation_{n}();' for n in range(1, 21)))
            summary = RunSummary(results=[TestOutcome('submit later', False, 'failed', 10, file='form.spec.ts', location='helper.ts:10', line=10)])
            text = failure_source_context(summary, root)
            self.assertIn('support/helper.ts', text)
            self.assertIn('> 10: operation_10();', text)
            self.assertNotIn('operation_1();', text)
            self.assertLessEqual(len(failure_source_context(summary, root, 50)), 50)
            (root/'helper.ts').write_text('other')
            self.assertEqual(failure_source_context(summary, root), '')

    def test_does_not_quote_external_symlink(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            root = Path(d)
            target = Path(outside)/'helper.ts'
            target.write_text('external')
            (root/'helper.ts').symlink_to(target)
            summary = RunSummary(results=[TestOutcome('test', False, 'failed', 10, location='helper.ts:1', line=1)])
            self.assertEqual(failure_source_context(summary, root), '')
