import json
from pathlib import Path
import tempfile
import unittest

from metrics import summarize


class MetricsDiagnosticTests(unittest.TestCase):
    def test_phase_costs_and_first_measurement_do_not_conflate_reasoning_or_node_repairs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.arc').mkdir()
            usage = [dict(phase='implement', prompt_tokens=100, completion_tokens=20,
                          reasoning_tokens=10, prompt_cache_hit_tokens=50, elapsed_ms=500),
                     dict(phase='repair', no_usage=True, guard_token_estimate=200, elapsed_ms=100)]
            flow = [dict(kind='acceptance', scope='node', passed=1, total=1),
                    dict(kind='acceptance', scope='whole_app', round=0, passed=2, total=3),
                    dict(kind='acceptance', scope='final_suite', round=0, passed=3, total=3),
                    dict(kind='turn', phase='repair', elapsed_seconds=4.5),
                    dict(kind='codegen', outcome='anchor_failed')]
            for name, rows in [('llm-usage', usage), ('flow-metrics', flow)]:
                (root / '.arc' / f'{name}.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
            data = summarize(root)
            self.assertEqual(data['billed']['total_tokens'], 120)  # reasoning is already in completion
            self.assertEqual(data['billed']['input_cache_hit_ratio'], 0.5)
            self.assertEqual(data['billed']['missing_usage_requests'], 1)
            self.assertEqual(data['billed']['cost_guard_tokens'], 320)
            self.assertEqual(data['by_phase']['implement']['completion_tokens'], 20)
            self.assertEqual(data['diagnostics']['first_whole_app_measurement']['passed'], 2)
            self.assertEqual(data['diagnostics']['repair_seconds'], 4.5)
            self.assertEqual(data['diagnostics']['codegen_outcomes'], {'anchor_failed': 1})

    def test_missing_first_pass_data_is_unknown_not_zero_or_final_score(self):
        with tempfile.TemporaryDirectory() as folder:
            data = summarize(Path(folder))
            self.assertIsNone(data['diagnostics']['first_whole_app_measurement'])
            self.assertIsNone(data['billed']['input_cache_hit_ratio'])
