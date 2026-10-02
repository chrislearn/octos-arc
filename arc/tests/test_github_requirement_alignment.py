import json
from pathlib import Path
import unittest
import yaml
from fixture_delivery import select_prerequisites
from audit_embedded_tests import leaves

ROOT=Path(__file__).resolve().parents[1]

class GitHubRequirementAlignmentTests(unittest.TestCase):
    def test_all_172_additional_cases_keep_their_phase_scope_and_provenance(self):
        recipes=json.loads((ROOT/'github_regression_recipes.json').read_text())
        plan=json.loads((ROOT/'derived-tests/hackathon--github/case-plan.json').read_text())
        original=[row for rows in recipes.values() for row in rows]
        self.assertEqual(len(original),172)
        self.assertEqual(sum(row['phase']=='node' for row in original),162)
        self.assertEqual(sum(row['phase']=='integration' for row in original),10)
        for file,rows in recipes.items():
            for row in rows:
                prefix=file if row['phase']=='integration' else row['node_id']
                matches=[case for case in plan if case['title']==prefix+': '+row['title']]
                self.assertEqual(len(matches),1)
                case=matches[0]
                self.assertEqual(case['file'],file+'.spec.ts')
                for key in ('node_id','phase','requires','fixture','origin_file','origin_title','origin_node_id','source_fixture'):
                    if key in row:self.assertEqual(case.get(key),row[key])

    def test_every_original_scenario_has_one_canonical_node_case(self):
        directory=ROOT/'derived-tests/hackathon--github'
        requirements=yaml.safe_load((directory/'requirements.yaml').read_text())
        plan=json.loads((directory/'case-plan.json').read_text())
        primary=[row for row in plan if row['phase']=='node' and ': requirement scenario ' in row['title']]
        self.assertEqual(len(primary),100)
        for node in leaves(requirements):
            cases=[row for row in primary if row['node_id']==node['id']]
            self.assertEqual([row['title'] for row in cases],
                             [f"{node['id']}: requirement scenario {i}" for i in range(1,len(node['scenarios'])+1)])
        for path in directory.glob('*.spec.ts'):
            self.assertNotIn('spec-owner',path.read_text())
            self.assertNotIn('spec-admin',path.read_text())

    def test_canonical_helper_delivery_includes_roles_and_named_work_items(self):
        document=json.loads((ROOT/'github_requirement_fixtures.json').read_text())
        selected,required=select_prerequisites(document,"await h.signIn(page,'issue-editor'); await h.scenarioIssue(page,'Editable onboarding issue');")
        repo=next(row for row in selected['repositories'] if row['name']=='acme-docs' and row['owner']=='Acme Demo')
        self.assertEqual(repo['direct_grants']['issue-editor'],'Maintain')
        self.assertEqual(repo['direct_grants']['issue-commenter'],'Write')
        self.assertTrue(any(issue['title']=='Editable onboarding issue' for issue in repo['issues']))
        self.assertTrue(any(account['username']=='org-owner' for account in selected['accounts']))
        self.assertTrue(required)

    def test_merge_fixture_delivery_resolves_the_separate_protected_repository(self):
        document=json.loads((ROOT/'github_requirement_fixtures.json').read_text())
        selected,_=select_prerequisites(document,'await h.scenarioPr(page,"Mergeable onboarding PR","merge-onboarding-demo");')
        repo=next(row for row in selected['repositories'] if row['name']=='merge-onboarding-demo')
        self.assertTrue(repo['branch_protection']['main']['require_1_approval'])
        self.assertEqual(repo['direct_grants']['pr-maintainer'],'Maintain')
        self.assertEqual(repo['pull_requests'][0]['check_test'],'success')

if __name__=='__main__':unittest.main()
