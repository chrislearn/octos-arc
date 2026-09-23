import tempfile
import unittest
from pathlib import Path

from local_config import api_environment


class LocalConfigTests(unittest.TestCase):
    def config(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'api.txt'
            path.write_text(text)
            return api_environment(path)

    def test_both_assignment_styles_and_quoted_values(self):
        self.assertEqual(self.config('api_key: "test-key"\nbase_url=https://example.invalid/v1\nmodel=test'),
                         {'OPENAI_API_KEY': 'test-key', 'OPENAI_BASE_URL': 'https://example.invalid/v1', 'MODEL': 'test'})

    def test_optional_visual_model_from_local_test_config(self):
        config = self.config('api_key=secret\nbase_url=https://example.invalid/v1\n'
                             'model=test\nvisual_model=visual-test')
        self.assertEqual(config['VISUAL_MODEL'], 'visual-test')

    def test_shell_expressions_are_plain_data(self):
        self.assertEqual(self.config('api_key=$(do-not-run)\nbase_url=https://example.invalid')['OPENAI_API_KEY'],
                         '$(do-not-run)')

    def test_invalid_fields_never_echo_credentials(self):
        for text in ('unknown=secret-sentinel', 'api_key=secret-sentinel',
                     'api_key=secret-sentinel\napi_key=duplicate\nbase_url=https://example.invalid'):
            with self.assertRaises(ValueError) as result:
                self.config(text)
            self.assertNotIn('secret-sentinel', str(result.exception))
