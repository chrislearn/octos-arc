"""Route registry, test hooks and resettable store shipped with the generic entry.

v10.0 sheet (819388a5f77b): an exact duplicate of a filters route across two
files was flagged as a fatal build error by a regex scan, three nodes and the
final suite measured 0/0 and the run shipped "as-is". The registry reports
the real Express route table with the owning file and line, and never stops
the server; the harness decides what a conflict costs.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import main as m
from generic_template import install_generic_template

NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is required")
class RouteRegistryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        install_generic_template(self.root, m.BUNDLE_DIR, 34123, [])
        (self.root / "backend/routes").mkdir()

    def node(self, script: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([NODE, "-e", script], cwd=self.root / "backend", capture_output=True, text=True,
                              timeout=20, env=dict(os.environ, **(env or {})))

    def fake_app_script(self, body: str) -> str:
        return ("const assert = require('node:assert/strict');\n"
                "const arc = require('./lib/arc');\n"
                "const calls = [];\n"
                "const app = {};\n"
                "for (const m of ['get','post','put','patch','delete','all','use']) "
                "app[m] = (...args) => { calls.push([m, ...args]); return app; };\n"
                "arc.trackRoutes(app);\n" + body)

    def test_should_report_exact_duplicate_route_with_owner_file_and_line(self):
        (self.root / "backend/routes/filters.js").write_text(
            "module.exports = app => {\n"
            "  app.post('/api/workbooks/:id/worksheets/:wsId/filters', (req, res) => res.end());\n"
            "};\n")
        (self.root / "backend/routes/workbooks.js").write_text(
            "module.exports = app => {\n"
            "  app.get('/api/workbooks', (req, res) => res.end());\n"
            "  app.post('/api/workbooks/:workbookId/worksheets/:sheet/filters', (req, res) => res.end());\n"
            "};\n")
        result = self.node(self.fake_app_script(
            "for (const f of ['filters','workbooks']) require('./routes/' + f)(app);\n"
            "const report = arc.routeReport();\n"
            "console.log(JSON.stringify(report));\n"))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(len(report["routes"]), 3)
        self.assertEqual(report["routes"][0]["file"], "backend/routes/filters.js")
        self.assertEqual(report["routes"][0]["line"], 2)
        self.assertEqual(len(report["conflicts"]), 1)
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["kind"], "duplicate")
        self.assertEqual((conflict["file"], conflict["line"]), ("backend/routes/workbooks.js", 3))
        self.assertEqual((conflict["owner_file"], conflict["owner_line"]), ("backend/routes/filters.js", 2))
        self.assertIn("already registered", conflict["message"])
        self.assertNotIn("literal path first", conflict["message"])

    def test_should_report_literal_route_shadowed_by_earlier_parameter_route(self):
        result = self.node(self.fake_app_script(
            "app.delete('/api/notes/:id', () => {});\n"
            "app.delete('/api/notes/trash', () => {});\n"
            "app.get('/api/notes/trash', () => {});\n"
            "app.get('/api/files/*path', () => {});\n"
            "app.get('/api/files/readme', () => {});\n"
            "console.log(JSON.stringify(arc.routeReport().conflicts));\n"))
        self.assertEqual(result.returncode, 0, result.stderr)
        conflicts = json.loads(result.stdout)
        self.assertEqual([(c["kind"], c["method"], c["path"]) for c in conflicts],
                         [("shadowed", "DELETE", "/api/notes/trash"), ("shadowed", "GET", "/api/files/readme")])
        self.assertIn("register it before", conflicts[0]["message"])

    def test_should_pass_calls_through_and_ignore_setting_getters(self):
        result = self.node(self.fake_app_script(
            "const handler = () => {};\n"
            "app.get('env');\n"
            "app.get('/api/a', handler);\n"
            "app.get(/^\\/regex$/, handler);\n"
            "assert.equal(calls.length, 3);\n"
            "assert.deepEqual(calls[1], ['get', '/api/a', handler]);\n"
            "console.log(JSON.stringify(arc.routeReport().routes.map(r => r.path)));\n"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["/api/a"])

    def test_should_dump_route_report_and_exit_without_listening(self):
        (self.root / "backend/routes/items.js").write_text(
            "module.exports = app => { app.get('/api/items', (q, s) => s.json([])); "
            "app.get('/api/items', (q, s) => s.json([])); };\n")
        dump = self.root / "routes.json"
        stub = self.root / "backend/node_modules/express"
        stub.mkdir(parents=True)
        (stub / "index.js").write_text(
            "function express() { const app = {disable() {}, use() {}, listen() { throw new Error('listened'); }};\n"
            "  for (const m of ['get','post','put','patch','delete','all']) app[m] = () => app; return app; }\n"
            "express.json = () => () => {}; express.urlencoded = () => () => {}; express.static = () => () => {};\n"
            "module.exports = express;\n")
        result = subprocess.run([NODE, "server.js"], cwd=self.root / "backend", capture_output=True, text=True,
                                timeout=20, env=dict(os.environ, ARC_ROUTE_DUMP=str(dump), PORT="1"))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(dump.read_text())
        self.assertEqual([c["kind"] for c in report["conflicts"]], ["duplicate"])
        self.assertEqual(report["routes"][0]["file"], "backend/routes/items.js")

    def test_should_mount_test_hooks_only_when_enabled(self):
        script = ("const arc = require('./lib/arc');\n"
                  "const paths = [];\n"
                  "const app = {post: (p) => paths.push('POST ' + p), get: (p) => paths.push('GET ' + p)};\n"
                  "arc.mountTestHooks(app);\n"
                  "console.log(JSON.stringify(paths));\n")
        off = self.node(script)
        on = self.node(script, {"ARC_TEST_HOOKS": "1"})
        self.assertEqual(json.loads(off.stdout), [])
        self.assertEqual(json.loads(on.stdout), ["POST /__arc/reset", "GET /__arc/routes"])


@unittest.skipUnless(NODE, "Node.js is required")
class ResettableStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        install_generic_template(self.root, m.BUNDLE_DIR, 34123, [])

    def test_should_keep_runtime_data_in_ARC_DATA_DIR_outside_the_worktree(self):
        data = self.root / "runtime-data"
        script = ("const {collection} = require('./lib/collection');\n"
                  "collection('notes', {initial: [{id: 'seed'}]}).create({id: 'mine'});\n")
        result = subprocess.run([NODE, "-e", script], cwd=self.root / "backend", capture_output=True, text=True,
                                timeout=20, env=dict(os.environ, ARC_DATA_DIR=str(data)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((data / "notes.json").read_text())["items"], [{"id": "seed"}, {"id": "mine"}])
        self.assertFalse((self.root / "backend/data").exists())

    def test_should_reset_to_seeds_replay_migrations_and_run_reset_hooks(self):
        script = r"""
const assert = require('node:assert/strict');
const store = require('./lib/store');
const {collection} = require('./lib/collection');
const migrations = [{id: 'add-b', up(data) { data.items.push({id: 'b'}); }}];
const notes = collection('notes', {initial: [{id: 'a'}], migrations});
notes.create({id: 'test-made'});
notes.remove('a');
const undo = new Map([['wb', ['step']]]);
store.onReset(() => undo.clear());
assert.throws(() => store.onReset('nope'), /function/);
store.reset();
assert.deepEqual(notes.all().map(n => n.id), ['a', 'b']);
assert.equal(undo.size, 0);
notes.create({id: 'again'});
store.reset();
assert.deepEqual(notes.all().map(n => n.id), ['a', 'b']);
"""
        data = self.root / "runtime-data"
        result = subprocess.run([NODE, "-e", script], cwd=self.root / "backend", capture_output=True, text=True,
                                timeout=20, env=dict(os.environ, ARC_DATA_DIR=str(data)))
        self.assertEqual(result.returncode, 0, result.stderr)


class TemplateInstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_should_install_runtime_helper_as_task_neutral_infrastructure(self):
        # backend/data stays tracked on purpose: apps that do not use lib/store still rely on
        # git to undo test writes between spec files; generic apps write to ARC_DATA_DIR.
        written = install_generic_template(self.root, m.BUNDLE_DIR, 34123, [])
        self.assertIn("backend/lib/arc.js", written)
        self.assertIn("backend/lib/arc.js", m.TASK_NEUTRAL_HELPERS)
        self.assertFalse((self.root / ".gitignore").exists())
        from generic_template import generic_entry_intact
        self.assertTrue(generic_entry_intact((self.root / "backend/server.js").read_text()))


if __name__ == "__main__":
    unittest.main()
