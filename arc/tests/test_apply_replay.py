import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ApplyReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'frontend').mkdir()
        (self.source / 'backend').mkdir()
        (self.source / 'frontend/a.js').write_text('const value = 1;\n')
        (self.source / 'backend/server.js').write_text('module.exports = {};\n')
        for args in [('init', '-q'), ('add', '.'),
                     ('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'initial')]:
            subprocess.run(['git', '-C', str(self.source), *args], check=True, capture_output=True)
        self.reply = self.root / 'reply.json'
        self.output = self.root / 'isolated'

    def apply(self, text, finish='stop'):
        self.reply.write_text(json.dumps({'choices': [{'finish_reason': finish, 'message': {'content': text}}]}))
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'apply-replay.py'),
            str(self.source), '--commit', 'HEAD', '--reply', str(self.reply), '--output', str(self.output)],
            capture_output=True, text=True)

    def test_changes_only_the_isolated_snapshot(self):
        result = self.apply('<<<EDIT frontend/a.js>>>\n<<<SEARCH>>>\nconst value = 1;\n'
                            '<<<REPLACE>>>\nconst value = 2;\n<<<END EDIT>>>')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('value = 2', (self.output / 'frontend/a.js').read_text())
        self.assertIn('value = 1', (self.source / 'frontend/a.js').read_text())
        self.assertFalse((self.output / '.git').exists())
        self.assertNotEqual(self.apply('<<<FILE backend/new.js>>>\nhello\n<<<END FILE>>>').returncode, 0)

    def test_truncated_reply_is_not_applied(self):
        self.assertNotEqual(self.apply('<<<FILE backend/new.js>>>\nhello\n<<<END FILE>>>', 'length').returncode, 0)
        self.assertFalse(self.output.exists())

    def test_anchor_failure_retains_unmodified_snapshot(self):
        result = self.apply('<<<EDIT frontend/a.js>>>\n<<<SEARCH>>>\nnot here\n'
                            '<<<REPLACE>>>\nchanged\n<<<END EDIT>>>')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('value = 1', (self.output / 'frontend/a.js').read_text())

    def test_rejects_paths_outside_application(self):
        self.assertNotEqual(self.apply('<<<FILE requirements/data.txt>>>\nhello\n<<<END FILE>>>').returncode, 0)
        self.assertFalse(self.output.exists())
