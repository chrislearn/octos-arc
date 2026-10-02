import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fixture_delivery import fixture_context, select_prerequisites

ROOT = Path(__file__).resolve().parents[1]


class FixtureDeliveryTests(unittest.TestCase):
    def document(self):
        return {'task':'hackathon--github','private_api_required':False,
                'repositories':[{'name':'spec-file-create','owner':'org-files',
                                 'direct_grants':{'writer':'Write'},
                                 'branches':{'main':{'files':{'x':'original'}}}},
                                {'name':'spec-unrelated','owner':'org-other','padding':'x'*1000}],
                'organizations':[{'identifier':'org-files','owners':['owner']},
                                 {'identifier':'org-other','owners':['other']}],
                'accounts':[{'username':'owner','id':'acct-owner'},
                            {'username':'writer','id':'acct-writer'}, {'username':'other'}]}

    def test_helper_case_id_brings_repo_owner_and_grant_accounts_together(self):
        selected, _ = select_prerequisites(self.document(), "await h.repo(page,h.fixtureRepo('file-create'));")
        self.assertEqual([r['name'] for r in selected['repositories']], ['spec-file-create'])
        self.assertEqual([r['identifier'] for r in selected['organizations']], ['org-files'])
        self.assertEqual({r['username'] for r in selected['accounts']}, {'owner','writer'})

    def test_public_pr_issue_org_and_compare_helpers_resolve_case_ids(self):
        for name in ['pr','issue','organization','compare']:
            with self.subTest(name=name):
                selected,_ = select_prerequisites(self.document(), f"await h.{name}(page,'file-create');")
                self.assertEqual(selected['repositories'][0]['name'], 'spec-file-create')

    def test_declared_fixture_resolves_computed_expression_for_an_active_node(self):
        plan=[{'node_id':'REQ-4-4','fixture':'file-create'}, {'node_id':'REQ-6-5','fixture':'unrelated'}]
        selected,_ = select_prerequisites(self.document(), "h.fixtureRepo('file-' + action)",plan=plan,node_ids=['REQ-4-4'])
        self.assertEqual([r['name'] for r in selected['repositories']], ['spec-file-create'])

    def test_exact_names_do_not_select_substring_neighbours(self):
        document={'records':[{'name':'active'}, {'name':'active-old'}]}
        selected,_ = select_prerequisites(document, 'Open active-old')
        self.assertEqual([r['name'] for r in selected['records']], ['active-old'])

    def test_dependency_closure_preserves_reverse_grants_and_display_name_owner(self):
        document={'repositories':[{'name':'repo','owner':'Acme Demo'}],
                  'organizations':[{'identifier':'acme-demo','display_name':'Acme Demo','owners':['alice']}],
                  'accounts':[{'username':'alice'},{'username':'bob'}],
                  'grants':[{'id':'grant-1','repository':'repo','subject':'bob','role':'Write'}]}
        selected,_ = select_prerequisites(document,'Open repo')
        self.assertEqual({r['username'] for r in selected['accounts']}, {'alice','bob'})
        self.assertEqual(len(selected['grants']),1)

    def test_small_context_preference_never_silently_omits_required_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);(directory/'fixtures.json').write_text(json.dumps(self.document()))
            flow=SimpleNamespace(tests_dir=directory,frozen_suite={'name':'hackathon--github'},metric=Mock())
            with patch.dict(os.environ, {'OCTOS_ARC_FIXTURE_CONTEXT_CHARS':'120'}):
                text=fixture_context(flow,"h.fixtureRepo('file-create')")
            selected=json.loads(text[text.index('\n{')+1:])
            self.assertEqual({r['username'] for r in selected['accounts']}, {'owner','writer'})
            self.assertEqual(selected['repositories'][0]['branches']['main']['files']['x'],'original')
            flow.metric.assert_called_once()
            self.assertTrue(flow.metric.call_args.kwargs['complete'])

    def test_invalid_verified_fixture_is_not_presented_as_no_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);(directory/'fixtures.json').write_text('{truncated')
            flow=SimpleNamespace(tests_dir=directory,frozen_suite={'name':'hackathon--github'})
            with self.assertRaises(ValueError):fixture_context(flow,'anything')

    def test_actual_file_node_delivers_every_declared_repository(self):
        directory=ROOT/'derived-tests/hackathon--github'
        flow=SimpleNamespace(tests_dir=directory,frozen_suite={'name':'hackathon--github'},metric=Mock())
        text=fixture_context(flow,(directory/'REQ-4-4.spec.ts').read_text(),['REQ-4-4'])
        selected=json.loads(text[text.index('\n{')+1:])
        plan=json.loads((directory/'case-plan.json').read_text())
        expected={'spec-'+row['fixture'] for row in plan if row['node_id']=='REQ-4-4' and row.get('fixture') and row['phase']=='node'}
        self.assertTrue(expected <= {r['name'] for r in selected['repositories']})

    def test_new_guidance_is_node_attached_and_uses_exclusive_mutation_fixtures(self):
        import build_embedded_tests
        from audit_embedded_tests import fixtures
        rows=[r for group in build_embedded_tests.CASES['hackathon--github'].values() for r in group if 'guide:' in r['title']]
        fixtures_added={'guide-default-release','guide-file-edit-history','guide-issue-lifecycle','guide-review-publication'}
        new=[r for r in rows if r.get('fixture') in fixtures_added or 'scenario prerequisites' in r['title']]
        self.assertEqual(len(new),5)
        self.assertTrue(all(r['phase']=='node' for r in new))
        mutations=[r['fixture'] for r in new if r.get('fixture')]
        self.assertEqual(len(mutations),len(set(mutations)))
        document=fixtures('hackathon--github',new)
        release=next(r for r in document['repositories'] if r['name']=='spec-guide-default-release')
        self.assertIn('release',release['branches'])
        review=next(r for r in document['repositories'] if r['name']=='spec-guide-review-publication')
        self.assertEqual(review['pull_requests'][0]['author'],'spec-write')
        self.assertEqual(review['pull_requests'][0]['reviews'],[])

    def test_generation_prompt_keeps_computed_prerequisites_and_refuses_hard_overflow(self):
        import argparse
        import main
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'frozen';directory.mkdir()
            document=self.document()
            contents='immutable fixture bytes '*2200
            document['repositories'][0]['branches']['main']['files']['x']=contents
            (directory/'fixtures.json').write_text(json.dumps(document))
            (directory/'case-plan.json').write_text(json.dumps([
                {'node_id':'REQ-4-4','fixture':'file-create'}]))
            flow=main.Flow(argparse.Namespace(web_port=1),root,root)
            flow.tests_dir=directory;flow.frozen_suite={'name':'hackathon--github'}
            flow.codegen_reasoning=lambda _:None
            flow.codegen_context_chars=lambda:96000
            node={'id':'REQ-4-4','description':'Edit a file','active_requirement_ids':['REQ-4-4']}
            spec="await h.repo(page,h.fixtureRepo(prefix + action));"
            with patch.dict(os.environ,{'OCTOS_ARC_FIXTURE_CONTEXT_CHARS':'120'}):
                prompt=flow.codegen_implement_prompt(node,spec)
                self.assertIsNotNone(prompt)
                self.assertIn(contents,prompt)
                self.assertIn('"username":"writer"',prompt)
                self.assertIn(spec,prompt)
                flow.codegen_context_chars=lambda:36000
                self.assertIsNone(flow.codegen_implement_prompt(node,spec))
                self.assertEqual(flow.codegen_budget['reason'],
                                 'fixed_prompt_entry_or_critical_corrections_exceed_budget')


if __name__=='__main__': unittest.main()
