"""Conservative scaffold checks catch failures a passing feature test can miss."""
import json
import tempfile
import unittest
from pathlib import Path

import main as m
from acceptance import AppServer
from web_checks import scaffold_issues


class ScaffoldChecksTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        m.write_codegen_manifests(self.root)
        from generic_template import install_generic_template
        install_generic_template(self.root, m.BUNDLE_DIR, 3000, [])
        routes = self.root / 'backend/routes'
        routes.mkdir()

    def test_detects_literal_route_shadowed_by_parameter_route(self):
        (self.root / 'backend/routes/notes.js').write_text(
            "module.exports = app => {\n"
            "app.delete('/api/notes/:id', (req, res) => res.end());\n"
            "app.delete('/api/notes/trash', (req, res) => res.end());\n"
            "};\n")
        issues = scaffold_issues(self.root)
        self.assertEqual(len(issues), 1)
        self.assertIn('DELETE /api/notes/trash is shadowed', issues[0])
        self.assertIn('notes.js:2', issues[0])
        error = AppServer(self.root, 3000, lambda _: None).build()
        self.assertIn('generic scaffold route checks failed', error)
        self.assertIn('DELETE /api/notes/trash', error)

    def test_literal_first_and_different_methods_are_safe(self):
        (self.root / 'backend/routes/notes.js').write_text(
            "app.delete('/api/notes/trash', handler);\n"
            "app.get('/api/notes/:id', handler);\n"
            "app.delete('/api/notes/:id', handler);\n")
        self.assertEqual(scaffold_issues(self.root), [])

    def test_spa_links_need_explicit_fallback_with_only_one_html_page(self):
        (self.root / 'frontend/src/index.html').write_text('<a href="/archive" data-route>Archive</a>')
        self.assertEqual(scaffold_issues(self.root), [], 'unused optional router helper is not an active SPA')
        (self.root / 'frontend/src/app.js').write_text("history.pushState(null, '', link.href);\n")
        self.assertIn('arc.spa=true', '\n'.join(scaffold_issues(self.root)))
        self.assertIn('arc.spa=true', AppServer(self.root, 3000, lambda _: None).build())
        manifest = self.root / 'frontend/package.json'
        data = json.loads(manifest.read_text())
        data['arc'] = {'spa': True}
        manifest.write_text(json.dumps(data))
        self.assertEqual(scaffold_issues(self.root), [])

    def test_multiple_real_pages_or_custom_entry_are_not_forced_into_spa(self):
        (self.root / 'frontend/src/index.html').write_text('<a href="/archive">Archive</a>')
        (self.root / 'frontend/src/app.js').write_text("history.pushState(null, '', '/archive');\n")
        (self.root / 'frontend/src/archive.html').write_text('<main>archive</main>')
        self.assertEqual(scaffold_issues(self.root), [])
        (self.root / 'frontend/src/archive.html').unlink()
        (self.root / 'backend/server.js').write_text('// custom entry')
        self.assertEqual(scaffold_issues(self.root), [])

    def test_unrelated_server_link_does_not_trigger_spa_guard(self):
        (self.root / 'frontend/src/index.html').write_text('<a href="/login">Login</a>')
        (self.root / 'frontend/src/app.js').write_text("history.pushState(null, '', '/?sort=recent');\n")
        self.assertEqual(scaffold_issues(self.root), [])

    def test_react_router_needs_spa_fallback_even_without_literal_html_links(self):
        (self.root / 'frontend/src/main.tsx').write_text(
            "import {BrowserRouter} from 'react-router'; export default () => <BrowserRouter />;")
        self.assertIn('arc.spa=true', '\n'.join(scaffold_issues(self.root)))
        (self.root / 'frontend/src/main.tsx').write_text(
            "import {HashRouter} from 'react-router'; export default () => <HashRouter />;")
        self.assertEqual(scaffold_issues(self.root), [])

    def test_detects_uncompiled_utility_classes_before_visual_acceptance(self):
        app = self.root / 'frontend/src/App.jsx'
        app.write_text('''export default function App() { return <main
          className="flex grid relative bg-white text-gray-700 border-gray-200 rounded-lg shadow-sm p-4 px-3 m-2 gap-3 items-center justify-between">
          <button className="hover:bg-gray-100 focus:ring-2">Save</button>
        </main>; }''')
        issues = scaffold_issues(self.root)
        self.assertIn('no active utility CSS', '\n'.join(issues))
        self.assertIn('tailwindcss/@tailwindcss/vite', '\n'.join(issues))
        self.assertIn('no active utility CSS', AppServer(self.root, 3000, lambda _: None).build())

    def test_utility_classes_are_valid_with_tailwind_or_explicit_css(self):
        app = self.root / 'frontend/src/App.jsx'
        classes = ('flex grid relative bg-white text-gray-700 border-gray-200 rounded-lg '
                   'shadow-sm p-4 px-3 m-2 gap-3 items-center justify-between')
        app.write_text(f'export default () => <main className="{classes}" />;')
        manifest = self.root / 'frontend/package.json'
        data = json.loads(manifest.read_text())
        data.setdefault('devDependencies', {}).update(
            {'tailwindcss': '4.3.3', '@tailwindcss/vite': '4.3.3'})
        manifest.write_text(json.dumps(data))
        (self.root / 'frontend/src/style.css').write_text('@import "tailwindcss";\n')
        self.assertEqual(scaffold_issues(self.root), [])

        data['devDependencies'].pop('tailwindcss')
        data['devDependencies'].pop('@tailwindcss/vite')
        manifest.write_text(json.dumps(data))
        (self.root / 'frontend/src/style.css').write_text(
            '\n'.join('.' + name + ' {}' for name in classes.split()))
        self.assertEqual(scaffold_issues(self.root), [])


if __name__ == '__main__':
    unittest.main()
