"""Bind the honest semantic coverage ledger to executable export witnesses."""
import json
from pathlib import Path
import unittest
import yaml
from sheet_coverage_review import coverage_review

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'derived-tests/hackathon--sheet'


class SheetDerivedAuditTests(unittest.TestCase):
    def test_frozen_review_links_actual_exported_cases_and_keeps_harness_gaps_explicit(self):
        tree = yaml.safe_load((SUITE/'requirements.yaml').read_text())
        plan = json.loads((SUITE/'case-plan.json').read_text())
        review = coverage_review(tree,plan)
        self.assertEqual(json.loads((SUITE/'coverage-review.json').read_text()), review)
        self.assertTrue(review['atomic_gate_coverage_complete'])
        self.assertFalse(review['semantic_coverage_complete'])
        self.assertFalse(review['product_runtime_certified'])
        self.assertTrue(review['remaining_gaps'])
        for item in review['reviewed_behaviors']:
            for witness in item['exported_witnesses']:
                self.assertFalse(witness['file'].startswith('INTEGRATION-'))
                self.assertIn(json.dumps(witness['title']), (SUITE/witness['file']).read_text())

if __name__ == '__main__': unittest.main()
