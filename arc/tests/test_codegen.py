import tempfile
import unittest
from pathlib import Path

from codegen import incomplete_blocks, normalize_bare_file_reply, normalize_paired_file_reply, parse_edit_blocks, parse_file_blocks, prepare_edit_files, write_files


class ParseTests(unittest.TestCase):
    def test_strictly_paired_alternate_file_envelopes(self):
        for raw in ('We will update two files.\n\n<FILE backend/a.js>\nmodule.exports = 1;\n<END FILE>\n'
                    '<FILE frontend/src/a.jsx>\nexport default 1;\n<END FILE>',
                    '<::<FILE backend/a.js>:::>\nmodule.exports = 1;\n<:: <END FILE> :::>'):
            with self.subTest(raw=raw):
                normalized = normalize_paired_file_reply(raw)
                self.assertIn('backend/a.js', parse_file_blocks(normalized))

    def test_alternate_envelope_rejects_mixed_or_incomplete_replies(self):
        for raw in ('<FILE backend/a.js>\nx\n<END FILE>\nunfinished',
                    '<FILE backend/a.js>\nx\n<END FILE>\n<FILE backend/b.js>\ny',
                    '<FILE backend/a.js>\nx\n<END FILE>\n<FILE backend/a.js>\ny\n<END FILE>',
                    '<FILE ../secret>\nx\n<END FILE>',
                    '<<<FILE backend/a.js>>>\nx\n<<<END FILE>>>'):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_paired_file_reply(raw))

    def test_rejected_reply_is_retained_outside_application_sources(self):
        import main
        with tempfile.TemporaryDirectory() as folder:
            flow = object.__new__(main.Flow)
            flow.output_dir = Path(folder)
            flow.save_rejected_reply('REQ-1 implement', 'no_blocks', '<FILE backend/a.js>\nx')
            saved = list((Path(folder) / '.arc' / 'rejected-replies').glob('*.txt'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_text(), '<FILE backend/a.js>\nx')

    def test_completed_bare_file_sections_have_a_deterministic_envelope(self):
        raw = "FILE backend/routes/example.js\nmodule.exports = app => {};\n\nFILE frontend/src/View.jsx\nexport default () => <p>View</p>;"
        self.assertEqual(parse_file_blocks(normalize_bare_file_reply(raw)), {
            'backend/routes/example.js': 'module.exports = app => {};\n',
            'frontend/src/View.jsx': 'export default () => <p>View</p>;\n'})

    def test_bare_compatibility_refuses_ambiguous_or_unsafe_envelopes(self):
        for raw in ('Here is code:\nFILE frontend/a.js\nx',
                    'FILE ../outside.js\nx', 'FILE /frontend/a.js\nx',
                    'FILE frontend/a.js\nx\nFILE frontend/a.js\ny',
                    'FILE frontend/a.js\nx\nFILE backend/b.js\n',
                    'FILE frontend/a.js\n```js\nx\n```',
                    'FILE frontend/a.js\nx\nEDIT backend/b.js\ny',
                    'FILE frontend/a.js\nx\n<<<EDIT backend/b.js>>>'):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_bare_file_reply(raw))
    def test_should_accept_a_file_header_with_two_closing_brackets(self):
        # v7.17 run 0892dfbc3f83: one `<<<FILE path>>` typo discarded a whole
        # three-file reply, including an unrelated build fix.
        reply = ("<<<FILE a.js>>>\nconst a = 1;\n<<<END FILE>>>\n"
                 "<<<FILE b.jsx>>\nexport default 1;\n<<<END FILE>>>\n<<<NO CHANGE>>>")
        self.assertFalse(incomplete_blocks(reply))
        self.assertEqual(parse_file_blocks(reply), {"a.js": "const a = 1;\n", "b.jsx": "export default 1;\n"})

    def test_should_extract_blocks_and_confine_paths(self):
        text = ("Here you go.\n<<<FILE backend/server.js>>>\nconst x = 1;\n<<<END FILE>>>\n"
                "<<<FILE frontend/src/index.html >>>\n<p>hi</p>\n<<<END FILE>>>\n"
                "<<<FILE ../etc/passwd>>>\nno\n<<<END FILE>>>\n<<<FILE /abs/x>>>\nno\n<<<END FILE>>>\nDone.")
        files = parse_file_blocks(text)
        self.assertEqual(sorted(files), ["backend/server.js", "frontend/src/index.html"])
        self.assertEqual(files["backend/server.js"], "const x = 1;\n")

    def test_should_strip_a_stray_fence_and_keep_marker_like_code(self):
        text = "<<<FILE a.js>>>\n```js\nif (a <<< b) {}\n```\n<<<END FILE>>>"
        self.assertEqual(parse_file_blocks(text)["a.js"], "if (a <<< b) {}\n")

    def test_should_return_empty_when_no_blocks(self):
        self.assertEqual(parse_file_blocks("just prose"), {})

    def test_accepts_only_standalone_short_end_markers(self):
        for ending in ("<<<END EDIT>>>", "<END EDIT>", "END EDIT"):
            reply = ("<<<EDIT page.js>>>\n<<<SEARCH>>>\nold\n<<<REPLACE>>>\nnew\n"
                     + ending + "\n")
            self.assertEqual(parse_edit_blocks(reply), [("page.js", "old", "new")])
        self.assertEqual(parse_edit_blocks("<<<EDIT page.js>>>\n<<<SEARCH>>>\na\n"
                                           "<<<REPLACE>>>\nb\nEND EDIT plus prose"), [])
        self.assertEqual(parse_file_blocks("<<<FILE page.js>>>\nconst x = 1;\n<END FILE>"),
                         {"page.js": "const x = 1;\n"})

    def test_should_write_files_under_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = write_files(Path(tmp), {"backend/server.js": "x\n"})
            self.assertEqual(written, ["backend/server.js"])
            self.assertEqual((Path(tmp) / "backend" / "server.js").read_text(), "x\n")

    def test_exact_edits_are_small_and_applied_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'page.html').write_text('alpha\nbeta\ngamma\n')
            reply = ('<<<EDIT page.html>>>\n<<<SEARCH>>>\nbeta\n<<<REPLACE>>>\nsecond\n<<<END EDIT>>>\n'
                     '<<<EDIT page.html>>>\n<<<SEARCH>>>\nsecond\n<<<REPLACE>>>\nupdated\n<<<END EDIT>>>')
            edits = parse_edit_blocks(reply)
            self.assertEqual(len(edits), 2)
            files, errors = prepare_edit_files(root, edits)
            self.assertEqual(errors, [])
            self.assertEqual(files['page.html'], 'alpha\nupdated\ngamma\n')
            self.assertEqual((root / 'page.html').read_text(), 'alpha\nbeta\ngamma\n', 'staging must not write')

    def test_empty_replacement_is_deletion_not_the_following_block(self):
        delete = '<<<EDIT page.js>>>\n<<<SEARCH>>>\nremove();\n<<<REPLACE>>>\n<<<END EDIT>>>'
        next_edit = '\n<<<EDIT page.js>>>\n<<<SEARCH>>>\nbefore();\n<<<REPLACE>>>\nafter();\n<<<END EDIT>>>'
        for newline in ('\n', '\r\n'):
            self.assertEqual(parse_edit_blocks((delete + next_edit).replace('\n', newline)),
                             [('page.js', 'remove();', ''), ('page.js', 'before();', 'after();')])
            self.assertEqual(parse_edit_blocks(delete.replace('\n', newline)), [('page.js', 'remove();', '')])

    def test_malformed_terminator_cannot_swallow_a_later_edit(self):
        bad = '<<<EDIT page.js>>>\n<<<SEARCH>>>\nold\n<<<REPLACE>>>\nnew\n<<<END EDIT>>\n'
        good = '<<<EDIT other.js>>>\n<<<SEARCH>>>\na\n<<<REPLACE>>>\nb\n<<<END EDIT>>>'
        self.assertEqual(parse_edit_blocks(bad + good), [('other.js', 'a', 'b')])
        self.assertTrue(incomplete_blocks(bad + good))

    def test_empty_search_is_parsed_then_rejected_by_the_write_guard(self):
        reply = '<<<EDIT page.js>>>\n<<<SEARCH>>>\n<<<REPLACE>>>\nnew\n<<<END EDIT>>>'
        edits = parse_edit_blocks(reply)
        self.assertEqual(edits, [('page.js', '', 'new')])
        files, errors = prepare_edit_files(Path('.'), edits)
        self.assertEqual(files, {})
        self.assertEqual(errors, ['page.js: empty SEARCH'])

    def test_malformed_file_end_never_consumes_the_next_file(self):
        for ending in ('<<<END FILE>>', '<<<END FILE>>>>', ''):
            bad = '<<<FILE backend/a.js>>>\nconst a = 1;\n' + ending + '\n'
            good = '<<<FILE backend/b.js>>>\nconst b = 2;\n<<<END FILE>>>'
            with self.subTest(ending=ending):
                self.assertEqual(parse_file_blocks(bad + good), {'backend/b.js': 'const b = 2;\n'})
                self.assertTrue(incomplete_blocks(bad + good))

    def test_malformed_end_marker_cannot_become_replacement_source(self):
        reply = '<<<EDIT page.js>>>\n<<<SEARCH>>>\nold\n<<<REPLACE>>>\nnew\n<<<END EDIT>>\n<<<END EDIT>>>'
        self.assertEqual(parse_edit_blocks(reply), [])
        self.assertTrue(incomplete_blocks(reply))

    def test_literal_end_marker_can_be_deleted_from_a_corrupted_source(self):
        reply = '<<<EDIT page.js>>>\n<<<SEARCH>>>\n<<<END EDIT>>>\n<<<REPLACE>>>\n<<<END EDIT>>>'
        self.assertEqual(parse_edit_blocks(reply), [('page.js', '<<<END EDIT>>>', '')])

    def test_file_body_containing_an_edit_example_is_not_an_edit_operation(self):
        example = '<<<EDIT another.js>>>\n<<<SEARCH>>>\na\n<<<REPLACE>>>\nb\n<<<END EDIT>>>'
        reply = '<<<FILE example.txt>>>\n' + example + '\n<<<END FILE>>>'
        self.assertEqual(parse_file_blocks(reply), {'example.txt': example + '\n'})
        self.assertEqual(parse_edit_blocks(reply), [])
        self.assertFalse(incomplete_blocks(reply))

    def test_missing_or_ambiguous_anchor_rejects_all_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'page.html').write_text('one\none\n')
            files, errors = prepare_edit_files(root, [('page.html', 'one', 'two')])
            self.assertEqual(files, {})
            self.assertIn('matched 2 times', errors[0])
            files, errors = prepare_edit_files(root, [('page.html', 'one\none', 'two'),
                                                      ('page.html', 'absent', 'x')])
            self.assertEqual(files, {})
            self.assertIn('matched 0 times', errors[0])
            self.assertEqual((root / 'page.html').read_text(), 'one\none\n')

    def test_edit_paths_cannot_escape_workspace(self):
        reply = ('<<<EDIT ../secret>>>\n<<<SEARCH>>>\na\n<<<REPLACE>>>\nb\n<<<END EDIT>>>\n'
                 '<<<EDIT /abs/path>>>\n<<<SEARCH>>>\na\n<<<REPLACE>>>\nb\n<<<END EDIT>>>')
        self.assertEqual(parse_edit_blocks(reply), [])


class EditTurnTests(unittest.TestCase):
    def setUp(self):
        import main
        from unittest.mock import Mock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        page = self.root / 'frontend/src/index.html'
        page.parent.mkdir(parents=True)
        page.write_text('<html><head><meta charset="utf-8"></head><body>old</body></html>\n')
        self.flow = object.__new__(main.Flow)
        self.flow.output_dir = self.root
        self.flow.pending_corrections = []
        self.flow.refused_paths = set()
        self.flow.generic_template_installed = False
        self.flow.text_turn = Mock()

    @staticmethod
    def edit(path, old, new):
        return (f'<<<EDIT {path}>>>\n<<<SEARCH>>>\n{old}\n<<<REPLACE>>>\n{new}\n<<<END EDIT>>>')

    def test_small_quoted_edit_updates_file_without_full_response(self):
        import main
        reply = self.edit('frontend/src/index.html', '<body>old</body>', '<body>new</body>')
        self.flow.text_turn.return_value = True, reply
        ok, _ = self.flow.codegen_turn('--- frontend/src/index.html ---\n' +
                                       (self.root / 'frontend/src/index.html').read_text(), 60, 'edit')
        self.assertTrue(ok)
        self.assertEqual(self.flow.last_codegen_written, ['frontend/src/index.html'])
        self.assertIn('<body>new</body>', (self.root / 'frontend/src/index.html').read_text())

    def test_malformed_file_batch_leaves_all_sources_untouched(self):
        self.flow.text_turn.return_value = True, (
            '<<<FILE backend/a.js>>>\nconst a=1;\n<<<END FILE>>\n'
            '<<<FILE backend/b.js>>>\nconst b=2;\n<<<END FILE>>>')
        ok, message = self.flow.codegen_turn('new files', 60, 'implement')
        self.assertFalse(ok)
        self.assertIn('no changes were applied', message)
        self.assertEqual(self.flow.last_codegen_written, [])
        self.assertFalse((self.root / 'backend').exists())

    def test_source_protocol_marker_rejects_otherwise_complete_batch(self):
        self.flow.text_turn.return_value = True, (
            '<<<FILE backend/a.js>>>\nconst a=1;\n<<<END FILE>>>\n'
            '<<<FILE backend/b.js>>>\n<<<SEARCH>>>\nconst b=2;\n<<<END FILE>>>')
        self.assertFalse(self.flow.codegen_turn('new files', 60, 'implement')[0])
        self.assertFalse((self.root / 'backend').exists())

    def test_force_files_bypasses_tool_selection_for_localized_startup_fix(self):
        from unittest.mock import Mock
        self.flow.use_structured_edits = Mock(return_value=True)
        self.flow.structured_edit_turn = Mock()
        self.flow.text_turn.return_value = True, '<<<FILE backend/a.js>>>\nconst a=1;\n<<<END FILE>>>'
        self.assertTrue(self.flow.codegen_turn('new files', 60, 'startup repair', force_files=True)[0])
        self.flow.structured_edit_turn.assert_not_called()

    def test_explicit_no_change_preserves_files_and_defers_to_acceptance(self):
        page = self.root / 'frontend/src/index.html'
        before = page.read_text()
        self.flow.text_turn.return_value = True, '<<<NO CHANGE>>>'
        ok, _ = self.flow.codegen_turn('Requirement already met', 60, 'no change')
        self.assertTrue(ok)
        self.assertTrue(self.flow.last_codegen_no_change)
        self.assertEqual(self.flow.last_codegen_written, [])
        self.assertEqual(page.read_text(), before)

    def test_no_change_marker_must_be_the_entire_reply(self):
        self.flow.text_turn.return_value = True, 'I think <<<NO CHANGE>>> is best.'
        ok, _ = self.flow.codegen_turn('Requirement already met', 60, 'no change prose')
        self.assertFalse(ok)
        self.assertFalse(self.flow.last_codegen_no_change)

    def test_blind_edit_is_refused_without_touching_file(self):
        reply = self.edit('frontend/src/index.html', 'old', 'new')
        self.flow.text_turn.return_value = True, reply
        ok, _ = self.flow.codegen_turn('Other files: frontend/src/index.html', 60, 'blind edit')
        self.assertFalse(ok)
        self.assertEqual(self.flow.refused_paths, {'frontend/src/index.html'})
        self.assertIn('old', (self.root / 'frontend/src/index.html').read_text())

    def test_failed_edit_does_not_apply_other_file_blocks(self):
        other = self.root / 'backend/server.js'
        other.parent.mkdir(parents=True)
        other.write_text('previous\n')
        reply = (self.edit('frontend/src/index.html', 'missing', 'new') + '\n'
                 '<<<FILE backend/server.js>>>\nchanged\n<<<END FILE>>>')
        self.flow.text_turn.return_value = True, reply
        prompt = ('--- frontend/src/index.html ---\n' + (self.root / 'frontend/src/index.html').read_text() +
                  '--- backend/server.js ---\nprevious\n')
        ok, _ = self.flow.codegen_turn(prompt, 60, 'bad anchor')
        self.assertFalse(ok)
        self.assertEqual(other.read_text(), 'previous\n')
        self.assertIn('matched 0 times', self.flow.pending_corrections[-1])
        self.assertEqual(self.flow.refused_paths, {'frontend/src/index.html'})

    def install_generic(self):
        import main
        from generic_template import install_generic_template
        install_generic_template(self.root, main.BUNDLE_DIR, 3000, [])
        self.flow.generic_template_installed = True
        routes = self.root / 'backend/routes'
        routes.mkdir(parents=True, exist_ok=True)
        (routes / 'filters.js').write_text(
            "module.exports = app => {\n  app.post('/api/w/:id/filters', (req, res) => res.end());\n};\n")

    def test_should_refuse_reply_that_registers_an_owned_route_again_and_requote_owner(self):
        # v10.0 sheet 819388a5f77b: workbooks.js re-registered filters.js's routes; the
        # conflict surfaced only as a fatal preflight nodes later.
        self.install_generic()
        reply = ('<<<FILE backend/routes/workbooks.js>>>\nmodule.exports = app => {\n'
                 "  app.get('/api/w', (req, res) => res.json([]));\n"
                 "  app.post('/api/w/:workbookId/filters', (req, res) => res.end());\n};\n<<<END FILE>>>")
        self.flow.text_turn.return_value = True, reply
        ok, message = self.flow.codegen_turn('new routes', 60, 'REQ-5 implement')
        self.assertFalse(ok)
        self.assertEqual(self.flow.last_codegen_outcome, 'route_conflict')
        self.assertFalse((self.root / 'backend/routes/workbooks.js').exists())
        self.assertIn('backend/routes/filters.js:2', message)
        self.assertIn('backend/routes/filters.js', self.flow.last_codegen_refused)
        self.assertIn('backend/routes/filters.js', self.flow.refused_paths)
        self.assertIn('already registered', self.flow.pending_corrections[-1])

    def test_should_accept_moving_a_route_between_files_in_one_reply(self):
        self.install_generic()
        owner = (self.root / 'backend/routes/filters.js').read_text()
        reply = ("<<<FILE backend/routes/filters.js>>>\nmodule.exports = () => {};\n<<<END FILE>>>\n"
                 '<<<FILE backend/routes/workbooks.js>>>\nmodule.exports = app => {\n'
                 "  app.post('/api/w/:id/filters', (req, res) => res.end());\n};\n<<<END FILE>>>")
        self.flow.text_turn.return_value = True, reply
        ok, _ = self.flow.codegen_turn('--- backend/routes/filters.js ---\n' + owner, 60, 'move')
        self.assertTrue(ok)
        self.assertEqual(sorted(self.flow.last_codegen_written),
                         ['backend/routes/filters.js', 'backend/routes/workbooks.js'])

    def test_should_refuse_generic_entry_rewrite_that_drops_runtime_but_apply_other_files(self):
        self.install_generic()
        entry = (self.root / 'backend/server.js').read_text()
        reply = ("<<<FILE backend/server.js>>>\nconst express = require('express');\n"
                 "express().listen(process.env.PORT);\n<<<END FILE>>>\n"
                 "<<<FILE backend/routes/items.js>>>\nmodule.exports = app => app.get('/api/items', (q, s) => s.json([]));\n"
                 "<<<END FILE>>>")
        self.flow.text_turn.return_value = True, reply
        ok, _ = self.flow.codegen_turn('--- backend/server.js ---\n' + entry, 60, 'entry rewrite')
        self.assertTrue(ok)
        self.assertEqual(self.flow.last_codegen_written, ['backend/routes/items.js'])
        self.assertEqual((self.root / 'backend/server.js').read_text(), entry)
        self.assertIn('backend/server.js is the installed generic entry', self.flow.pending_corrections[-1])

    def test_mixed_file_and_edit_for_one_path_is_refused(self):
        reply = (self.edit('frontend/src/index.html', 'old', 'new') + '\n'
                 '<<<FILE frontend/src/index.html>>>\n<p>whole</p>\n<<<END FILE>>>')
        self.flow.text_turn.return_value = True, reply
        ok, _ = self.flow.codegen_turn('--- frontend/src/index.html ---\nsource', 60, 'mixed')
        self.assertFalse(ok)
        self.assertIn('old', (self.root / 'frontend/src/index.html').read_text())


class EnsureCharsetTests(unittest.TestCase):
    def test_should_inject_meta_charset_when_missing(self):
        from codegen import ensure_charset
        self.assertEqual(ensure_charset("<html><head><title>x</title></head><body>账户</body></html>"),
                         '<html><head><meta charset="utf-8"><title>x</title></head><body>账户</body></html>')
        self.assertEqual(ensure_charset("<html><body>x</body></html>"),
                         '<html><head><meta charset="utf-8"></head><body>x</body></html>')
        self.assertEqual(ensure_charset("<p>x</p>"), '<meta charset="utf-8">\n<p>x</p>')

    def test_should_keep_existing_charset(self):
        from codegen import ensure_charset
        page = '<html><head><meta charset="UTF-8"></head></html>'
        self.assertEqual(ensure_charset(page), page)

    def test_should_apply_to_written_html_files(self):
        import tempfile
        from pathlib import Path
        from codegen import write_files
        root = Path(tempfile.mkdtemp())
        write_files(root, {"frontend/src/index.html": "<html><head></head><body></body></html>", "backend/server.js": "x"})
        self.assertIn('<meta charset="utf-8">', (root / "frontend/src/index.html").read_text())
        self.assertEqual((root / "backend/server.js").read_text(), "x")


class UnescapeFlattenedTests(unittest.TestCase):
    def test_should_restore_newlines_in_a_flattened_block(self):
        from codegen import unescape_flattened
        flat = "const a = 1;\\n" * 12 + "x"
        out = unescape_flattened(flat)
        self.assertEqual(out.count("\n"), 12)
        self.assertNotIn("\\n", out)

    def test_should_leave_normal_files_with_string_escapes_alone(self):
        from codegen import unescape_flattened
        normal = "res.end('a\\nb');\n" * 20
        self.assertEqual(unescape_flattened(normal), normal)


class RepairFlattenedJsTests(unittest.TestCase):
    def test_should_unescape_only_when_it_makes_the_file_parse(self):
        import shutil, tempfile
        from pathlib import Path
        from codegen import repair_flattened_js
        if not shutil.which("node"):
            self.skipTest("node not on PATH")
        p = Path(tempfile.mkdtemp()) / "server.js"
        p.write_text("const a = 1;\nfunction f() {\n  if (a) x = 1;\\n  if (!a) x = 2;\\n  return x;\n}\n")
        self.assertTrue(repair_flattened_js(p))
        self.assertNotIn("\\n", p.read_text())
        good = "const s = 'a\\nb';\nconsole.log(s);\n"
        p.write_text(good)
        self.assertFalse(repair_flattened_js(p))
        self.assertEqual(p.read_text(), good)


class DedupeNavLinksTests(unittest.TestCase):
    def test_should_preserve_legitimate_links_with_shared_destinations(self):
        import tempfile
        from pathlib import Path
        from codegen import dedupe_nav_links
        root = Path(tempfile.mkdtemp())
        (root / "frontend/src").mkdir(parents=True); (root / "backend").mkdir()
        page = '<body><!--NAV-->\n<a href="/register">Register</a>\n<a href="/about">About</a>\n<a href="/help">Help</a></body>'
        (root / "frontend/src/index.html").write_text(page)
        (root / "backend/server.js").write_text("x")
        self.assertEqual(dedupe_nav_links(root), [])
        (root / "backend/server.js").write_text("""const nav = '<a href="/register">R</a> <a href="/about">A</a>'; html.replace('<!--NAV-->', nav)""")
        self.assertEqual(dedupe_nav_links(root), [])
        out = (root / "frontend/src/index.html").read_text()
        self.assertIn('href="/register"', out)
        self.assertIn('href="/about"', out)
        self.assertIn('href="/help"', out)  # not rendered by the server: kept
        self.assertIn("<!--NAV-->", out)
        self.assertIn("<!--NAV-->", out)


class PreserveFileSemanticsTests(unittest.TestCase):
    def test_should_preserve_escape_heavy_valid_javascript_and_json(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = "line\n" * 20
            js = "const text = " + json.dumps(value) + ";\n"
            data = json.dumps({"text": value})
            write_files(root, {"backend/server.js": js, "backend/sample.json": data})
            self.assertEqual((root / "backend/server.js").read_text(), js)
            self.assertEqual((root / "backend/sample.json").read_text(), data)


class TinyFailureEvidenceTests(unittest.TestCase):
    def test_failed_selector_is_logged_before_compact_fallback(self):
        import main
        from acceptance import RunSummary, TestOutcome
        from unittest.mock import patch
        flow = object.__new__(main.Flow)
        with tempfile.TemporaryDirectory() as tmp:
            flow.output_dir = Path(tmp)
            flow.tests_dir = Path(tmp)
            flow.web_port = 43219
            flow.runner = object()
            flow.spec_bodies = lambda _: 'public contract'
            def generated(*args, **kwargs):
                page = flow.output_dir / 'frontend/src/index.html'
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text('<p>ready</p>')
                return True, 'generated'
            flow.codegen_turn = generated
            flow.run_specs = lambda _: RunSummary(total=1, results=[TestOutcome(
                title='status display', ok=False, status='failed', duration_ms=5000,
                message="getByTestId('status-output'): element not found")])
            with patch('main.log') as log:
                self.assertFalse(flow.tiny_turn('node', ['public.spec.ts'], 60, {'description': 'show status'}))
                self.assertIn("getByTestId('status-output')", '\n'.join(str(c.args[0]) for c in log.call_args_list))


class RepairLocationTests(unittest.TestCase):
    def test_repair_prompt_identifies_external_readonly_tests(self):
        import main
        location = '/external/acceptance specs'
        prompt = main.REPAIR_PROMPT.format(node_id='node', passed=0, total=1,
            failures='example.spec.ts: missing element', corrections='', slow='', sources='',
            smoke=1234, port=3000, test_location=location)
        self.assertIn(location, prompt)


class BestRepairStateTests(unittest.TestCase):
    def test_restores_uncommitted_regression_even_when_commit_id_is_unchanged(self):
        import main
        import time
        from unittest.mock import Mock
        from acceptance import RunSummary, TestOutcome
        flow = object.__new__(main.Flow)
        flow.runner = object()
        flow.repair_rounds = 2
        flow.min_repair_seconds = 0
        flow.node_timeout = 60
        flow.smoke_port = 43219
        flow.web_port = 3000
        flow.tests_dir = None
        flow.pending_corrections = []
        flow.head = lambda: 'same-commit'
        flow.codegen_mode = lambda: False
        flow.wound_down = lambda: False
        flow.time_up = lambda: False
        flow.record_tests = Mock()
        flow.snapshot_sources = Mock()
        flow.sources_text = lambda: ''
        flow.corrections_text = lambda: ''
        flow.turn = Mock(return_value=(False, 'incomplete'))  # partial edits; HEAD remains unchanged
        flow.commit = Mock()
        flow.restore_app = Mock()
        failure = TestOutcome('behavior', False, 'failed', 1, message='missing control')
        flow.run_specs = Mock(side_effect=[RunSummary(passed=1, total=2, results=[failure]),
                                          RunSummary(passed=0, total=2, results=[failure]),
                                          RunSummary(passed=1, total=2, results=[failure])])
        rebuild = Mock(return_value='Rewrite everything')
        self.assertFalse(flow.acceptance_loop('node', ['example.spec.ts'], time.time()+1000, rebuild))
        rebuild.assert_not_called()
        self.assertEqual(flow.turn.call_count, 2)
        flow.restore_app.assert_called_once_with('same-commit')


class VerifiedBehaviorRewriteTests(unittest.TestCase):
    def test_should_repair_failed_extension_without_calling_rebuild(self):
        import main, time
        from unittest.mock import Mock, patch
        from acceptance import RunSummary, TestOutcome
        flow = object.__new__(main.Flow)
        flow.runner = object()
        flow.repair_rounds = 1
        flow.min_repair_seconds = 0
        flow.node_timeout = 60
        flow.tests_dir = None
        flow.pending_corrections = []
        flow.test_verdict = {'working-feature': True}
        flow.requirement_nodes = {'new-feature': {'id':'new-feature', 'description':'Initial content must be preserved even if not asserted'}}
        flow.head = lambda: 'original'
        flow.codegen_mode = lambda: False
        flow.wound_down = flow.time_up = lambda: False
        flow.sources_text = flow.corrections_text = flow.repair_test_location = lambda *args: ''
        flow.record_tests = flow.snapshot_sources = flow.commit = Mock()
        flow.turn = Mock(return_value=(True, 'done'))
        flow.smoke_port, flow.web_port = 43219, 3000
        fail = TestOutcome('new behavior', False, 'failed', 1, message='missing control')
        flow.run_specs = Mock(side_effect=[RunSummary(passed=0, total=1, results=[fail]),
                                          RunSummary(passed=1, total=1)])
        rebuild = Mock(return_value='Replace the application')
        with patch.dict('os.environ', {'OCTOS_ARC_REWRITE_ON_ZERO': '1'}):
            self.assertTrue(flow.acceptance_loop('new-feature', ['new.spec.ts'],
                                                time.time()+1000, rebuild))
        rebuild.assert_not_called()
        flow.turn.assert_called_once()
        self.assertIn('Fix frontend/', flow.turn.call_args.args[0])
        self.assertIn('Initial content must be preserved even if not asserted', flow.turn.call_args.args[0])

    def test_should_avoid_full_rewrite_when_any_behavior_already_passed(self):
        import main
        from acceptance import RunSummary
        flow = object.__new__(main.Flow)
        flow.test_verdict = {'new-feature': False}
        flow.probe_summaries = {}
        self.assertTrue(flow.can_rewrite_from_scratch())
        flow.test_verdict['existing-feature'] = True
        self.assertFalse(flow.can_rewrite_from_scratch())
        flow.test_verdict.clear()
        flow.probe_summaries['template-feature'] = RunSummary(passed=1, total=2)
        self.assertFalse(flow.can_rewrite_from_scratch())


class RepairModeTransitionTests(unittest.TestCase):
    def test_should_try_tool_repair_before_stopping_at_codegen_plateau(self):
        import main
        import time
        from unittest.mock import Mock, patch
        from acceptance import RunSummary, TestOutcome
        for tools_succeed, rounds in ((True, 5), (False, 5), (False, 2)):
            with self.subTest(tools_succeed=tools_succeed, rounds=rounds):
                flow = object.__new__(main.Flow)
                flow.runner = object()
                flow.repair_rounds = rounds
                flow.min_repair_seconds = 0
                flow.node_timeout = 60
                flow.smoke_port = 43219
                flow.web_port = 3000
                flow.tests_dir = None
                flow.pending_corrections = []
                flow.head = lambda: 'same-commit'
                flow.codegen_mode = lambda: not flow.codegen_blocked
                flow.wound_down = lambda: False
                flow.time_up = lambda: False
                flow.record_tests = Mock()
                flow.snapshot_sources = Mock()
                flow.sources_text = lambda: ''
                flow.corrections_text = lambda: ''
                flow.spec_bodies = lambda _: 'complete-spec-and-helper-evidence'
                def generated_repair(*args, **kwargs):
                    # This test models applied but ineffective code changes;
                    # an unchanged response now goes straight to bounded fallback.
                    flow.last_codegen_written = ['frontend/src/app.js']
                    return True, 'generated repair'
                flow.codegen_turn = Mock(side_effect=generated_repair)
                flow.turn = Mock(return_value=(True, 'done'))
                flow.commit = Mock()
                flow.restore_app = Mock()
                summaries = [RunSummary(passed=0, total=1, results=[
                    TestOutcome('behavior', False, 'failed', 1, message=f'missing control {i}')])
                    for i in range(3)]
                summaries.append(RunSummary(passed=int(tools_succeed), total=1, results=[
                    TestOutcome('behavior', tools_succeed, 'passed' if tools_succeed else 'failed',
                                1, message='' if tools_succeed else 'still missing control')]))
                flow.run_specs = Mock(side_effect=summaries)
                with patch.dict('os.environ', {'OCTOS_ARC_CODEGEN_REPAIRS': '2'}):
                    self.assertEqual(flow.acceptance_loop('node', ['generic.spec.ts'], time.time()+1000),
                                     tools_succeed)
                self.assertEqual(flow.codegen_turn.call_count, 2)
                for call in flow.codegen_turn.call_args_list:
                    self.assertIn('complete-spec-and-helper-evidence', call.args[0])
                self.assertEqual(flow.turn.call_count, int(rounds > 2))
                self.assertEqual(flow.run_specs.call_count, 4 if rounds > 2 else 3)


class RepairEntryTests(unittest.TestCase):
    def test_should_supply_executable_test_entry_with_quoted_paths(self):
        import main
        import json
        import subprocess
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix="runner space ' ") as tmp:
            root = Path(tmp).resolve()
            work = root / 'prepared'
            work.mkdir()
            config = work / 'playwright.config.ts'
            config.write_text('// prepared')
            binary = root / 'node_modules/.bin/playwright'
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/usr/bin/env python3\nimport os,sys,json\nprint(json.dumps([os.getcwd(), os.environ["E2E_BASE_URL"], sys.argv[1:]]))\n')
            binary.chmod(0o755)
            flow = object.__new__(main.Flow)
            flow.tests_dir = root / 'original tests'
            flow.output_dir = root / 'application'
            flow.smoke_port = 43219
            flow.runner = SimpleNamespace(root=root, work_dir=work, workers=2)
            flow.mem_limit = None
            from unittest.mock import patch
            helper = root / 'verify_app.py'
            helper.write_text('import sys,json; print(json.dumps(sys.argv[1:]))')
            with patch.object(main, 'BUNDLE_DIR', root):
                context = flow.repair_test_location(["generic one's.spec.ts"])
                self.assertIn(str(flow.output_dir), context)
                command = context.split('```sh\n')[1].split('\n```')[0]
                out = subprocess.check_output(['sh', '-c', command], text=True)
                self.assertEqual(json.loads(out), ['--app', str(flow.output_dir), '--tests', str(flow.tests_dir),
                                                   '--playwright', str(root), '--workers', '2', '--spec', "generic one's.spec.ts"])
                with patch.dict('os.environ', {'OCTOS_ARC_FINAL_WORKERS': '4'}):
                    full = flow.repair_test_location()
                    self.assertNotIn('--spec', full)
                    command = full.split('```sh\n')[1].split('\n```')[0]
                    args = json.loads(subprocess.check_output(['sh', '-c', command], text=True))
                    self.assertEqual(args[args.index('--workers') + 1], '4')
                    flow.mem_limit = 512 * 1024 * 1024
                    command = flow.repair_test_location().split('```sh\n')[1].split('\n```')[0]
                    args = json.loads(subprocess.check_output(['sh', '-c', command], text=True))
                    self.assertEqual(args[args.index('--workers') + 1], '1')
                helper.unlink()
                self.assertNotIn('```sh', flow.repair_test_location())


class RegressionCheckpointTests(unittest.TestCase):
    def test_should_bound_checkpoint_gaps_and_skip_final_or_disabled(self):
        import main
        self.assertEqual([i for i in range(1,33) if main.regression_checkpoint_due(i,32,4)], [4,8,16,24,28])
        self.assertEqual([i for i in range(1,20) if main.regression_checkpoint_due(i,20,3)], [3,6,12,18])
        self.assertFalse(main.regression_checkpoint_due(4,20,0))
        points = [0] + [i for i in range(1, 122) if main.regression_checkpoint_due(i, 121, 4)] + [121]
        self.assertLessEqual(max(b - a for a, b in zip(points, points[1:])), 8)

    def test_should_recheck_only_verified_specs_and_queue_observed_regressions(self):
        import main, tempfile
        from pathlib import Path
        from unittest.mock import Mock, patch
        from acceptance import RunSummary, TestOutcome
        with tempfile.TemporaryDirectory() as folder:
            flow=object.__new__(main.Flow)
            flow.runner=object(); flow.tests_dir=Path(folder)
            flow.remaining=lambda:1000; flow.min_repair_seconds=300; flow.mem_limit=None
            flow.test_verdict={'old':True,'new':True,'future':None,'broken':False}
            flow.spec_map={key:[key+'.spec.ts'] for key in flow.test_verdict}
            flow.pending_corrections=[]; flow.mark=Mock(); flow.metric=Mock(); flow.remember_delivery_checkpoint=Mock()
            flow.run_specs=Mock(return_value=RunSummary(passed=1,total=2,results=[
                TestOutcome('new behavior',True,'passed',1,file='new.spec.ts'),
                TestOutcome('old behavior',False,'failed',1,file='old.spec.ts',message='handler undefined')]))
            with patch.dict('os.environ',{'OCTOS_ARC_REGRESSION_CHECKPOINT':'4','OCTOS_ARC_FINAL_WORKERS':'4','OCTOS_ARC_CHECKPOINT_BACKLOG':'0'}):
                flow.repair_regressions = lambda *a, **k: None  # covered by CheckpointRepairTests
                flow.regression_checkpoint(4,12)
            flow.run_specs.assert_called_once_with(['new.spec.ts','old.spec.ts'],workers=4,grader_like=True)
            self.assertIs(flow.test_verdict['old'],False)
            self.assertIs(flow.test_verdict['new'],True)
            self.assertIsNone(flow.test_verdict['future'])
            self.assertIn('handler undefined',' '.join(flow.pending_corrections))
            flow.run_specs.reset_mock()
            flow.run_specs.return_value = RunSummary(passed=1,total=1,results=[
                TestOutcome('new behavior',True,'passed',1,file='new.spec.ts')])
            with patch.dict('os.environ', {'OCTOS_ARC_CHECKPOINT_BACKLOG': '0'}):
                flow.regression_checkpoint(8,32)
            self.assertIn('old.spec.ts', flow.run_specs.call_args.args[0])
            self.assertIs(flow.test_verdict['old'],False)  # absent results cannot prove recovery
            flow.run_specs.return_value = RunSummary(passed=2,total=2,results=[
                TestOutcome('old behavior',True,'passed',1,file='old.spec.ts'),
                TestOutcome('new behavior',True,'passed',1,file='new.spec.ts')])
            with patch.dict('os.environ', {'OCTOS_ARC_CHECKPOINT_BACKLOG': '0'}):
                flow.regression_checkpoint(16,32)
            self.assertIs(flow.test_verdict['old'],True)
            self.assertNotIn('broken.spec.ts', flow.run_specs.call_args.args[0])

    def test_should_preserve_verdicts_when_runner_cannot_report(self):
        import main, tempfile
        from pathlib import Path
        from unittest.mock import Mock, patch
        from acceptance import RunSummary
        with tempfile.TemporaryDirectory() as folder:
            flow = object.__new__(main.Flow)
            flow.runner = object(); flow.tests_dir = Path(folder)
            flow.remaining = lambda: 1000; flow.min_repair_seconds = 300
            flow.test_verdict = {'old': True, 'new': True}
            flow.spec_map = {'old': ['old.spec.ts'], 'new': ['new.spec.ts']}
            flow.pending_corrections = []
            for summary in [RunSummary(error='runner unavailable'), RunSummary(killed=True)]:
                flow.run_specs = Mock(return_value=summary)
                with patch.dict('os.environ', {'OCTOS_ARC_REGRESSION_CHECKPOINT': '4'}):
                    flow.regression_checkpoint(4, 12)
                self.assertEqual(flow.test_verdict, {'old': True, 'new': True})
                self.assertEqual(flow.pending_corrections, [])
            flow.run_specs.reset_mock()
            with patch.dict('os.environ', {'OCTOS_ARC_REGRESSION_CHECKPOINT': '0'}):
                flow.regression_checkpoint(4, 12)
            flow.run_specs.assert_not_called()
            flow.remaining = lambda: 10
            flow.regression_checkpoint(4, 12)
            flow.run_specs.assert_not_called()


class CodegenRepairEvidenceTests(unittest.TestCase):
    def test_should_use_tools_when_complete_evidence_does_not_fit(self):
        import main
        from unittest.mock import patch
        flow = object.__new__(main.Flow)
        flow.spec_bodies = lambda _: 'complete acceptance helper'
        flow.sources_text = lambda: ''
        with patch.dict('os.environ', {'OCTOS_ARC_CODEGEN_CONTEXT_CHARS': '10'}):
            self.assertIsNone(flow.codegen_repair_prompt('node', 'failure and sources'))
        flow.spec_bodies = lambda _: '(none)'
        self.assertIsNone(flow.codegen_repair_prompt('node', 'failure and sources'))


class TailCheckpointTests(unittest.TestCase):
    """Cloud 746c81a2b5aa: the doubling schedule leaves the end of a 32-node run
    unchecked from node 24 to the full suite, where the app is most layered."""

    def test_should_guard_the_last_interval_before_the_end(self):
        import main
        self.assertIn(28, [i for i in range(1, 33) if main.regression_checkpoint_due(i, 32, 4)])

    def test_should_not_add_checkpoints_the_schedule_already_covers(self):
        import main
        self.assertEqual([i for i in range(1, 20) if main.regression_checkpoint_due(i, 20, 3)], [3, 6, 12, 18])
        self.assertEqual([i for i in range(1, 122) if main.regression_checkpoint_due(i, 121, 4)],
                         [4, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120])

    def test_should_still_skip_the_final_node_and_a_disabled_interval(self):
        import main
        self.assertFalse(main.regression_checkpoint_due(32, 32, 4))
        self.assertFalse(main.regression_checkpoint_due(4, 20, 0))


class OutlinedFileEditTests(unittest.TestCase):
    """A file too large to quote whole is shown as an outline; anchored EDIT blocks
    on it are safe (the anchor must match exactly once), whole-file rewrites are not."""

    def setUp(self):
        import main
        from unittest.mock import Mock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        page = self.root / 'frontend/src/App.jsx'
        page.parent.mkdir(parents=True)
        page.write_text("import A from './A';\nexport default function App() {\n  return <Route path='/a' />;\n}\n")
        self.flow = object.__new__(main.Flow)
        self.flow.output_dir = self.root
        self.flow.pending_corrections = []
        self.flow.refused_paths = set()
        self.flow.generic_template_installed = False
        self.flow.text_turn = Mock()
        self.outline = ("--- frontend/src/App.jsx --- (outline, 90 chars; too large to quote whole)\n"
                        "import A from './A';\n  return <Route path='/a' />;\n")

    def test_anchored_edit_on_an_outlined_file_is_applied(self):
        reply = ("<<<EDIT frontend/src/App.jsx>>>\n<<<SEARCH>>>\n  return <Route path='/a' />;\n<<<REPLACE>>>\n"
                 "  return <><Route path='/a' /><Route path='/b' /></>;\n<<<END EDIT>>>")
        self.flow.text_turn.return_value = True, reply
        ok, _ = self.flow.codegen_turn(self.outline, 60, 'outline edit')
        self.assertTrue(ok)
        self.assertIn("path='/b'", (self.root / 'frontend/src/App.jsx').read_text())
        self.assertEqual(self.flow.refused_paths, set())

    def test_whole_file_rewrite_of_an_outlined_file_is_still_refused(self):
        self.flow.text_turn.return_value = True, "<<<FILE frontend/src/App.jsx>>>\nexport default 1;\n<<<END FILE>>>"
        ok, _ = self.flow.codegen_turn(self.outline, 60, 'outline rewrite')
        self.assertFalse(ok)
        self.assertEqual(self.flow.refused_paths, {'frontend/src/App.jsx'})
        self.assertIn("import A", (self.root / 'frontend/src/App.jsx').read_text())

    def test_outline_keeps_imports_exports_routes_and_signatures_verbatim(self):
        import main
        text = ("import x from './x';\nconst helper = 1;\nexport function Page() {\n  const y = 2;\n"
                "  return <Route path='/p' element={<Page />} />;\n}\napp.get('/api/p', handler);\n" + "// filler\n" * 400)
        outline = main.outline_source(text, 2000)
        for line in ("import x from './x';", "export function Page() {", "  return <Route path='/p' element={<Page />} />;",
                     "app.get('/api/p', handler);"):
            self.assertIn(line, outline)
        self.assertNotIn("const y = 2;", outline)
        self.assertLessEqual(len(outline), 2000)


class ParseFailureRecoveryTests(unittest.TestCase):
    def test_kernel_parse_failure_recovers_the_retained_truncated_reply(self):
        import main
        from unittest.mock import Mock
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        flow = object.__new__(main.Flow)
        flow.output_dir = Path(tmp.name)
        flow.pending_corrections = []; flow.refused_paths = set(); flow.generic_template_installed = False
        flow.text_turn = Mock(return_value=(False, "runtime_error: failed to parse response from custom/m (api_style=openai_chat_completions)"))
        proxy = Mock(spec=main.LlmProxy)
        proxy.take_truncated_reply.return_value = "<<<FILE backend/a.js>>>\nconst a = 1;\n<<<END FILE>>>\n<<<FILE backend/b.js>>>\nconst b ="
        flow.llm_proxy = proxy
        ok, text = flow.codegen_turn("new files", 60, "REQ-1 implement")
        self.assertTrue((flow.output_dir / "backend/a.js").is_file())
        self.assertFalse((flow.output_dir / "backend/b.js").exists())
        self.assertIn("backend/a.js", flow.last_codegen_written)
