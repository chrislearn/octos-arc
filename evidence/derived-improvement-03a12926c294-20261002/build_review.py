"""Verify the delivered suite against the immutable downloaded baseline."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO/'arc'))
from embedded_suites import verify_directory

old = ROOT.parent/'derived-audit-03a12926c294-20261002/template/derived-tests'
new = ROOT/'derived-tests'
source = REPO/'arc/derived-tests/hackathon--sheet'
tree = yaml.safe_load((new/'requirements.yaml').read_text())
old_manifest = verify_directory(old, tree, 'hackathon--sheet')
new_manifest = verify_directory(new, tree, 'hackathon--sheet')
source_manifest = verify_directory(source, tree, 'hackathon--sheet')
old_plan = json.loads((old/'case-plan.json').read_text())
new_plan = json.loads((new/'case-plan.json').read_text())
old_titles = {row['title'] for row in old_plan}
new_titles = {row['title'] for row in new_plan}
assert old_titles <= new_titles
assert (old/'requirements.yaml').read_bytes() == (new/'requirements.yaml').read_bytes()
assert source_manifest['case_count'] == 196 and new_manifest['case_count'] == 143
assert new_manifest['spec_count'] == 24 and len(new_titles-old_titles) == 12
def origins(plan):
    return {(row['origin_file'], row['origin_title'], row['origin_node_id'])
            for row in plan if row.get('origin_file')}
assert origins(old_plan) == origins(new_plan) and len(origins(new_plan)) == 53
zip_path = ROOT/'derived-tests-improved.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(new.iterdir()):
        archive.write(path, 'derived-tests/'+path.name)
summary = {
    'run': 'https://arc-bench.com/runs/03a12926c294',
    'requirements_unchanged_byte_for_byte': True,
    'old_exported_cases': old_manifest['case_count'],
    'new_exported_cases': new_manifest['case_count'],
    'source_cases': source_manifest['case_count'],
    'atomic_nodes': new_manifest['spec_count'],
    'spec_revision': new_manifest['spec_revision'],
    'all_original_exported_titles_retained': True,
    'integration_context_origins_retained': len(origins(new_plan)),
    'source_and_export_hash_verification': 'passed',
    'added_cases': [{'file':row['file'],'title':row['title']}
                    for row in new_plan if row['title'] not in old_titles],
    'archive_sha256': hashlib.sha256(zip_path.read_bytes()).hexdigest(),
    'product_runtime_certified': False,
    'complete_semantic_coverage_claimed': False,
    'delivery': 'local refreshed export; remote run and installed binary unchanged',
}
(ROOT/'review-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='added_cases'}, ensure_ascii=False, indent=2))
