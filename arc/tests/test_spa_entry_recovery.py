"""The known Vite nested-entry failure has a narrow, reversible repair."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from main import Flow


ERROR = ('frontend `npm run build` succeeded but the SPA entry '
         'frontend/dist/index.html is missing; emitted HTML: [\'dist/src/index.html\']')
BLUEPRINT = Path(__file__).parents[1] / 'blueprints'


class SpaEntryRecoveryTests(unittest.TestCase):
    def setup_flow(self, root, build_result=None):
        frontend = root / 'frontend'
        frontend.mkdir()
        (frontend / 'vite.config.mjs').write_bytes((BLUEPRINT / 'vite.config.mjs').read_bytes())
        build = frontend / 'build.mjs'
        build.write_text('// generated builder with wrong root\n')
        server = SimpleNamespace(build=Mock(return_value=build_result))
        flow = SimpleNamespace(output_dir=root, app_server=Mock(return_value=server),
                               commit=Mock(), metric=Mock())
        return flow, build, server

    def test_restores_blueprint_only_after_successful_trial_build(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, build, server = self.setup_flow(Path(temp))
            self.assertTrue(Flow.repair_spa_entry_from_blueprint(flow, ERROR))
            self.assertEqual(build.read_bytes(), (BLUEPRINT / 'frontend-build.mjs').read_bytes())
            server.build.assert_called_once()
            flow.commit.assert_called_once()

    def test_failed_trial_restores_generated_builder(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, build, _ = self.setup_flow(Path(temp), 'bundle still fails')
            original = build.read_bytes()
            self.assertFalse(Flow.repair_spa_entry_from_blueprint(flow, ERROR))
            self.assertEqual(build.read_bytes(), original)
            flow.commit.assert_not_called()

    def test_trial_exception_restores_generated_builder(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, build, server = self.setup_flow(Path(temp))
            original = build.read_bytes()
            server.build.side_effect = RuntimeError('build tool interrupted')
            self.assertFalse(Flow.repair_spa_entry_from_blueprint(flow, ERROR))
            self.assertEqual(build.read_bytes(), original)
            flow.commit.assert_not_called()

    def test_custom_vite_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, build, _ = self.setup_flow(Path(temp))
            (build.parent / 'vite.config.mjs').write_text('// customized\n')
            original = build.read_bytes()
            self.assertFalse(Flow.repair_spa_entry_from_blueprint(flow, ERROR))
            self.assertEqual(build.read_bytes(), original)
            flow.app_server.assert_not_called()


if __name__ == '__main__':
    unittest.main()
