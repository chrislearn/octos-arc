"""Literal positives, real omissions and unsupported routing must differ."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from route_evidence import (frontend_route_index, frontend_route_evidence,
                            backend_route_evidence, runtime_backend_routes)


class RouteEvidenceTests(unittest.TestCase):
    def evidence(self, source, path):
        return frontend_route_evidence(frontend_route_index({'frontend/src/OrgRoutes.jsx': source}), path)

    def test_rerun_nested_routes_and_pathless_index(self):
        source = '''<Routes><Route element={<Layout title="}" />}>
          <Route path="/orgs/:org" element={<Org />}>
            <Route index element={<Overview />} />
            <Route element={<Teams />} path="teams" />
            <Route path="teams/:team" element={<Team />} />
            <Route path="people" element={<People />} />
            <Route path="/help" element={<Help />} />
          </Route></Route></Routes>'''
        for path in ('/orgs/:org', '/orgs/:org/teams', '/orgs/:org/teams/:id', '/orgs/:org/people', '/help'):
            with self.subTest(path=path):
                result = self.evidence(source, path)
                self.assertEqual(result['status'], 'present', result)
                self.assertEqual(result['sources'][0]['file'], 'frontend/src/OrgRoutes.jsx')
                self.assertIn('reachability unverified', result['scope'])
        self.assertEqual(self.evidence(source, '/orgs/:org/missing')['status'], 'proven_missing')

    def test_unknown_is_not_a_missing_route(self):
        for source in (
            '<Routes><Route path={root}><Route path="teams" /></Route></Routes>',
            '<Routes>{routes.map(r => <Route {...r} />)}</Routes>',
            '<BrowserRouter basename="/base"><Routes><Route path="/users" /></Routes></BrowserRouter>',
            'const X = lazy(() => import("./routes")); <Routes><Route path="/x" element={<X />} /></Routes>',
            '<Routes><ExtraRoutes /></Routes>',
            '<Routes><Route {...props} path="/known" /></Routes>',
            '<Routes><Route path="/known" {...props} /></Routes>',
            '<Routes><Route path="/known" path={override} /></Routes>',
            '<Routes><Route path="*" /></Routes>',
            '<Routes><Route path="/users/:id?" /></Routes>',
            '<Routes><Route index={enabled} /></Routes>',
            '<Routes><Route path="/x" /></Routes><RR.Routes><RR.Route path="/missing" /></RR.Routes>',
            '<Routes><Route path="/users" >',
            "const router = createBrowserRouter([{path: '/users'}]);",
            'import {Route as R} from "react-router-dom"; <Routes><R path="/users" /></Routes>',
            'const example = `<Routes><Route path="/users" /></Routes>`;',
            '// <Routes><Route path="/users" /></Routes>',
            '<Routes><Route path="/users" />{otherRoutes}</Routes>',
        ):
            with self.subTest(source=source):
                self.assertEqual(self.evidence(source, '/missing')['status'], 'unknown')
        self.assertEqual(self.evidence('<Routes><Route path={root}><Route path="teams" /></Route></Routes>', '/teams')['status'], 'unknown')

    def test_element_expression_cannot_fabricate_a_path(self):
        source = '''<Routes><Route element={<Page path="/fake" />} path="/real" /></Routes>'''
        self.assertEqual(self.evidence(source, '/real')['status'], 'present')
        self.assertEqual(self.evidence(source, '/fake')['status'], 'proven_missing')
        source = '''<Routes>{/* <Route path="/fake" /> */}<Route path="/real" /></Routes>'''
        self.assertEqual(self.evidence(source, '/fake')['status'], 'proven_missing')

    def test_attribute_values_and_data_attributes_are_not_paths(self):
        source = """<Routes><Route title=' path="/fake"' data-path="/also-fake" element={<Page />} path="/real" /></Routes>"""
        self.assertEqual(self.evidence(source, '/real')['status'], 'present')
        for path in ('/fake', '/also-fake'):
            self.assertEqual(self.evidence(source, path)['status'], 'proven_missing')

    def test_backend_mounts_and_dynamic_registries_are_unknown(self):
        for source in ("module.exports = app => { const r = Router(); r.get('/users', list); app.use('/api', r); };",
                       "module.exports = app => { for (const r of routes) app[r.method](r.path, r.handler); };",
                       "module.exports = app => { app.route('/api/users').get(list); };",
                       "// app.get('/api/users', list);\nmodule.exports = register;"):
            self.assertEqual(backend_route_evidence({'backend/routes/users.js': source}, 'GET', '/api/users')['status'], 'unknown')
        sources = {'backend/routes/users.js': "module.exports = app => { app.get('/api/users/:id', list); };"}
        self.assertEqual(backend_route_evidence(sources, 'GET', '/api/users/:user')['status'], 'present')
        self.assertEqual(backend_route_evidence(sources, 'POST', '/api/users/:user')['status'], 'proven_missing')
        optional = {'backend/routes/users.js': "module.exports = app => { app.get('/api/users/:id?', list); };"}
        self.assertEqual(backend_route_evidence(optional, 'GET', '/api/users')['status'], 'unknown')
        self.assertEqual(self.evidence('<Routes><Route path="/Users" /></Routes>', '/users')['status'], 'unknown')
        sources['backend/server.js'] = "app.use('/prefix', router);"
        self.assertEqual(backend_route_evidence(sources, 'POST', '/prefix/api/users/:user')['status'], 'unknown')

    def test_runtime_registry_uses_only_trusted_unmounted_server(self):
        blueprint = Path(__file__).parents[1] / 'blueprints'
        server = (blueprint / 'server.js').read_text().replace('__ARC_DEFAULT_PORT__', '43100').replace(
            '__ARC_EXTRA_PORTS__', '[]')
        sources = {'backend/server.js': server,
                   'backend/lib/arc.js': (blueprint / 'arc-runtime.js').read_text(),
                   'backend/routes/workbooks.js': "module.exports = app => { app.get('/api/workbooks', list); };"}
        with TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / 'backend/node_modules/express').mkdir(parents=True)

            def write_dump(_cmd, **kwargs):
                Path(kwargs['env']['ARC_ROUTE_DUMP']).write_text(
                    '{"routes":[{"method":"GET","path":"/api/workbooks"}],"conflicts":[]}')
                return SimpleNamespace(returncode=0)

            with patch('route_evidence.shutil.which', return_value='/bin/node'), \
                    patch('route_evidence.subprocess.run', side_effect=write_dump) as run:
                result = runtime_backend_routes(project, sources)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(result['routes'][0]['path'], '/api/workbooks')
                run.assert_called_once()
                mounted = {**sources, 'backend/routes/workbooks.js':
                           "module.exports = app => { app.use('/api', router); };"}
                self.assertEqual(runtime_backend_routes(project, mounted)['status'], 'unknown')
                delayed = {**sources, 'backend/routes/workbooks.js':
                           "module.exports = app => { setTimeout(() => app.post('/late', save), 10); };"}
                self.assertEqual(runtime_backend_routes(project, delayed)['status'], 'unknown')
                untrusted = {**sources, 'backend/server.js': server + '\napp.use(router);'}
                self.assertEqual(runtime_backend_routes(project, untrusted)['status'], 'unknown')
                run.assert_called_once()
