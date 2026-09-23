import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
import main as m
from generic_template import install_generic_template
from web_stack import BUILD, CAPABILITIES, CORE, recommended_capabilities, stack_note
from frontend_assets import external_browser_assets
from acceptance import AppServer


class WebStackTests(unittest.TestCase):
    def test_reactive_state_contract_is_scoped_to_react_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_generic_template(root, m.BUNDLE_DIR, 34123, [], react=True)
            self.assertIn('persistence is not a React notification', stack_note(root))
            manifest = root / 'frontend/package.json'
            manifest.write_text('{}')
            self.assertEqual(stack_note(root), '')

    def test_fresh_large_app_defaults_to_local_plain_modules(self):
        flow = self.flow()
        flow.app_design = Mock()
        with patch.dict(os.environ, {"OCTOS_ARC_REACT": "0"}):
            flow.prepare_build({}, [{"id": str(i)} for i in range(34)])
        manifest = json.loads((self.root / "frontend/package.json").read_text())
        dependencies = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
        self.assertEqual(manifest["scripts"]["build"], "node build.mjs")
        self.assertTrue(manifest["arc"]["spa"])
        self.assertFalse(set(dependencies) & {"react", "react-dom", "radix-ui", "react-router"})
        self.assertTrue((self.root / "frontend/src/app.js").is_file())
        self.assertTrue((self.root / "frontend/src/shared/router.js").is_file())
        self.assertFalse((self.root / "frontend/src/main.jsx").exists())
        prompt = flow.codegen_implement_prompt({"id": "A", "description": "Create form"}, "page.goto('/')")
        self.assertNotIn("Fixed frontend baseline: React", prompt)
        self.assertNotIn("react-hook-form@", prompt)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def install(self):
        install_generic_template(self.root, m.BUNDLE_DIR, 3000, [], react=True,
                                 capabilities=["forms", "markdown"])
        m.write_codegen_manifests(self.root)

    def flow(self):
        flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        flow.commit = Mock()
        flow.head = Mock(return_value="baseline")
        flow.codegen_mode = Mock(return_value=True)
        return flow

    def test_fresh_large_flow_installs_pins_before_design_and_never_copy_builds(self):
        self.assertIn("React/Vite/Radix/React Router", m.APP_DESIGN_PROMPT)
        self.assertNotIn("without React or JSX", m.APP_DESIGN_PROMPT)
        self.assertNotIn("do not introduce React", m.ARCHITECTURE_CONTRACT)
        flow = self.flow()
        flow.app_design = Mock(side_effect=lambda *_: self.assertIn("Fixed frontend baseline", stack_note(self.root)))
        with patch.dict(os.environ, {"OCTOS_ARC_REACT": "1"}):
            flow.prepare_build({"description": "registration form", "children": []}, [{"id": str(i)} for i in range(3)])
        manifest = json.loads((self.root / "frontend/package.json").read_text())
        self.assertEqual(manifest["dependencies"], CORE)
        self.assertEqual(manifest["devDependencies"], BUILD)
        self.assertEqual(manifest["scripts"]["build"], "node build.mjs")
        self.assertTrue(manifest["arc"]["spa"])
        self.assertFalse((self.root / "frontend/src/shared/dom.js").exists())
        self.assertFalse((self.root / "frontend/src/shared/router.js").exists())
        prompt = flow.codegen_implement_prompt({"id": "A", "description": "Create form"}, "page.goto('/')")
        self.assertIn("Fixed frontend baseline", prompt)
        self.assertIn("below 18000 characters", prompt)
        self.assertIn("App.jsx owns routing", prompt)
        self.assertIn("unfinished until it is mounted", prompt)
        self.assertIn("does not prove styles are active", prompt)
        self.assertIn("onCheckedChange", prompt)
        self.assertIn("react-hook-form@", prompt)
        self.assertIn("--- frontend/src/App.jsx ---", prompt)
        self.assertNotIn("--- frontend/package-lock.json ---", prompt)
        self.assertFalse(flow.tiny_mode(100))

    def test_tiny_tree_and_existing_app_are_not_migrated(self):
        flow = self.flow()
        flow.app_design = Mock()
        flow.prepare_build({}, [{"id": "one"}])
        before = (self.root / "frontend/package.json").read_text()
        self.assertNotIn('"react"', before)
        flow.prepare_build({}, [{"id": str(i)} for i in range(20)])
        self.assertEqual((self.root / "frontend/package.json").read_text(), before)
        self.assertEqual(stack_note(self.root), "")

    def test_changed_or_older_adapter_is_not_given_the_current_return_contract(self):
        self.install()
        self.assertIn('NEITHER adds an {ok,value} envelope', stack_note(self.root))
        path = self.root / 'frontend/src/shared/interactions.jsx'
        path.write_text('// application-owned adapter with a different contract')
        self.assertNotIn('NEITHER adds an {ok,value} envelope', stack_note(self.root))
        path.write_text((m.BUNDLE_DIR / 'blueprints/react-interactions.jsx').read_text())
        request = self.root / 'frontend/src/shared/request.js'
        request.write_text('// application-owned response adapter with a different contract')
        self.assertNotIn('NEITHER adds an {ok,value} envelope', stack_note(self.root))

    def test_evolution_app_is_not_migrated(self):
        flow = self.flow()
        flow.app_design = Mock()
        flow.evolution = True
        flow.prepare_build({}, [{"id": str(i)} for i in range(20)])
        self.assertFalse((self.root / "frontend").exists())

    def test_scaffold_refuses_to_overwrite_existing_frontend(self):
        self.install()
        before = (self.root / "frontend/src/App.jsx").read_text()
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual((self.root / "frontend/src/App.jsx").read_text(), before)

    def test_precreated_directories_and_local_media_do_not_block_fresh_scaffold(self):
        src = self.root / "frontend/src"
        src.mkdir(parents=True)
        (src / "image.png").write_bytes(b"local media")
        self.install()
        self.assertEqual((src / "image.png").read_bytes(), b"local media")
        self.assertTrue((src / "App.jsx").exists())

    def test_baseline_lock_matches_pins_and_records_transitive_integrity(self):
        self.install()
        lock = json.loads((self.root / "frontend/package-lock.json").read_text())
        self.assertEqual(lock["packages"][""]["dependencies"], CORE)
        self.assertEqual(lock["packages"][""]["devDependencies"], BUILD)
        for name, version in {**CORE, **BUILD}.items():
            package = lock["packages"]["node_modules/" + name]
            self.assertEqual(package["version"], version)
            self.assertTrue(package["integrity"].startswith("sha512-"))

    def test_all_task_trees_have_domain_neutral_recommendations(self):
        rows = {}
        for path in sorted((m.BUNDLE_DIR / "tasks").glob("*/requirements.yaml")):
            tree = yaml.safe_load(path.read_text())
            rows[path.parent.name] = recommended_capabilities(tree)
        self.assertEqual(len(rows), 11)
        self.assertIn("calendar", rows["arc-bench-web--12306"])
        self.assertIn("calendar", rows["arc-bench-web--ctrip"])
        self.assertIn("richtext", rows["arc-bench-web--bookstack"])
        self.assertIn("markdown", rows["arc-bench-web--stackoverflow"])
        self.assertNotIn("richtext", rows["arc-bench-web--stackoverflow"])
        self.assertIn("documents", rows["arc-bench-web--prestashop"])
        self.assertNotIn("money", rows["arc-bench-web--keep"])
        self.assertEqual(recommended_capabilities({"id": "calendar", "scenarios": ["markdown payment"]}), ["styling"])
        self.assertEqual(recommended_capabilities({"description": "Homepage content and information"}), ["styling"])
        self.assertEqual(recommended_capabilities({"description": "日期选择与价格计算"}), ["styling", "calendar", "money"])

    def test_framework_sources_and_build_config_are_quoted_and_snapshotted_but_not_locks(self):
        self.install()
        src = self.root / "frontend/src"
        for name in ("View.tsx", "types.ts", "View.vue", "theme.scss", "module.mts"):
            (src / name).write_text("// feature implementation")
        for name in ("frontend/dist/compiled.js", "frontend/node_modules/lib/index.js", "frontend/coverage/a.js"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// do not quote")
        quoted = m.inline_sources(self.root)
        for name in ("App.jsx", "View.tsx", "types.ts", "View.vue", "theme.scss", "module.mts"):
            self.assertIn(name, quoted)
        self.assertNotIn("package-lock.json", quoted)
        self.assertNotIn("do not quote", quoted)
        snapshot = self.flow().snapshot_sources("A", 0)
        for name in ("src/App.jsx", "src/View.tsx", "vite.config.mjs", "package.json", "package-lock.json"):
            self.assertTrue((snapshot / "frontend" / name).exists(), name)
        self.assertFalse((snapshot / "frontend/node_modules").exists())

    def test_suite_invalid_replies_get_one_retry_then_tools(self):
        flow = self.flow()
        flow.suite_repair_prompt = Mock(return_value="repair prompt")
        flow.codegen_turn = Mock(return_value=(False, "codegen reply contained no <<<FILE>>> or <<<EDIT>>> blocks"))
        flow.last_codegen_written = []
        flow.last_codegen_refused = set()
        flow.turn = Mock(return_value=(True, "repaired with tools"))
        mode, _ = flow.suite_repair_turn("suite", ["A"], "failure", 300, tool_prompt="tools")
        self.assertEqual(mode, "tools")
        self.assertEqual(flow.codegen_turn.call_count, 2)
        self.assertIn("Previous reply was not applied", flow.codegen_turn.call_args.args[0])
        self.assertLess(flow.turn.call_args.args[1], 300)

    def test_suite_no_change_and_false_success_do_not_count_as_repair(self):
        for ok, response in [(True, "<<<NO CHANGE>>>"), (True, "reply without any applied file"), (False, "timeout")]:
            flow = self.flow()
            flow.suite_repair_prompt = Mock(return_value="repair prompt")
            flow.codegen_turn = Mock(return_value=(ok, response))
            flow.last_codegen_written = []
            flow.last_codegen_refused = set()
            flow.turn = Mock(return_value=(True, "done"))
            self.assertEqual(flow.suite_repair_turn("suite", ["A"], "failure", 300, tool_prompt="tools")[0], "tools")
            flow.codegen_turn.assert_called_once()

    def test_suite_retry_and_fallback_share_one_deadline(self):
        flow = self.flow()
        flow.suite_repair_prompt = Mock(return_value="repair prompt")
        flow.codegen_turn = Mock(return_value=(False, "timeout"))
        flow.last_codegen_written = []
        flow.last_codegen_refused = set()
        flow.turn = Mock(return_value=(True, "done"))
        with patch("main.time.monotonic", side_effect=[100, 101, 401, 402]):
            self.assertEqual(flow.suite_repair_turn("suite", ["A"], "failure", 300, tool_prompt="tools")[0], "unapplied")
        flow.turn.assert_not_called()


@unittest.skipUnless(os.environ.get("ARC_TEST_NPM_INTEGRATION") and shutil.which("npm"),
                     "Set ARC_TEST_NPM_INTEGRATION=1 for the pinned stack integration")
class PinnedStackIntegrationTests(unittest.TestCase):
    def test_core_and_optional_libraries_build_and_run_from_local_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            install_generic_template(root, m.BUNDLE_DIR, port, [], react=True,
                                     capabilities=list(CAPABILITIES))
            m.write_codegen_manifests(root)
            frontend = root / "frontend"
            result = subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=frontend,
                                    capture_output=True, text=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(["npm", "run", "build"], cwd=frontend,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for part in ("frontend", "backend"):
                path = root / part / "package.json"
                manifest = json.loads(path.read_text())
                for _, frontend_pins, backend_pins, _ in CAPABILITIES.values():
                    manifest.setdefault("dependencies", {}).update(frontend_pins if part == "frontend" else backend_pins)
                path.write_text(json.dumps(manifest))
            fixture = Path(__file__).parent / "fixtures"
            shutil.copy2(fixture / "framework-smoke.jsx", frontend / "src/App.jsx")
            (frontend / "src/style.css").write_text('@import "tailwindcss";\n')
            (frontend / "public").mkdir()
            (frontend / "public/local.txt").write_text("local public asset")
            server = AppServer(root, port, print)
            self.assertIsNone(server.build())
            self.assertEqual((frontend / "dist/local.txt").read_text(), "local public asset")
            self.assertEqual(external_browser_assets(frontend, built=True), [])
            self.assertTrue(any(".text-3xl" in p.read_text() for p in (frontend / "dist/assets").glob("*.css")))
            result = subprocess.run(["node", "-e",
                "const D=require('decimal.js');if(new D('0.1').plus('0.2').toString()!=='0.3')process.exit(1);"
                "const PDF=require('pdfkit');const p=new PDF();p.on('data',()=>{});p.text('Invoice');p.end();"],
                cwd=root / "backend", capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Browser checks are opt-in separately, so CI without Chromium still builds every pin.
            playwright_root = os.environ.get("ARC_TEST_PLAYWRIGHT_ROOT")
            if playwright_root:
                self.assertIsNone(server.start())
                try:
                    if Path('/proc/self/fd').is_dir():
                        for descriptor in Path('/proc/self/fd').iterdir():
                            try:
                                self.assertNotEqual(descriptor.resolve(strict=True), server.log_file)
                            except FileNotFoundError:
                                pass  # /proc iteration's own descriptor is already closed.
                    env = dict(os.environ, NODE_PATH=str(Path(playwright_root) / "node_modules"))
                    result = subprocess.run(["node", str(fixture / "framework-smoke.cjs"), str(port)],
                                            env=env, capture_output=True, text=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                finally:
                    server.stop()
