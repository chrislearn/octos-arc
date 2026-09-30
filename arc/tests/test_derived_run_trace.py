import json
import tempfile
import unittest
from pathlib import Path

from derived_run_trace import snapshot


class DerivedRunTraceTests(unittest.TestCase):
    def test_snapshot_separates_candidates_approvals_and_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            suite = root / 'derived-tests'
            review = suite / 'review'
            review.mkdir(parents=True)
            arc = root / '.arc'
            arc.mkdir()
            requirements = root / 'requirements'
            requirements.mkdir()
            (requirements / 'requirements.yaml').write_text('id: SHEET\n')
            (suite / 'A.spec.ts').write_text("test('candidate', () => {});\n")
            (suite / 'mechanical-outcomes.json').write_text(json.dumps({'rows': [
                {'status': 'candidate'}, {'status': 'needs_ai'}]}))
            (review / 'plan.json').write_text(json.dumps({'targets': [{'status': 'accepted'}]}))
            (review / 'cases.json').write_text(json.dumps({'cases': [
                {'status': 'approved_behavior'}, {'status': 'unreviewed'}]}))
            (review / 'spec-handoff.json').write_text(json.dumps({'nodes': [
                {'node_id': 'A', 'status': 'review_pending', 'candidate_covered': 1,
                 'approved_behavior_cases': 0, 'approved_scenarios': 0,
                 'unverified_scenarios': 1, 'total': 1}]}))
            (arc / 'derived-coverage.json').write_text(json.dumps({'totals': {'covered': 1},
                'execution': {'active_total': 0}}))
            (arc / 'flow-metrics.jsonl').write_text('\n'.join(json.dumps(row) for row in [
                {'kind': 'derived_spec_stage', 'stage': 'requested'},
                {'kind': 'derived_background', 'outcome': 'stale_batch_input'},
                {'kind': 'derived_model_review', 'remaining_invalid_categories': {'missing_assertion': 2}},
                {'kind': 'derived_prompt_overflow', 'target_id': 'S1', 'prompt_chars': 200}]))
            (arc / 'llm-usage.jsonl').write_text(json.dumps({
                'label': 'derived scenario review', 'prompt_tokens': 100,
                'completion_tokens': 20, 'prompt_cache_hit_tokens': 40}) + '\n')
            result = snapshot(root)
            self.assertEqual(result['spec_files'], 1)
            self.assertEqual(result['mechanical_outcomes'], {'candidate': 1, 'needs_ai': 1})
            self.assertEqual(result['case_statuses'], {'approved_behavior': 1, 'unreviewed': 1})
            self.assertEqual(result['handoff_statuses'], {'review_pending': 1})
            self.assertEqual(result['nodes'][0]['unverified_scenarios'], 1)
            self.assertEqual(result['execution'], {'active_total': 0})
            self.assertEqual(result['background_outcomes'], {'stale_batch_input': 1})
            self.assertEqual(result['remaining_invalid_categories'], {'missing_assertion': 2})
            self.assertEqual(result['prompt_overflows'][0]['target_id'], 'S1')
            self.assertEqual(result['model_usage_by_label']['derived scenario review'], {
                'requests': 1, 'prompt_tokens': 100, 'completion_tokens': 20, 'cache_hit_tokens': 40})


if __name__ == '__main__':
    unittest.main()
