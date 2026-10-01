import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import yaml
from embedded_suites import NAMES, materialize, requested_name, requirements_digest, verify_directory
from main import Flow

ROOT=Path(__file__).resolve().parents[1]

class EmbeddedSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.tree=yaml.safe_load((ROOT/'tasks/hackathon--sheet/requirements.yaml').read_text())
        self.directory=self.root/'suite'; shutil.copytree(ROOT/'derived-tests/hackathon--sheet',self.directory)

    def test_all_case_reviews_cover_all_atomic_nodes_and_bind_their_spec_hashes(self):
        for name in NAMES.values():
            directory=ROOT/'derived-tests'/name
            tree=yaml.safe_load((ROOT/'tasks'/name/'requirements.yaml').read_text())
            manifest=verify_directory(directory,tree,name)
            from audit_embedded_tests import leaves
            self.assertEqual(set(manifest['node_ids']),{node['id'] for node in leaves(tree)})
            review=json.loads((directory/'review.json').read_text())
            self.assertEqual({r['node_id'] for r in review['cases']},set(manifest['node_ids']))
            self.assertTrue(all(r['runtime_status']=='not_run_against_product' for r in review['cases']))

    def test_integration_cases_are_retained_without_becoming_first_node_gates(self):
        from acceptance import map_specs_to_nodes
        from audit_embedded_tests import leaves, validate_plan
        for name in NAMES.values():
            directory=ROOT/'derived-tests'/name
            tree=yaml.safe_load((directory/'requirements.yaml').read_text())
            nodes={node['id']:node for node in leaves(tree)}
            plan=json.loads((directory/'case-plan.json').read_text())
            specs=sorted(p.name for p in directory.glob('*.spec.ts'))
            validate_plan(plan,nodes,{p.removesuffix('.spec.ts') for p in specs})
            mapping,aliases=map_specs_to_nodes(specs,list(nodes))
            integrations=[p for p in specs if p.startswith('INTEGRATION-')]
            self.assertTrue(integrations)
            self.assertEqual(mapping[None],integrations)
            self.assertEqual(aliases,{})
            self.assertTrue(all(mapping[nid]==[nid+'.spec.ts'] for nid in nodes))
            manifest=json.loads((directory/'suite-origin.json').read_text())
            self.assertEqual(manifest['node_case_count']+manifest['integration_case_count'],len(plan))
            self.assertEqual(manifest['node_spec_count']+manifest['integration_spec_count'],len(specs))
        first=(ROOT/'derived-tests/hackathon--sheet/REQ-1-1-1.spec.ts').read_text()
        for later in ['h.edit(', 'h.blank(', 'h.validation(', 'h.pivot(']:
            self.assertNotIn(later,first)
        first=(ROOT/'derived-tests/hackathon--github/REQ-1-1-1.spec.ts').read_text()
        self.assertNotIn('h.signIn(',first)

    def test_each_integration_assertion_has_an_independent_exportable_node_witness(self):
        import build_embedded_tests
        from requirement_order import topo_order
        for name in NAMES.values():
            tree=yaml.safe_load((ROOT/'tasks'/name/'requirements.yaml').read_text())
            order={node['id']:i for i,node in enumerate(topo_order(tree))}
            recipes=build_embedded_tests.CASES[name]
            for file,rows in recipes.items():
                if not file.startswith('INTEGRATION-'): continue
                for source in rows:
                    candidates=[row for node,rs in recipes.items() if node.startswith('REQ-') for row in rs
                                if row.get('origin_file') == file+'.spec.ts'
                                and row.get('origin_title') == file+': '+source['title']]
                    self.assertEqual(len(candidates),1,(name,file,source['title']))
                    witness=candidates[0]
                    self.assertEqual(witness['phase'],'node')
                    self.assertEqual(witness['node_id'],max(source['requires'],key=order.__getitem__))
                    expected=source['body']
                    if source.get('fixture'):
                        self.assertNotEqual(witness['fixture'],source['fixture'])
                        expected=expected.replace("'"+source['fixture']+"'", "'"+witness['fixture']+"'")
                    self.assertEqual(witness['body'],expected)
                    self.assertEqual(witness['requires'],source['requires'])

    def test_local_requirement_export_preserves_each_witness_and_binds_only_present_specs(self):
        from export_node_tests import export
        from embedded_suites import PROJECT_EXPORT_POLICY
        for name in NAMES.values():
            destination=self.root/name
            manifest=export(ROOT/'derived-tests'/name,destination)
            self.assertEqual(manifest['export_policy'],PROJECT_EXPORT_POLICY)
            self.assertEqual(manifest['case_count'],manifest['node_case_count'])
            self.assertEqual(manifest['integration_case_count'],0)
            self.assertFalse(list(destination.glob('INTEGRATION-*.spec.ts')))
            plan=json.loads((destination/'case-plan.json').read_text())
            self.assertTrue(all(row['phase']=='node' for row in plan))
            self.assertTrue(any(row.get('origin_file') for row in plan))
            self.assertEqual(manifest,export(ROOT/'derived-tests'/name,destination))

    def test_local_export_refuses_to_overwrite_modified_or_unrelated_project_files(self):
        from export_node_tests import export
        source=ROOT/'derived-tests/hackathon--sheet'
        destination=self.root/'project-export'
        export(source,destination)
        original=(destination/'helpers.ts').read_bytes()
        (destination/'helpers.ts').write_text('user edit')
        with self.assertRaises(ValueError): export(source,destination)
        self.assertEqual((destination/'helpers.ts').read_text(),'user edit')
        (destination/'helpers.ts').write_bytes(original)
        (destination/'user-file.txt').write_text('keep')
        with self.assertRaises(ValueError): export(source,destination)
        self.assertEqual((destination/'user-file.txt').read_text(),'keep')

    def test_plan_rejects_unknown_requirements_wrong_phase_and_lost_atomic_gate(self):
        from copy import deepcopy
        from audit_embedded_tests import leaves, validate_plan
        nodes={node['id']:node for node in leaves(self.tree)}
        plan=json.loads((self.directory/'case-plan.json').read_text())
        specs={p.name.removesuffix('.spec.ts') for p in self.directory.glob('*.spec.ts')}
        row=next(i for i,r in enumerate(plan) if r['phase']=='integration')
        for field,value in [('phase','node'),('requires',['REQ-missing'])]:
            changed=deepcopy(plan); changed[row][field]=value
            with self.assertRaises(AssertionError): validate_plan(changed,nodes,specs)
        with self.assertRaises(AssertionError): validate_plan(plan,nodes,specs-{'REQ-1-1-1'})

    def test_curated_recipes_reproduce_exact_reviewed_spec_and_plan_bytes(self):
        import build_embedded_tests
        output=self.root/'recipes'
        for name in NAMES.values(): (output/name).mkdir(parents=True)
        with patch.object(build_embedded_tests,'ROOT',output): build_embedded_tests.build()
        for name in NAMES.values():
            expected=ROOT/'derived-tests'/name
            for generated in (output/name).iterdir():
                self.assertEqual(generated.read_bytes(),(expected/generated.name).read_bytes(),(name,generated.name))

    def test_sheet_node_gates_use_only_already_available_ui_capabilities(self):
        from embedded_case_phases import sheet_features, partition_sheet_cases
        from requirement_order import topo_order
        import build_embedded_tests
        order={n['id']:i for i,n in enumerate(topo_order(self.tree))}
        for file,recipes in build_embedded_tests.CASES['hackathon--sheet'].items():
            for row in recipes:
                self.assertLessEqual(sheet_features(row['body']),set(row['requires']))
                if row['phase']=='node':
                    self.assertTrue(all(order[rid]<=order[row['node_id']] for rid in row['requires']),row['title'])
        recipe={'node_id':'REQ-3-2-1','title':'copy formula','body':"await h.edit(page,'A1','=B1'); await page.keyboard.press('Control+c');",'requires':['REQ-3-2-1'],'phase':'node','fixture':None}
        deferred=partition_sheet_cases({'REQ-3-2-1':[recipe]},self.tree)
        self.assertEqual(list(deferred),['INTEGRATION-deferred-3-2-1'])
        self.assertIn('REQ-4-1-2',next(iter(deferred.values()))[0]['requires'])
        from audit_embedded_tests import leaves,validate_plan
        plan=json.loads((self.directory/'case-plan.json').read_text())
        next(row for row in plan if row['node_id']=='REQ-1-1-1')['requires'].append('REQ-5-3-1')
        with self.assertRaisesRegex(AssertionError,'later capability'):
            validate_plan(plan,{n['id']:n for n in leaves(self.tree)},{p.name.removesuffix('.spec.ts') for p in self.directory.glob('*.spec.ts')})

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

    def test_unknown_task_requests_prompt_generation_then_falls_back(self):
        with patch('embedded_suites.subprocess.run',return_value=Mock(returncode=1,stdout='{"trusted":false}')) as run:
            self.assertIsNone(materialize('octos',{'name':'another task'},self.root))
        command=run.call_args.args[0]
        self.assertEqual(command[:3],['octos','arc','generate-test-suite'])
        self.assertIn('For task "another task"',command[command.index('--prompt')+1])
        self.assertIn('--exclude-integration',command)
        self.assertFalse((self.root/'derived-tests').exists())

    def test_embedded_export_uses_derived_tests_and_preserves_existing_user_directories(self):
        from embedded_suites import project_destination, PROJECT_EXPORT_POLICY
        target=project_destination(self.root,self.tree,'hackathon--sheet')
        self.assertEqual(target,self.root/'derived-tests')
        target.mkdir(); (target/'user.txt').write_text('keep')
        self.assertEqual(project_destination(self.root,self.tree,'hackathon--sheet'),self.root/'derived-tests-2')
        reusable=self.root/'derived-tests-2'; reusable.mkdir()
        (reusable/'suite-origin.json').write_text(json.dumps({'name':'hackathon--sheet','requirements_sha256':requirements_digest(self.tree),'export_policy':PROJECT_EXPORT_POLICY}))
        self.assertEqual(project_destination(self.root,self.tree,'hackathon--sheet'),reusable)
        self.assertEqual((target/'user.txt').read_text(),'keep')

    def test_failed_generation_falls_back_for_explicit_and_automatic_names(self):
        with patch('embedded_suites.subprocess.run',return_value=Mock(returncode=1,stdout='{"trusted":false}')) as run:
            self.assertIsNone(materialize('octos',self.tree,self.root,'unknown'))
            changed={**self.tree,'description':'different'}
            self.assertIsNone(materialize('octos',changed,self.root))
            self.assertIsNone(materialize('octos',changed,self.root,'hackathon--sheet'))
            self.assertEqual(run.call_count,3)

    def test_old_binary_command_failure_uses_the_mechanical_fallback(self):
        with patch('embedded_suites.subprocess.run',return_value=Mock(returncode=2,stdout='')):
            self.assertIsNone(materialize('old-octos',self.tree,self.root))
            self.assertIsNone(materialize('old-octos',self.tree,self.root,'hackathon--sheet'))

    def test_only_true_octos_receipt_can_attest_trusted_tests_and_contracts(self):
        for trusted in [False, None, 'true', 1]:
            with self.subTest(trusted=trusted), patch('embedded_suites.subprocess.run',return_value=
                Mock(returncode=0,stdout=json.dumps({'trusted':trusted}))):
                self.assertIsNone(materialize('octos',self.tree,self.root,'hackathon--sheet'))

    def test_failed_octos_generation_enters_the_existing_mechanical_pipeline(self):
        flow=Flow(argparse.Namespace(web_port=3000,trusted_tests=True),self.root,self.root/'requirements')
        flow.original_requirement_tree={'id':'ROOT','name':'unknown task','type':'FOLDER','children':[]}
        layer=Mock()
        flow.prepare_derived_tests=Mock(return_value=True)
        flow.adopt_derived_specs=Mock()
        with patch('main.locate_acceptance_tests',return_value=None), patch('main.find_octos',return_value='octos'), \
                patch('embedded_suites.materialize',return_value=None) as generate, \
                patch('layered_tests.LayeredTests',return_value=layer):
            flow.prepare_test_spec_source(flow.original_requirement_tree,[])
        generate.assert_called_once()
        flow.prepare_derived_tests.assert_called_once_with([])
        flow.adopt_derived_specs.assert_called_once_with([])
        self.assertFalse(flow.test_specs_trusted)
        self.assertIs(flow.layered,layer)

    def test_trusted_run_generates_and_tests_each_node_without_spec_queues(self):
        flow,runtime=self._run_trusted_source_flow()
        from requirement_order import topo_order
        ids=[row['id'] for row in topo_order(self.tree)]
        self.assertEqual([call.args[0] for call in flow.acceptance_loop.call_args_list],ids)
        self.assertEqual(flow.turn.call_count,len(ids))
        self.assertTrue(all(flow.test_verdict[node] is True for node in ids))
        self.assertTrue(flow.test_specs_trusted)
        self.assertIsNone(flow.layered)
        self.assertFalse(flow.derived_as_specs)
        flow.batch_codegen.assert_not_called()
        runtime.events.mark_run_completed.assert_called_once()

    def test_runnable_delivery_survives_final_suite_timeout_without_promoting_verdicts(self):
        for verdict in (False,None):
            with self.subTest(verdict=verdict):
                flow,runtime=self._run_trusted_source_flow(verdict=verdict,final_timeout=True)
                self.assertTrue(flow.test_verdict)
                self.assertTrue(all(value is verdict for value in flow.test_verdict.values()))
                self.assertFalse(flow.final_suite_green)
                runtime.events.mark_run_failed.assert_not_called()
                runtime.events.mark_run_completed.assert_called_once()
                message=runtime.events.mark_run_completed.call_args.args[0]
                self.assertIn('runnable application delivered',message)
                self.assertIn('local verification incomplete',message)
                flow.write_preview_ready.assert_called_once()
                flow.run_specs.assert_called_once()

    def test_confirmed_startup_failure_is_submitted_without_claiming_ready(self):
        flow,runtime=self._run_trusted_source_flow(verdict=False,rehearsed=False)
        runtime.events.mark_run_failed.assert_not_called()
        runtime.events.mark_run_completed.assert_called_once()
        flow.write_preview_ready.assert_not_called()

    def test_model_failure_and_cleanup_failure_preserve_unknowns_and_submit(self):
        for error in [RuntimeError('model requests continuously failed'), SystemExit(1)]:
            with self.subTest(error=type(error).__name__):
                flow,runtime=self._run_trusted_source_flow(turn_error=error,cleanup_error=OSError('cleanup unavailable'))
                runtime.events.mark_run_failed.assert_not_called()
                runtime.events.mark_run_completed.assert_called_once()
                self.assertTrue(flow.test_verdict)
                self.assertTrue(all(value is None for value in flow.test_verdict.values()))
                record=json.loads((self.root/'.arc/delivery-state.json').read_text())
                self.assertEqual(record['verification_state'],'incomplete')
                self.assertEqual(record['model_calls_during_handoff'],0)
                self.assertEqual(flow.turn.call_count,1)

    def _run_trusted_source_flow(self,verdict=True,rehearsed=True,final_timeout=False,turn_error=None,cleanup_error=None,suite_name='hackathon--sheet'):
        """Exercise coordinator + real node_cycle; model and product execution are stubbed."""
        flow=Flow(argparse.Namespace(web_port=3000,trusted_tests=True,test_suite=suite_name),self.root,self.root/'requirements')
        runtime=SimpleNamespace(events=Mock(),traceability=Mock(),git=Mock())
        runtime.traceability.list_interfaces.return_value=[]
        flow.runner=Mock()
        flow.metric=Mock()
        flow.resolve_seed_conflicts=Mock(return_value=self.tree)
        flow.remaining=Mock(return_value=10000)
        flow.final_phase_due=Mock(return_value=False)
        flow.node_start_budget_available=flow.admit_node=Mock(return_value=True)
        flow.codegen_mode=Mock(return_value=False)
        flow.head=Mock(return_value='source')
        flow.has_app=Mock(return_value=True)
        from source_index import SourceIndex
        flow.repair_source_index=Mock(return_value=SourceIndex({}))
        flow.app_source_digest=Mock(return_value='source')
        flow.corrections_text=Mock(return_value='')
        flow.turn=Mock(return_value=(True,'generated node source'),side_effect=turn_error)
        flow.acceptance_loop=Mock(return_value=verdict)
        flow.rehearsal=Mock(return_value=rehearsed)
        flow.batch_codegen=Mock(side_effect=AssertionError('One node at a time'))
        for name in ['maybe_probe','setup_playwright','start_llm_proxy','prepare_build',
                     'prime_generation_dependencies','snapshot_protected','record_implementation_evidence',
                     'mark','commit','regression_checkpoint','log_usage_checkpoint','final_acceptance_passes',
                     'postflight','write_quality_summary','mark_folders','write_preview_ready']:
            setattr(flow,name,Mock())
        if cleanup_error:
            flow.postflight.side_effect=cleanup_error
        if final_timeout:
            from acceptance import RunSummary
            flow.run_specs=Mock(return_value=RunSummary(error='playwright run exceeded 900s'))
            flow.verify_repair_memory=Mock()
            def time_out_final_suite():
                if getattr(flow,'_final_suite_attempted',False):
                    return
                flow._final_suite_attempted=True
                Flow.final_acceptance(flow)
            flow.final_acceptance_passes=Mock(side_effect=time_out_final_suite)
        for name in ['prepare_derived_tests','start_background_specs','close_background_specs',
                     'pre_review_derived_system_check','review_derived_after_implementation',
                     'design','inline_design_instruction','review_domain_design']:
            setattr(flow,name,Mock(side_effect=AssertionError(f'Trusted run must skip {name}')))
        manifest=verify_directory(self.directory,self.tree,suite_name)
        with patch('main.AgentRuntime.from_env',return_value=runtime), \
                patch('main.load_requirement_tree',return_value=self.tree), \
                patch('main.previous_requirement_records',return_value={}), \
                patch('main.locate_acceptance_tests',return_value=None), patch('main.find_octos',return_value='octos'), \
                patch('embedded_suites.materialize',return_value=(self.directory,manifest)), \
                patch('layered_tests.LayeredTests',side_effect=AssertionError('No basic/business coordinator')), \
                patch('main.build_octos_env',return_value={}), patch('main.write_profile_defaults'), \
                patch('main._port_watchdog'), patch('main._reap_stray_processes'), patch('main.reap_workspace_processes'), \
                patch('main._postflight_structure_check'), patch('main._free_web_port'), \
                patch.dict('os.environ',{'OCTOS_ARC_DRYRUN':'1','OCTOS_ARC_SIBLING_BATCH_SIZE':'24',
                                         'OCTOS_FINAL_REPAIR_ROUNDS':'0'}):
            self.assertEqual(flow.run(),0)
        return flow,runtime

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
        self.assertIn('SOURCE-REVIEWED INTERNAL DERIVED',prompt); self.assertIn('fixtures.json',prompt)
        self.assertIn('not official benchmark tests',prompt)
        self.assertIn('app-design.json',prompt); self.assertIn('test-obligations.json',prompt)
        self.assertIn('source-reviewed internal derived',flow.verify_text(24))
        flow.runner=Mock(); (self.directory/'helpers.ts').write_text('changed')
        result=flow.run_specs(['REQ-1-1-1.spec.ts'])
        self.assertIn('Derived test suite integrity check failed',result.error); flow.runner.run.assert_not_called()

if __name__=='__main__': unittest.main()
