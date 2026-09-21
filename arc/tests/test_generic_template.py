"""The shared scaffold is infrastructure, not a domain solution."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

import main as m
from generic_template import install_generic_template


class GenericTemplateTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_fresh_and_upgrade_contract_preserves_edits_and_deletions(self):
        install_generic_template(self.root, m.BUNDLE_DIR, 34123, [])
        helper = str(self.root / 'backend/lib/collection.js')
        script = """
const assert = require('node:assert/strict');
const {collection} = require(process.argv[1]);
const initial = [{id:'a', title:'Initial'}, {id:'b', title:'Removable'}];
const first = collection('entries', {initial});
assert.equal(first.all().length, 2);
first.patch('a', {title:'User edit'});
first.remove('b');
// A changed fallback must not overwrite persisted values or restore deletion.
assert.deepEqual(collection('entries', {initial:[...initial, {id:'c'}]}).all(),
                 [{id:'a', title:'User edit'}]);
const migrations = [{id:'add-c', up(data) { data.items.push({id:'c', title:'New requirement'}); }}];
const upgraded = collection('entries', {initial, migrations});
assert.deepEqual(upgraded.all(), [{id:'a', title:'User edit'}, {id:'c', title:'New requirement'}]);
upgraded.remove('c');
assert.deepEqual(collection('entries', {initial, migrations}).all(), [{id:'a', title:'User edit'}]);
"""
        subprocess.run(['node', '-e', script, helper], check=True, timeout=10, capture_output=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_installs_only_missing_generic_files_and_fills_ports(self):
        files = install_generic_template(self.root, m.BUNDLE_DIR, 34123, [34124, 34125])
        self.assertEqual(files, ["frontend/package.json", "backend/server.js", "backend/lib/store.js", "backend/lib/collection.js",
                                 "backend/lib/errors.js", "backend/lib/query.js",
                                 "frontend/build.mjs", "frontend/vite.config.mjs",
                                 "frontend/src/index.html", "frontend/src/app.js", "frontend/src/style.css",
                                 "frontend/src/shared/dom.js", "frontend/src/shared/request.js",
                                 "frontend/src/shared/router.js"])
        server = (self.root / "backend/server.js").read_text()
        self.assertIn("process.env.PORT || 34123", server)
        self.assertIn("[34124, 34125]", server)
        self.assertNotIn("__ARC_", server)
        self.assertEqual(install_generic_template(self.root, m.BUNDLE_DIR, 1, []), [])
        self.assertIn("34123", (self.root / "backend/server.js").read_text())

    def test_prepare_build_installs_scaffold_only_for_fresh_codegen(self):
        (self.root / "api.spec.ts").write_text("const base = 'http://localhost:34124';\n")
        flow = m.Flow(argparse.Namespace(web_port=34123), self.root, self.root)
        flow.codegen_mode = Mock(return_value=True)
        flow.app_design = Mock()
        flow.commit = Mock(return_value=True)
        flow.head = lambda: "scaffold-sha"
        with patch.dict(os.environ, {"OCTOS_ARC_GENERIC_TEMPLATE": "1"}):
            flow.prepare_build({"id": "ROOT"}, [{"id": "A"}])
        self.assertTrue(flow.generic_template_installed)
        self.assertTrue((self.root / "backend/server.js").exists())
        prompt = flow.codegen_implement_prompt({"id": "A", "description": "Create a page"}, "page.goto('/')")
        self.assertIn("Shared task-neutral files already exist", prompt)
        self.assertIn("backend/routes/*.js", prompt)
        self.assertIn("require('../lib/store')", prompt)
        self.assertIn("Express 5 entry", prompt)
        self.assertIn('build is "node build.mjs"', prompt)
        self.assertEqual(flow.codegen_ports_clause(), "")  # installed server already binds 34124
        self.assertIn("backend/server.js", m.quoted_paths(prompt))
        self.assertNotIn("backend/lib/store.js", m.quoted_paths(prompt))
        self.assertNotIn("backend/lib/collection.js", m.quoted_paths(prompt))
        self.assertNotIn("backend/lib/errors.js", m.quoted_paths(prompt))
        self.assertIn("transact(items => result)", prompt)
        self.assertIn("HttpError(status,message)", prompt)
        self.assertNotIn("frontend/build.mjs", m.quoted_paths(prompt))
        self.assertNotIn("frontend/vite.config.mjs", m.quoted_paths(prompt))
        self.assertIn("frontend/src/index.html", m.quoted_paths(prompt))
        self.assertNotIn("frontend/src/shared/dom.js", m.quoted_paths(prompt))
        requoted = flow.codegen_implement_prompt({"id": "A", "description": "Create a page"}, "page.goto('/')",
                                                  must_include={"backend/lib/store.js"})
        self.assertIn("backend/lib/store.js", m.quoted_paths(requoted))
        store = self.root / "backend/lib/store.js"
        store.write_text(store.read_text() + "\n// application-specific extension\n")
        changed = flow.codegen_implement_prompt({"id": "A", "description": "Create a page"}, "page.goto('/')")
        self.assertIn("backend/lib/store.js", m.quoted_paths(changed))
        build = self.root / "frontend/build.mjs"
        build.write_text(build.read_text() + "\n// application-specific build extension\n")
        changed = flow.codegen_implement_prompt({"id": "A", "description": "Create a page"}, "page.goto('/')")
        self.assertIn("frontend/build.mjs", m.quoted_paths(changed))
        flow.commit.assert_called_once()

    def test_prepare_build_leaves_partial_existing_application_alone(self):
        (self.root / "backend").mkdir()
        (self.root / "backend/server.js").write_text("// user entry\n")
        flow = m.Flow(argparse.Namespace(web_port=34123), self.root, self.root)
        flow.codegen_mode = Mock(return_value=True)
        flow.app_design = Mock()
        flow.head = lambda: "existing-sha"
        with patch.dict(os.environ, {"OCTOS_ARC_GENERIC_TEMPLATE": "1"}):
            flow.prepare_build({"id": "ROOT"}, [{"id": "A"}])
        self.assertFalse(flow.generic_template_installed)
        self.assertEqual((self.root / "backend/server.js").read_text(), "// user entry\n")
        self.assertFalse((self.root / "backend/lib").exists())
        self.assertFalse((self.root / "frontend/build.mjs").exists())

    def _install_express(self):
        m.write_codegen_manifests(self.root)
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=self.root / "backend",
                       check=True, capture_output=True, text=True, timeout=120)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_collection_shape_atomic_command_and_http_errors_are_task_neutral(self):
        install_generic_template(self.root, m.BUNDLE_DIR, 34123, [])
        script = r"""
const assert = require('node:assert/strict');
const {collection} = require('./backend/lib/collection');
const {HttpError} = require('./backend/lib/errors');
const fs = require('node:fs');
const shape = row => ({flags: [], ...row});
assert.throws(() => collection('bad-shape', {initial: {items: []}}), /initial must be an array/);
assert.equal(fs.existsSync('backend/data/bad-shape.json'), false);
const rows = collection('records', {initial: [{id: 'a'}], normalize: shape});
assert.deepEqual(rows.get('a'), {id: 'a', flags: []});
assert.equal(fs.existsSync('backend/data/records.json'), false, 'read normalization is not a migration');
assert.deepEqual(rows.create({id: 'b'}), {id: 'b', flags: []});
assert.deepEqual(rows.patch('b', {label: 'two'}), {id: 'b', flags: [], label: 'two'});
assert.equal(rows.transact(items => { items[0].flags.push('x'); items[1].flags.push('y'); return 2; }), 2);
assert.deepEqual(rows.all(), [
  {id: 'a', flags: ['x']}, {id: 'b', flags: ['y'], label: 'two'}
]);
assert.throws(() => rows.transact(items => { items.push({id: 'a'}); }), /unique ids/);
assert.throws(() => rows.transact(async () => {}), /synchronous/);
assert.deepEqual(rows.all(), [
  {id: 'a', flags: ['x']}, {id: 'b', flags: ['y'], label: 'two'}
]);
assert.throws(() => collection('invalid', {normalize: row => ({...row, id: 'other'})}).create({id: 'a'}), /preserve/);
assert.equal(rows.remove('a'), true);
assert.deepEqual(rows.all(), [{id: 'b', flags: ['y'], label: 'two'}]);
assert.equal(new HttpError(409, 'conflict').status, 409);
assert.throws(() => new HttpError(500, 'secret'), /400..499/);
"""
        result = subprocess.run(["node", "-e", script], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stored = json.loads((self.root / "backend/data/records.json").read_text())
        self.assertEqual(stored["items"], [{"id": "b", "flags": ["y"], "label": "two"}])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_request_json_exposes_plain_error_message_and_status(self):
        install_generic_template(self.root, m.BUNDLE_DIR, 34123, [])
        m.write_codegen_manifests(self.root)
        script = r"""
import assert from 'node:assert/strict';
import {requestJson} from './frontend/src/shared/request.js';
globalThis.fetch = async () => new Response(JSON.stringify({error: 'invalid input'}),
  {status: 422, headers: {'Content-Type': 'application/json'}});
await assert.rejects(requestJson('/api/items'), error =>
  error.message === 'invalid input' && error.status === 422);
globalThis.fetch = async () => new Response(JSON.stringify({items: []}),
  {status: 200, headers: {'Content-Type': 'application/json'}});
assert.deepEqual(await requestJson('/api/items'), {items: []});
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 to run npm-backed scaffold tests")
    def test_server_routes_static_pages_and_store_persists_without_domain_seed(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        install_generic_template(self.root, m.BUNDLE_DIR, port, [])
        self._install_express()
        dist = self.root / "frontend/dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<main>generic home</main>")
        (dist / "about.html").write_text("<main>about</main>")
        routes = self.root / "backend/routes"
        routes.mkdir()
        (routes / "health.js").write_text(
            "module.exports = app => {"
            "app.get('/api/health',(req,res)=>res.json({ok:true}));"
            "app.post('/api/echo',(req,res)=>res.json(req.body));"
            "app.get('/api/rejected',()=>{throw new (require('../lib/errors').HttpError)(422,'invalid input')}); };\n")
        env = dict(os.environ, PORT=str(port), ARC_EXTRA_PORTS="0")
        process = subprocess.Popen(["node", str(self.root / "backend/server.js")], cwd=self.root,
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.2) as response:
                        self.assertIn("generic home", response.read().decode())
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.05)
            else:
                self.fail("generic server did not start")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/about") as response:
                self.assertIn("about", response.read().decode())
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as response:
                self.assertEqual(json.load(response), {"ok": True})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/rejected")
            self.assertEqual(error.exception.code, 422)
            self.assertEqual(json.load(error.exception), {"error": "invalid input"})
            error.exception.close()
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/echo", b'{"value":2}',
                                             {"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(json.load(response), {"value": 2})
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/echo", b'{bad}',
                                             {"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        finally:
            process.terminate()
            process.wait(timeout=5)
        helper = str(self.root / "backend/lib/store.js")
        script = "const s=require(process.argv[1]);s.update('items',{items:[]},d=>{d.items.push('x')});console.log(JSON.stringify(s.read('items')));"
        output = subprocess.check_output(["node", "-e", script, helper], text=True)
        self.assertEqual(json.loads(output), {"items": ["x"]})
        self.assertEqual(json.loads((self.root / "backend/data/items.json").read_text()), {"items": ["x"]})
        collection_helper = str(self.root / "backend/lib/collection.js")
        script = ("const c=require(process.argv[1]).collection('records',{idKey:'key'});"
                  "c.create({key:'a',title:'One'});c.patch('a',{title:'Two'});"
                  "console.log(JSON.stringify([c.get('a'),c.remove('a'),c.all()]));")
        output = subprocess.check_output(["node", "-e", script, collection_helper], text=True)
        self.assertEqual(json.loads(output), [{"key": "a", "title": "Two"}, True, []])
        script = ("const make=require(process.argv[1]).collection;"
                  "const c=make('seeded',{initial:[{id:'first'}]});c.remove('first');"
                  "console.log(JSON.stringify(make('seeded',{initial:[{id:'first'}]}).all()));")
        output = subprocess.check_output(["node", "-e", script, collection_helper], text=True)
        self.assertEqual(json.loads(output), [], "persisted deletion must not reseed on a later read")

    @unittest.skipUnless(shutil.which("node") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 to run npm-backed scaffold tests")
    def test_listens_on_separate_extra_port_when_required(self):
        ports = []
        while len(ports) < 2:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
                if port not in ports:
                    ports.append(port)
        install_generic_template(self.root, m.BUNDLE_DIR, ports[0], [ports[0], ports[1]])
        self._install_express()
        dist = self.root / "frontend/dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("two ports")
        env = dict(os.environ, PORT=str(ports[0]))
        env.pop("ARC_EXTRA_PORTS", None)
        process = subprocess.Popen(["node", str(self.root / "backend/server.js")], cwd=self.root,
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    for port in ports:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.2) as response:
                            self.assertEqual(response.read(), b"two ports")
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.05)
            else:
                self.fail("both template ports did not start")
        finally:
            process.terminate()
            process.wait(timeout=5)

    @unittest.skipUnless(shutil.which("node") and os.environ.get("ARC_TEST_NPM_INTEGRATION"),
                         "Set ARC_TEST_NPM_INTEGRATION=1 to run npm-backed scaffold tests")
    def test_opt_in_spa_fallback_serves_deep_links_but_not_api_or_missing_assets(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        install_generic_template(self.root, m.BUNDLE_DIR, port, [])
        self._install_express()
        manifest = self.root / 'frontend/package.json'
        data = json.loads(manifest.read_text())
        data['arc'] = {'spa': True}
        manifest.write_text(json.dumps(data))
        dist = self.root / 'frontend/dist'
        dist.mkdir(parents=True)
        (dist / 'index.html').write_text('<main>SPA entry</main>')
        (dist / 'about.html').write_text('<main>Real about page</main>')
        env = dict(os.environ, PORT=str(port), ARC_EXTRA_PORTS='0')
        local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        process = subprocess.Popen(['node', str(self.root / 'backend/server.js')], cwd=self.root,
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            last_error = None
            for _ in range(40):
                try:
                    navigation = urllib.request.Request(f'http://127.0.0.1:{port}/archive',
                                                        headers={'Accept': 'text/html'})
                    with local.open(navigation, timeout=0.2) as response:
                        self.assertIn('SPA entry', response.read().decode())
                    break
                except (OSError, urllib.error.URLError) as error:
                    last_error = error
                    time.sleep(0.05)
            else:
                self.fail(f'SPA server did not serve /archive: {last_error}; process={process.poll()}')
            with local.open(urllib.request.Request(f'http://127.0.0.1:{port}/about',
                                                   headers={'Accept': 'text/html'})) as response:
                self.assertIn('Real about page', response.read().decode())
            for path in ('/api/unknown', '/missing.js'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    local.open(f'http://127.0.0.1:{port}{path}')
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
