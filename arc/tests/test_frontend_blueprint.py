"""Optional frontend packages use one shared, task-neutral local build path."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import main as m
from frontend_assets import external_browser_assets
from generic_template import install_generic_template


@unittest.skipUnless(shutil.which("node"), "Node.js is required")
class FrontendBlueprintTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        m.write_codegen_manifests(self.root)
        install_generic_template(self.root, m.BUNDLE_DIR, 3000, [])
        self.frontend = self.root / "frontend"
        (self.frontend / "src").mkdir(exist_ok=True)

    def build(self):
        result = subprocess.run(["node", "build.mjs"], cwd=self.frontend, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_neutral_frontend_shell_and_optional_modules_are_local(self):
        index = (self.frontend / 'src/index.html').read_text()
        self.assertIn('type="module" src="/app.js"', index)
        self.assertIn('href="/style.css"', index)
        self.assertNotIn('https://', index)
        self.build()
        for rel in ('index.html', 'app.js', 'style.css', 'shared/dom.js',
                    'shared/request.js', 'shared/router.js'):
            self.assertTrue((self.frontend / 'dist' / rel).is_file(), rel)
        self.assertEqual(external_browser_assets(self.frontend, built=True), [])

    def package(self, **dependencies):
        manifest = json.loads((self.frontend / "package.json").read_text())
        manifest["dependencies"] = dependencies
        (self.frontend / "package.json").write_text(json.dumps(manifest))

    def bin(self, name, body):
        path = self.frontend / "node_modules/.bin" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env node\n" + body)
        path.chmod(0o755)

    def test_plain_copy_preserves_nested_files_and_removes_stale_dist(self):
        (self.frontend / "src/assets").mkdir()
        (self.frontend / "src/index.html").write_text("home")
        (self.frontend / "src/assets/style.css").write_text("body {color: blue}")
        (self.frontend / "dist").mkdir()
        (self.frontend / "dist/stale.html").write_text("stale")
        self.build()
        self.assertEqual((self.frontend / "dist/index.html").read_text(), "home")
        self.assertTrue((self.frontend / "dist/assets/style.css").is_file())
        self.assertFalse((self.frontend / "dist/stale.html").exists())

    def test_plain_build_copies_public_assets_to_dist_root(self):
        (self.frontend / "public").mkdir()
        (self.frontend / "public/icon.svg").write_text('<svg />')
        self.build()
        self.assertEqual((self.frontend / "dist/icon.svg").read_text(), '<svg />')

    def test_plain_copy_refuses_uncompiled_jsx(self):
        (self.frontend / "src/App.jsx").write_text('export default () => <main />;')
        result = subprocess.run(['node', 'build.mjs'], cwd=self.frontend, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('require a local bundler', result.stderr)

    def test_unchanged_build_blueprint_is_not_requoted_in_tool_prompts(self):
        self.assertNotIn("--- frontend/build.mjs ---", m.inline_sources(self.root))
        self.assertNotIn("--- frontend/vite.config.mjs ---", m.inline_sources(self.root))
        build = self.frontend / "build.mjs"
        build.write_text(build.read_text() + "\n// application-specific change\n")
        self.assertIn("--- frontend/build.mjs ---", m.inline_sources(self.root))

    def test_htmx_package_is_copied_to_a_local_browser_path(self):
        self.package(**{"htmx.org": "2.0.10"})
        (self.frontend / "src/index.html").write_text('<script src="/vendor/htmx.min.js"></script>')
        vendor = self.frontend / "node_modules/htmx.org/dist"
        vendor.mkdir(parents=True)
        (vendor / "htmx.min.js").write_text("window.htmx={};")
        self.build()
        self.assertEqual((self.frontend / "dist/vendor/htmx.min.js").read_text(), "window.htmx={};")

    def test_tailwind_source_uses_local_compiler(self):
        self.package(**{"tailwindcss": "4.0.0", "@tailwindcss/cli": "4.0.0"})
        (self.frontend / "src/index.html").write_text('<link rel="stylesheet" href="/assets/style.css">')
        (self.frontend / "src/assets").mkdir()
        (self.frontend / "src/assets/style.css").write_text('@import "tailwindcss";')
        self.bin("tailwindcss", "const fs=require('fs');const a=process.argv;"
                             "fs.writeFileSync(a[a.indexOf('-o')+1], '/* compiled locally */');\n")
        self.build()
        self.assertEqual((self.frontend / "dist/assets/style.css").read_text(), "/* compiled locally */")

    def test_vite_config_discovers_all_html_pages(self):
        self.package(vite="7.1.9")
        (self.frontend / "src/index.html").write_text("home")
        (self.frontend / "src/notes").mkdir()
        (self.frontend / "src/notes/list.html").write_text("notes")
        self.bin("vite", "const fs=require('fs');const path=require('path');"
                         "const u=require('url');import(u.pathToFileURL(path.resolve('vite.config.mjs')).href)"
                         ".then(({default:c})=>{fs.mkdirSync('dist',{recursive:true});"
                         "fs.writeFileSync('dist/entries.json',JSON.stringify(c.build.rollupOptions.input));});\n")
        self.build()
        entries = json.loads((self.frontend / "dist/entries.json").read_text())
        self.assertEqual(set(entries), {"index.html", "notes/list.html"})
        self.assertTrue(all(Path(value).is_file() for value in entries.values()))

    @unittest.skipUnless(shutil.which("npm") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 for the real Vite build")
    def test_real_vite_build_outputs_multiple_local_pages(self):
        self.package(vite="7.1.9")
        (self.frontend / "src/index.html").write_text('<main>home</main><script type="module" src="/app.js"></script>')
        (self.frontend / "src/about.html").write_text('<main>about</main><script type="module" src="/app.js"></script>')
        (self.frontend / "src/app.js").write_text("document.body.dataset.ready = 'yes';\n")
        result = subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=self.frontend,
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.build()
        self.assertIn("home", (self.frontend / "dist/index.html").read_text())
        self.assertIn("about", (self.frontend / "dist/about.html").read_text())
        self.assertTrue(list((self.frontend / "dist/assets").glob("*.js")))
        self.assertEqual(external_browser_assets(self.frontend, built=True), [])

    @unittest.skipUnless(shutil.which("npm") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 for the real Tailwind build")
    def test_real_tailwind_build_outputs_local_css(self):
        self.package(**{"tailwindcss": "4.1.13", "@tailwindcss/cli": "4.1.13"})
        (self.frontend / "src/index.html").write_text('<link rel="stylesheet" href="/style.css"><h1 class="text-3xl">Hi</h1>')
        (self.frontend / "src/style.css").write_text('@import "tailwindcss";\n')
        result = subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=self.frontend,
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.build()
        css = (self.frontend / "dist/style.css").read_text()
        self.assertIn(".text-3xl", css)
        self.assertNotIn('@import "tailwindcss"', css)
        self.assertEqual(external_browser_assets(self.frontend, built=True), [])

    @unittest.skipUnless(shutil.which("npm") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 for the real htmx build")
    def test_real_htmx_package_is_served_from_local_dist(self):
        self.package(**{"htmx.org": "2.0.10"})
        (self.frontend / "src/index.html").write_text('<script src="/vendor/htmx.min.js"></script>')
        result = subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=self.frontend,
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.build()
        self.assertGreater((self.frontend / "dist/vendor/htmx.min.js").stat().st_size, 1000)
        self.assertEqual(external_browser_assets(self.frontend, built=True), [])

    @unittest.skipUnless(shutil.which("npm") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 for the real React build")
    def test_real_react_plugin_builds_local_js(self):
        self.package(vite="7.1.9", react="19.1.1", **{"react-dom": "19.1.1", "@vitejs/plugin-react": "5.0.0"})
        (self.frontend / "src/index.html").write_text('<div id="root"></div><script type="module" src="/main.jsx"></script>')
        (self.frontend / "src/main.jsx").write_text(
            "import React from 'react';import{createRoot}from'react-dom/client';"
            "createRoot(document.getElementById('root')).render(<h1>Local React</h1>);\n")
        result = subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=self.frontend,
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.build()
        self.assertTrue(list((self.frontend / "dist/assets").glob("*.js")))
        self.assertEqual(external_browser_assets(self.frontend, built=True), [])


if __name__ == "__main__":
    unittest.main()
