"""The submission adapter gets suites exclusively through the command interface."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from main import Flow
from octos_tests import MissingTestSuiteError, generate_test_suite, project_destination


ROOT = Path(__file__).resolve().parents[1]


class OctosCommandTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_real_command_accepts_an_arbitrary_task_without_source_manifests(self):
        binary = self.root / 'octos'
        binary.write_text(f'#!{sys.executable}\n' + '''import json, sys
from pathlib import Path
assert sys.argv[1:3] == ['arc', 'generate-test-suite']
destination = Path(sys.argv[sys.argv.index('--output-dir') + 1])
destination.mkdir(parents=True)
(destination/'REQ-1.spec.ts').write_text('command supplied test')
(destination/'request.json').write_text(json.dumps(sys.argv[1:]))
print(json.dumps({'trusted': True, 'name': 'arbitrary-command-task'}))
''')
        binary.chmod(0o755)
        tree = {'name': 'Inventory workspace', 'id': 'custom-inventory'}
        source = self.root / 'input with spaces' / 'requirements.yaml'
        directory, receipt = generate_test_suite(str(binary), tree, self.root, requirements_path=source)
        self.assertEqual(receipt, {'trusted': True, 'name': 'arbitrary-command-task'})
        self.assertEqual((directory/'REQ-1.spec.ts').read_text(), 'command supplied test')
        self.assertFalse((directory/'suite-origin.json').exists())
        request = json.loads((directory/'request.json').read_text())
        prompt = request[request.index('--prompt') + 1]
        self.assertIn('For task "Inventory workspace custom-inventory"', prompt)
        self.assertIn(str(source), prompt)
        second, _ = generate_test_suite(str(binary), tree, self.root, 'explicit-task')
        self.assertEqual(second, self.root/'derived-tests-2')
        request = json.loads((second/'request.json').read_text())
        self.assertIn('For task "explicit-task"', request[request.index('--prompt') + 1])
        self.assertTrue((directory/'REQ-1.spec.ts').is_file())

    def test_unavailable_or_unreadable_command_returns_no_suite(self):
        for response in ('not json', 'null', '[]', '{"trusted":false}'):
            with self.subTest(response=response), patch('octos_tests.subprocess.run',
                    return_value=Mock(returncode=0, stdout=response)):
                self.assertIsNone(generate_test_suite('octos', {}, self.root))
        for error in (FileNotFoundError('octos'), subprocess.TimeoutExpired('octos', 30)):
            with self.subTest(error=type(error).__name__), patch('octos_tests.subprocess.run', side_effect=error):
                self.assertIsNone(generate_test_suite('octos', {}, self.root))

    def test_official_specs_skip_octos_generation(self):
        existing = self.root/'provided-tests'
        existing.mkdir()
        (existing/'REQ-1.spec.ts').write_text('provided test')
        tree = {'id': 'ROOT', 'name': 'Inventory', 'children': [{'id': 'REQ-1'}]}
        flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root/'requirements')
        flow.original_requirement_tree = tree
        flow.metric = Mock()
        with patch('main.find_octos', return_value='octos'), \
                patch('main.locate_acceptance_tests', return_value=existing), \
                patch('octos_tests.generate_test_suite', side_effect=AssertionError('Should not generate')) as generate:
            flow.prepare_test_spec_source(tree, tree['children'])
        generate.assert_not_called()
        self.assertEqual(flow.tests_dir, existing)
        self.assertEqual(flow.spec_map['REQ-1'], ['REQ-1.spec.ts'])
        self.assertTrue(flow.test_specs_trusted)
        self.assertIsNone(flow.layered)

    def test_missing_specs_and_failed_octos_generation_stops_before_codegen(self):
        tree = {'id': 'ROOT', 'name': 'unknown task', 'children': [{'id': 'REQ-1'}]}
        flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root/'requirements')
        flow.original_requirement_tree = tree
        with patch('main.locate_acceptance_tests', return_value=None), \
                patch('main.find_octos', return_value='octos'), \
                patch('octos_tests.generate_test_suite', return_value=None) as generate:
            with self.assertRaisesRegex(RuntimeError, 'No official acceptance specs'):
                flow.prepare_test_spec_source(tree, tree['children'])
        generate.assert_called_once()

    def test_octos_suite_must_cover_every_requirement_node(self):
        tree = {'id': 'ROOT', 'name': 'task', 'children': [{'id': 'REQ-1'}, {'id': 'REQ-2'}]}
        suite = self.root / 'generated'
        suite.mkdir()
        (suite / 'REQ-1.spec.ts').write_text("test('one', () => {});")
        flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root / 'requirements')
        flow.original_requirement_tree = tree
        flow.metric = Mock()
        flow.adopt_frozen_business = Mock()
        with patch('main.locate_acceptance_tests', return_value=None), \
                patch('main.find_octos', return_value='octos'), \
                patch('octos_tests.generate_test_suite', return_value=(suite, {'trusted': True})):
            with self.assertRaisesRegex(RuntimeError, 'REQ-2'):
                flow.prepare_test_spec_source(tree, tree['children'])
        flow.adopt_frozen_business.assert_not_called()

    def test_missing_suite_exits_without_starting_codegen(self):
        node = {'id': 'REQ-1', 'type': 'ATOMIC', 'description': 'A feature'}
        tree = {'id': 'ROOT', 'children': [node]}
        flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root / 'requirements')
        runtime = Mock()
        runtime.events = Mock()
        runtime.traceability = Mock()
        flow.resolve_seed_conflicts = Mock(return_value=tree)
        flow.classify_tree = Mock()
        flow.has_app = Mock(return_value=False)
        flow.prepare_test_spec_source = Mock(side_effect=MissingTestSuiteError('unsupported task'))
        flow.prepare_build = Mock()
        with patch('main.AgentRuntime.from_env', return_value=runtime), \
                patch('main.load_requirement_tree', return_value=tree), \
                patch('main.topo_order', return_value=[node]):
            self.assertEqual(flow.run(), 1)
        flow.prepare_build.assert_not_called()
        self.assertIn('unsupported task', (self.root / '.arc/terminal-state.json').read_text())

    def test_output_selection_skips_broken_symlinks(self):
        (self.root/'derived-tests').symlink_to(self.root/'missing')
        self.assertEqual(project_destination(self.root), self.root/'derived-tests-2')


class SubmissionBundleTests(unittest.TestCase):
    def test_real_bundle_omits_source_catalogue_and_imports_without_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            staging = Path(folder)
            arc = staging/'arc'
            arc.mkdir()
            script = (ROOT/'pack.sh').read_text()
            command = shlex.split(next(line for line in script.splitlines() if line.startswith('zip -qr ')))
            entries = command[3:command.index('-x')]
            for entry in entries + ['pack.sh', 'pack_kernel.py']:
                source = ROOT/entry
                if source.is_dir():
                    shutil.copytree(source, arc/entry, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                else:
                    shutil.copy2(source, arc/entry)
            # Leave development tools beside the packer to catch a future broad directory include.
            for name in ('embedded_suites.py', 'embedded_private_cases.py', 'github_test_setup.py'):
                (arc/name).write_text('raise AssertionError("development-only module")')
            env = {**os.environ, 'ARC_PACK_KERNEL': '0'}
            packed = subprocess.run(['sh', str(arc/'pack.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
            unpacked = staging/'unpacked'
            with zipfile.ZipFile(staging/'octos-arc-bundle.zip') as bundle:
                names = bundle.namelist()
                self.assertIn('octos_tests.py', names)
                self.assertFalse(any(Path(name).name.startswith('embedded_') for name in names))
                self.assertNotIn('github_test_setup.py', names)
                self.assertFalse(any(name.startswith('derived-tests/') for name in names))
                for name in names:
                    if name.endswith(('.py', '.md')):
                        contents = bundle.read(name).decode('utf8')
                        for marker in ('embedded_suites', 'embedded_reviewed', 'embedded_derived_tests',
                                       'SOURCE-REVIEWED INTERNAL DERIVED', 'Embedded reviewed suite'):
                            self.assertNotIn(marker, contents, name)
                bundle.extractall(unpacked)
            check = subprocess.run([sys.executable, '-I', '-c',
                'import sys; sys.path.insert(0, sys.argv[1]); '
                'import main, rust_engine, octos_tests, frozen_setup; '
                'assert "embedded_suites" not in sys.modules; '
                'from unittest.mock import patch, Mock; from pathlib import Path; '
                'ctx = patch("octos_tests.subprocess.run", return_value=Mock(returncode=0, stdout=\'{"trusted":true}\')); '
                'ctx.start(); result = octos_tests.generate_test_suite("octos", {"name":"custom"}, Path(sys.argv[2])); '
                'assert result[1]["trusted"] is True', str(unpacked), str(staging/'project')],
                cwd=unpacked, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == '__main__':
    unittest.main()
