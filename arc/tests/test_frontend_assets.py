import json
import shutil
import tempfile
import unittest
from pathlib import Path

from acceptance import AppServer
from frontend_assets import external_browser_assets


class FrontendAssetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "frontend/src").mkdir(parents=True)
        (self.root / "backend").mkdir()

    def test_rejects_remote_runtime_assets_but_allows_navigation_and_api_calls(self):
        src = self.root / "frontend/src"
        (src / "index.html").write_text(
            '<a href="https://example.com/help">Help</a>\n'
            '<script src="https://cdn.example.com/app.js"></script>\n'
            '<link rel="stylesheet" href="//cdn.example.com/style.css">\n'
            '<img src="https://cdn.example.com/photo.png">\n')
        (src / "app.css").write_text('@import "https://cdn.example.com/theme.css";\n')
        (src / "app.js").write_text("fetch('https://api.example.com/data');\nimport x from 'https://cdn.example.com/x.js';\n")
        hits = external_browser_assets(self.root / "frontend")
        self.assertEqual(len(hits), 5)
        self.assertFalse(any("example.com/help" in hit or "api.example.com" in hit for hit in hits))

    def test_local_assets_are_allowed(self):
        src = self.root / "frontend/src"
        (src / "index.html").write_text('<script src="/assets/app.js"></script><link rel="stylesheet" href="style.css">')
        (src / "app.css").write_text('@import "./theme.css";\n')
        (src / "app.js").write_text("import './components.js';\n")
        self.assertEqual(external_browser_assets(self.root / "frontend"), [])

    def test_framework_literal_assets_are_checked_without_blocking_api_or_links(self):
        src = self.root / "frontend/src"
        (src / "App.tsx").write_text(
            '<img src={"https://cdn.example.com/image.png"} />\n'
            '<a href="https://example.com/help">Help</a>\n'
            "fetch('https://api.example.com/data');\n")
        (src / "App.vue").write_text(
            '<template><img :src="\'https://cdn.example.com/vue.png\'" /></template>\n'
            '<style>@import "https://cdn.example.com/style.css";</style>')
        (src / "module.mts").write_text("import 'https://cdn.example.com/module.js';")
        hits = external_browser_assets(self.root / "frontend")
        self.assertTrue(any('image.png' in hit for hit in hits))
        self.assertTrue(any('vue.png' in hit for hit in hits))
        self.assertTrue(any('style.css' in hit for hit in hits))
        self.assertTrue(any('module.js' in hit for hit in hits))
        self.assertFalse(any('example.com/help' in hit or 'api.example.com' in hit for hit in hits))

    def test_compiled_js_assets_but_not_namespace_urls_are_checked(self):
        dist = self.root / "frontend/dist"
        dist.mkdir()
        (dist / "app.js").write_text('const ns="http://www.w3.org/2000/svg";x("img",{src:"https://cdn.example.com/a.png"});')
        self.assertEqual(len(external_browser_assets(self.root / "frontend", built=True)), 1)

    def test_lock_changes_invalidate_install_cache(self):
        frontend = self.root / "frontend"
        (frontend / "package.json").write_text('{"dependencies":{"react":"19.3.0"},"scripts":{"build":"vite build"}}')
        (self.root / "backend/package.json").write_text('{}')
        lock = frontend / "package-lock.json"
        lock.write_text('{"lockfileVersion":3}')
        calls = []
        server = AppServer(self.root, 3000, lambda _: None)
        def run(command, cwd, timeout):
            calls.append(command)
            if command[:2] == ['npm', 'install']:
                lock.write_text('{"lockfileVersion":3,"updated":true}')
            return 0, ''
        server._run = run
        self.assertIsNone(server.build())
        calls.clear()
        self.assertIsNone(server.build())
        self.assertEqual([cmd[:2] for cmd in calls], [['npm', 'run']])
        lock.write_text('{"lockfileVersion":3,"updated":false}')
        calls.clear()
        self.assertIsNone(server.build())
        self.assertEqual([cmd[:2] for cmd in calls], [['npm', 'install'], ['npm', 'run']])

    def test_build_refuses_source_or_built_cdn_assets(self):
        frontend = self.root / "frontend"
        (frontend / "package.json").write_text('{"scripts":{"build":"node build.js"}}')
        (self.root / "backend/package.json").write_text('{"scripts":{"start":"node server.js"}}')
        (frontend / "src/index.html").write_text('<script src="https://cdn.example.com/app.js"></script>')
        server = AppServer(self.root, 3000, lambda _: None)
        self.assertIn("external browser assets", server.build())
        (frontend / "src/index.html").write_text('<script src="/app.js"></script>')
        (frontend / "build.js").write_text(
            "const fs=require('fs');fs.writeFileSync('dist/index.html',"
            "'<link rel=\"stylesheet\" href=\"https://cdn.example.com/a.css\">');")
        self.assertIn("built frontend uses external browser assets", server.build())

    def test_local_install_includes_dev_dependencies_and_tracks_manifest_changes(self):
        frontend = self.root / "frontend"
        manifest = frontend / "package.json"
        manifest.write_text(json.dumps({"scripts": {"build": "vite build"},
                                        "devDependencies": {"vite": "1.0.0"}}))
        (self.root / "backend/package.json").write_text('{"scripts":{"start":"node server.js"}}')
        calls = []
        server = AppServer(self.root, 3000, lambda _: None)
        server._run = lambda command, cwd, timeout: (calls.append((command, cwd)) or (0, ""))
        self.assertIsNone(server.build())
        self.assertEqual([cmd[0][:2] for cmd in calls], [["npm", "install"], ["npm", "run"]])
        self.assertIn("--include=dev", calls[0][0])
        calls.clear()
        self.assertIsNone(server.build())
        self.assertEqual(len(calls), 1)  # unchanged manifest does not reinstall
        manifest.write_text(json.dumps({"scripts": {"build": "vite build"},
                                        "devDependencies": {"vite": "2.0.0"}}))
        calls.clear()
        self.assertIsNone(server.build())
        # A manifest-only declaration change can use the installed tree until
        # source actually imports the new package. A lock change still forces
        # installation immediately (covered above).
        self.assertEqual([cmd[0][:2] for cmd in calls], [["npm", "run"]])

    @unittest.skipUnless(shutil.which("npm"), "npm is required for the real frontend build check")
    def test_real_frontend_build_can_use_a_local_dev_dependency(self):
        tool = self.root / "bundle-tool"
        tool.mkdir()
        (tool / "package.json").write_text('{"name":"bundle-tool","version":"1.0.0","bin":{"bundle-tool":"cli.js"}}')
        (tool / "cli.js").write_text(
            "#!/usr/bin/env node\nconst fs=require('fs');"
            "fs.mkdirSync('dist',{recursive:true});"
            "fs.cpSync('src','dist',{recursive:true});\n")
        (tool / "cli.js").chmod(0o755)
        frontend = self.root / "frontend"
        (frontend / "src/index.html").write_text('<script src="/app.js"></script>')
        (frontend / "src/app.js").write_text("document.body.dataset.ready='yes';\n")
        (frontend / "package.json").write_text(json.dumps({"scripts": {"build": "bundle-tool"},
                                                           "devDependencies": {"bundle-tool": "file:../bundle-tool"}}))
        (self.root / "backend/package.json").write_text('{"scripts":{"start":"node server.js"}}')
        self.assertIsNone(AppServer(self.root, 3000, lambda _: None).build())
        self.assertTrue((frontend / "node_modules/.bin/bundle-tool").exists())
        self.assertEqual((frontend / "dist/app.js").read_text(), "document.body.dataset.ready='yes';\n")


if __name__ == "__main__":
    unittest.main()
