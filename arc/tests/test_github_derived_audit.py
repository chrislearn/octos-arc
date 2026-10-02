"""Source/fixture regressions for the full GitHub suite review."""
import json
from pathlib import Path
import re
import unittest
import yaml
from audit_embedded_tests import fixtures
from github_coverage_review import coverage_review
from build_embedded_tests import CASES

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'derived-tests/hackathon--github'


class GitHubDerivedAuditTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((SUITE / 'case-plan.json').read_text())
        self.seed = fixtures('hackathon--github', self.plan)
        self.repos = {r['name']: r for r in self.seed['repositories'] if r['name'].startswith('regression-')}

    def test_team_grant_starts_private_and_denied_then_changes_only_a_direct_team_member(self):
        repo = self.repos['regression-grant-add']
        org = next(o for o in self.seed['organizations'] if o['identifier'] == repo['owner'])
        team = next(t for t in org['teams'] if t['name'] == 'frontend-team')
        self.assertEqual(repo['visibility'], 'Private')
        self.assertEqual(repo['direct_grants']['repo-admin'], 'Admin')
        self.assertNotIn('bob-reviewer', repo['direct_grants'])
        self.assertNotIn('new-member', repo['direct_grants'])
        self.assertEqual(repo['team_grants'], {})
        self.assertIn('bob-reviewer', org['members'])
        self.assertIn('bob-reviewer', team['direct_members'])
        self.assertNotIn('new-member', team['direct_members'])
        replacement = self.repos['regression-grant-replace']
        self.assertEqual(replacement['visibility'], 'Private')
        self.assertNotIn('bob-reviewer', replacement['direct_grants'])
        self.assertEqual(replacement['team_grants'], {'frontend-team': 'Write'})

    def test_every_recipe_pr_target_has_the_referenced_seed_and_unique_number(self):
        all_repos = {r['name']: r for r in self.seed['repositories']}
        for recipes in CASES['hackathon--github'].values():
            for recipe in recipes:
                for case_id in re.findall(r"h\.pr\(\w+,\s*['\"]([^'\"]+)['\"]", recipe['body']):
                    repo = all_repos['regression-' + case_id]
                    self.assertTrue(repo['pull_requests'], case_id)
                    numbers = [pr['number'] for pr in repo['pull_requests']]
                    self.assertEqual(len(numbers), len(set(numbers)), case_id)

    def test_denied_review_seeds_isolate_the_author_draft_and_repository_roles(self):
        for suffix in ['author', 'draft', 'read', 'triage']:
            pr = self.repos['regression-review-denied-' + suffix]['pull_requests'][0]
            self.assertEqual(pr['author'], 'file-contributor')
            self.assertEqual(pr['status'], 'Draft' if suffix == 'draft' else 'Open')
            self.assertEqual(pr['title'], 'Improve onboarding')
            self.assertEqual(pr['reviews'], [])
        for suffix in ['write', 'read', 'triage']:
            repo = self.repos['regression-merge-denied-' + suffix]
            pr = repo['pull_requests'][0]
            self.assertEqual(pr['status'], 'Open')
            self.assertEqual(pr['check_test'], 'success')
            self.assertEqual(pr['reviews'][0]['reviewer'], 'bob-reviewer')
            self.assertNotEqual(pr['reviews'][0]['reviewer'], pr['author'])

    def test_pr_milestone_target_has_no_foreign_milestone_but_foreign_record_exists(self):
        target = self.repos['regression-pr-milestone']
        foreign = next(r for r in self.seed['repositories'] if r['name'] == 'foreign-milestone-repo')
        self.assertIn('v1.0', target['milestones'])
        self.assertNotIn('foreign-milestone', target['milestones'])
        self.assertIn('foreign-milestone', foreign['milestones'])

    def test_frozen_seed_and_coverage_review_are_reproducible_and_do_not_claim_all_clauses(self):
        self.assertEqual(json.loads((SUITE / 'fixtures.json').read_text()), self.seed)
        tree = yaml.safe_load((SUITE / 'requirements.yaml').read_text())
        review = coverage_review(tree, self.plan)
        self.assertEqual(json.loads((SUITE / 'coverage-review.json').read_text()), review)
        self.assertTrue(review['atomic_gate_coverage_complete'])
        self.assertFalse(review['semantic_coverage_complete'])
        self.assertFalse(review['product_runtime_certified'])
        self.assertTrue(review['remaining_gaps'])
        exported = {(r['file'], r['title']) for r in self.plan if r['phase'] == 'node'}
        for item in review['reviewed_behaviors']:
            self.assertTrue(item['exported_witnesses'])
            self.assertTrue(all((w['file'], w['title']) in exported for w in item['exported_witnesses']))


if __name__ == '__main__':
    unittest.main()
