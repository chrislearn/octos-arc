"""Public suite paths retain protection, loading and data-cleanup boundaries."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from acceptance import AcceptanceRunner
from main import Flow


class ExportedSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        requirements=self.root/'requirements'; requirements.mkdir()
        self.flow=Flow(argparse.Namespace(web_port=3000),self.root,requirements)
        self.flow.metric=Mock(); self.flow.write_derived_coverage=Mock()
        self.source="import {test,expect} from '@playwright/test';\ntest('works',()=>expect(1).toBe(1));\n"
        self.nodes=[{'id':'A','type':'ATOMIC','description':'Increment a counter.'}]

    def compile(self):
        with patch('main.compile_derived_suite',return_value={'A.spec.ts':self.source,'helpers.ts':'export {};\n'}):
            self.assertTrue(self.flow.prepare_derived_tests(self.nodes))
        return self.flow.derived_tests_dir

    def test_root_suite_is_authoritative_and_protected_even_before_adoption(self):
        directory=self.compile()
        self.assertEqual(directory,self.root/'derived-tests')
        self.assertIn('derived-tests/',self.flow.protected_prefixes())
        self.flow.snapshot_protected()
        for _,snap,_ in self.flow.protected_snapshots:
            self.addCleanup(shutil.rmtree,snap.parent,ignore_errors=True)
        (directory/'A.spec.ts').write_text('weakened spec')
        self.assertTrue(self.flow.restore_protected())
        self.assertEqual((directory/'A.spec.ts').read_text(),self.source)
        self.flow.adopt_derived_specs(['A'])
        self.assertEqual(self.flow.tests_dir,directory)
        self.assertEqual(self.flow.spec_map['A'],['A.spec.ts'])
        runner=AcceptanceRunner(self.root/'playwright',self.flow.tests_dir,self.root/'execution',lambda _:None)
        runner._prepare()
        staged=(runner.work_dir/'tests/A.spec.ts').read_text()
        self.assertTrue(staged.startswith(self.source))
        self.assertIn('__octosObservePageErrors',staged)
        self.assertEqual((directory/'A.spec.ts').read_text(),self.source)

    def test_postflight_data_cleanup_keeps_specs_and_custom_app_data(self):
        directory=self.compile()
        runtime=self.root/'.arc/runtime-data/acceptance'; runtime.mkdir(parents=True)
        (runtime/'test.json').write_text('{}')
        custom=self.root/'backend/data';custom.mkdir(parents=True)
        (custom/'user.json').write_text('{"preserve":true}')
        self.flow.discard_runtime_store()
        self.assertFalse(runtime.exists())
        self.assertTrue((custom/'user.json').exists())
        self.assertEqual((directory/'A.spec.ts').read_text(),self.source)
        self.assertFalse(json.loads((directory/'suite-origin.json').read_text())['official'])

    def test_existing_user_directory_is_not_removed(self):
        existing=self.root/'derived-tests';existing.mkdir();(existing/'user.txt').write_text('keep')
        directory=self.compile()
        self.assertEqual(directory,self.root/'derived-tests-2')
        self.assertEqual((existing/'user.txt').read_text(),'keep')
        (directory/'obsolete.spec.ts').write_text('previous generated suite')
        self.assertEqual(self.compile(),directory)
        self.assertFalse((directory/'obsolete.spec.ts').exists())
        self.assertTrue((existing/'user.txt').exists())

    def test_symlink_directory_is_never_recursively_removed(self):
        elsewhere=self.root/'real';elsewhere.mkdir();(elsewhere/'keep').write_text('keep')
        (self.root/'derived-tests').symlink_to(elsewhere,target_is_directory=True)
        self.assertEqual(self.compile(),self.root/'derived-tests-2')
        self.assertTrue((elsewhere/'keep').exists())

if __name__=='__main__': unittest.main()
