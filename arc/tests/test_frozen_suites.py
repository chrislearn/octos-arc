import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import yaml
from frozen_suites import NAMES, materialize, requested_name, requirements_digest, verify_directory
from main import Flow

ROOT=Path(__file__).resolve().parents[1]

class FrozenSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.tree=yaml.safe_load((ROOT/'tasks/hackathon--sheet/requirements.yaml').read_text())
        self.directory=self.root/'suite'; shutil.copytree(ROOT/'frozen-tests/hackathon--sheet',self.directory)

    def test_all_case_reviews_cover_all_atomic_nodes_and_bind_their_spec_hashes(self):
        for name in NAMES.values():
            directory=ROOT/'frozen-tests'/name
            tree=yaml.safe_load((ROOT/'tasks'/name/'requirements.yaml').read_text())
            manifest=verify_directory(directory,tree,name)
            from audit_frozen_tests import leaves
            self.assertEqual(set(manifest['node_ids']),{node['id'] for node in leaves(tree)})
            review=json.loads((directory/'review.json').read_text())
            self.assertEqual({r['node_id'] for r in review['cases']},set(manifest['node_ids']))
            self.assertTrue(all(r['runtime_status']=='not_run_against_product' for r in review['cases']))

    def test_digest_ignores_mapping_key_order_but_binds_original_requirement_content(self):
        self.assertEqual(requirements_digest({'b':'中文','a':[1,2]}),requirements_digest({'a':[1,2],'b':'中文'}))
        changed={**self.tree,'description':'different'}
        with self.assertRaises(ValueError): verify_directory(self.directory,changed,'hackathon--sheet')

    def test_changed_helper_missing_spec_and_extra_file_are_rejected(self):
        helper=self.directory/'helpers.ts'; original=helper.read_bytes(); helper.write_text('changed')
        with self.assertRaises(ValueError): verify_directory(self.directory,self.tree,'hackathon--sheet')
        helper.write_bytes(original); spec=self.directory/'REQ-1-1-1.spec.ts'; contents=spec.read_bytes(); spec.unlink()
        with self.assertRaises(ValueError): verify_directory(self.directory,self.tree,'hackathon--sheet')
        spec.write_bytes(contents); (self.directory/'extra.spec.ts').write_text('unreviewed')
        with self.assertRaises(ValueError): verify_directory(self.directory,self.tree,'hackathon--sheet')

    def test_false_review_and_symlink_cannot_admit_a_suite(self):
        marker=self.directory/'suite-origin.json'; manifest=json.loads(marker.read_text()); manifest['frozen']=False; marker.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): verify_directory(self.directory,self.tree,'hackathon--sheet')
        manifest['frozen']=True; marker.write_text(json.dumps(manifest)); helper=self.directory/'helpers.ts'; original=helper.read_bytes(); helper.unlink(); target=self.root/'outside.ts'; target.write_bytes(original); helper.symlink_to(target)
        with self.assertRaises(ValueError): verify_directory(self.directory,self.tree,'hackathon--sheet')

    def test_rehashing_a_changed_helper_cannot_replace_the_manifest_anchored_at_extraction(self):
        original=verify_directory(self.directory,self.tree,'hackathon--sheet')
        helper=self.directory/'helpers.ts'; helper.write_text('unreviewed helper')
        marker=self.directory/'suite-origin.json'; modified=json.loads(marker.read_text())
        modified['files']['helpers.ts']=hashlib.sha256(helper.read_bytes()).hexdigest()
        marker.write_text(json.dumps(modified))
        with self.assertRaisesRegex(ValueError,'manifest changed'):
            verify_directory(self.directory,self.tree,'hackathon--sheet',original)

    def test_unknown_task_does_not_start_a_process(self):
        self.assertIsNone(requested_name({'name':'another task'}))
        with patch('frozen_suites.subprocess.run') as run:
            self.assertIsNone(materialize('octos',{'name':'another task'},self.root)); run.assert_not_called()

    def test_unknown_name_and_automatic_mismatch_fall_back_but_explicit_mismatch_fails(self):
        catalogue=json.loads((ROOT/'frozen-tests/manifest.json').read_text())
        with patch('frozen_suites.subprocess.run',return_value=Mock(returncode=0,stdout=json.dumps(catalogue))) as run:
            self.assertIsNone(materialize('octos',self.tree,self.root,'unknown'))
            changed={**self.tree,'description':'different'}
            self.assertIsNone(materialize('octos',changed,self.root))
            with self.assertRaises(ValueError): materialize('octos',changed,self.root,'hackathon--sheet')
            self.assertEqual(run.call_count,3)

    def test_old_binary_falls_back_only_for_automatic_selection(self):
        with patch('frozen_suites.subprocess.run',return_value=Mock(returncode=2)):
            self.assertIsNone(materialize('old-octos',self.tree,self.root))
            with self.assertRaises(RuntimeError): materialize('old-octos',self.tree,self.root,'hackathon--sheet')

    def test_frozen_flow_uses_specs_directly_without_regeneration_and_labels_prompts(self):
        flow=Flow(argparse.Namespace(web_port=3000),self.root,self.root/'requirements')
        flow.tests_dir=self.directory; flow.frozen_suite=verify_directory(self.directory,self.tree,'hackathon--sheet')
        flow.original_requirement_tree=self.tree; flow.spec_map={'REQ-1-1-1':['REQ-1-1-1.spec.ts']}
        flow.metric=Mock(); flow.adopt_frozen_business()
        with patch.object(flow, 'text_turn', side_effect=AssertionError('Frozen design must not be regenerated')):
            self.assertIs(flow.app_design(self.tree,[]),flow.app_design_doc)
        self.assertTrue(flow._design_semantics_reviewed)
        self.assertEqual(len(flow.requirement_contracts['nodes']),24)
        self.assertTrue(flow.derived_obligations)
        self.assertTrue((self.root/'.arc/design/app.json').is_file())
        from main import app_design_blocks
        stable,active=app_design_blocks(flow.app_design_doc,'REQ-1-2-2',4000,requirement_ids=['REQ-1-2-2'])
        self.assertIn('Workbook',stable); self.assertIn('Rename workbook',active)
        self.assertNotIn('Create/apply/refresh pivot',active)
        self.assertLess(len(stable)+len(active),30_000)
        self.assertFalse(flow.prepare_derived_tests([]))
        flow.start_background_specs([{'id':'REQ-1-1-1'}])
        prompt=flow.tests_prompt_for('REQ-1-1-1')
        self.assertIn('SOURCE-REVIEWED FROZEN INTERNAL',prompt); self.assertIn('fixtures.json',prompt)
        self.assertIn('not official benchmark tests',prompt)
        self.assertIn('app-design.json',prompt); self.assertIn('test-obligations.json',prompt)
        self.assertIn('source-reviewed frozen internal',flow.verify_text(24))
        flow.runner=Mock(); (self.directory/'helpers.ts').write_text('changed')
        result=flow.run_specs(['REQ-1-1-1.spec.ts'])
        self.assertIn('Frozen suite integrity check failed',result.error); flow.runner.run.assert_not_called()

if __name__=='__main__': unittest.main()
