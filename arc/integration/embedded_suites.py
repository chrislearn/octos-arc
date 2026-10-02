#!/usr/bin/env python3
"""Actual CLI -> Python -> protected suite -> Playwright staging, no model call."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import Mock
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from acceptance import AcceptanceRunner, map_specs_to_nodes
from embedded_suites import verify_directory, PROJECT_EXPORT_POLICY
from octos_tests import generate_test_suite
from main import Flow


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('binary'); parser.add_argument('output'); args=parser.parse_args()
    binary=str(Path(args.binary).resolve()); output=Path(args.output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['OCTOS_DATA_DIR']=str(output/'kernel-data'); os.environ['OCTOS_CONFIG_DIR']=str(output/'kernel-config')
    catalogue=json.loads(subprocess.check_output([binary,'arc','tests','--list'],text=True))
    evidence=[]
    for name in catalogue['suites']:
        tree=yaml.safe_load((ROOT/'tasks'/name/'requirements.yaml').read_text())
        workspace=output/name; workspace.mkdir(exist_ok=True)
        directory,manifest=generate_test_suite(binary,tree,workspace,name,print)
        manifest=verify_directory(directory,tree,name)
        requirements=workspace/'requirements'; shutil.copytree(ROOT/'tasks'/name,requirements,dirs_exist_ok=True)
        flow=Flow(argparse.Namespace(web_port=3000),workspace,requirements); flow.metric=Mock()
        flow.tests_dir=directory; flow.frozen_suite=manifest; flow.original_requirement_tree=tree; flow.adopt_frozen_business()
        specs=sorted(p.name for p in directory.glob('*.spec.ts'))
        assert directory==workspace/'derived-tests'
        assert manifest['export_policy']==PROJECT_EXPORT_POLICY
        assert manifest['ignored_specs'] and not any(p.startswith('INTEGRATION-') for p in specs)
        plan=json.loads((directory/'case-plan.json').read_text())
        assert len(plan)==manifest['case_count'] and all(r['phase']=='node' for r in plan)
        flow.spec_map,flow.aliases=map_specs_to_nodes(specs,manifest['node_ids'])
        assert flow.spec_map[None]==[]
        assert not flow.prepare_derived_tests([]); flow.start_background_specs([{'id':manifest['node_ids'][0]}])
        prompt=flow.tests_prompt_for(manifest['node_ids'][0]); assert 'OCTOS TEST SUITE' in prompt
        flow.snapshot_protected(); helper=directory/'helpers.ts'; original=helper.read_bytes(); helper.write_text('attempted model rewrite')
        assert flow.restore_protected(); assert helper.read_bytes()==original
        verify_directory(directory,tree,name)
        runner=AcceptanceRunner(output/'playwright',directory,output/'execution'/name,print)
        runner._prepare(); staged=runner.work_dir/'tests'/specs[0]
        assert not list((runner.work_dir/'tests').rglob('INTEGRATION-*.spec.ts'))
        assert '__octosObservePageErrors' in staged.read_text(); verify_directory(directory,tree,name)
        for _,snapshot,_ in flow.protected_snapshots: shutil.rmtree(snapshot.parent,ignore_errors=True)
        evidence.append({'name':name,'trusted':manifest['trusted'],'spec_count':len(specs),'case_count':manifest['case_count'],
                         'directory':str(directory),'export_policy':manifest['export_policy'],'ignored_spec_count':len(manifest['ignored_specs']),
                         'source_spec_count':manifest['source_spec_count'],'source_case_count':manifest['source_case_count'],
                         'reviewed':True,'frozen':True,'protection_restore':'passed','playwright_staging':'passed','business_model_entities':len(flow.app_design_doc['data_model']),'business_model_reuse':'passed','product_execution':'not_run'})
    unsupported=output/'unsupported'
    response=subprocess.run([binary,'arc','generate-test-suite','--prompt','Read /task/requirements.yaml. For task "unknown", generate test specs and contracts.',
                             '--requirements-sha256','unavailable','--output-dir',str(unsupported)],capture_output=True,text=True)
    assert response.returncode!=0 and json.loads(response.stdout)['trusted'] is False and not unsupported.exists()
    evidence.append({'name':'unknown','generation':'failed','trusted':False,'files_written':False,'product_execution':'not_run'})
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n'); print(json.dumps(evidence,indent=2))

if __name__=='__main__': main()
