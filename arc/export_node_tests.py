#!/usr/bin/env python3
"""Refresh a local project's verified requirement-only test export.

Applies the same filtering/count/hash policy as Rust project_content. This is
an explicit local refresh, not a binary extraction receipt or runtime attestation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import yaml
from embedded_suites import PROJECT_EXPORT_POLICY, verify_directory


def export(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.absolute()
    tree = yaml.safe_load((source / 'requirements.yaml').read_text())
    name = json.loads((source / 'suite-origin.json').read_text())['name']
    manifest = verify_directory(source, tree, name)
    if destination == source or source in destination.parents:
        raise ValueError('Project export must be outside the source suite')
    if destination.exists() or destination.is_symlink():
        previous = verify_directory(destination, tree, name)
        if previous.get('export_policy') != PROJECT_EXPORT_POLICY:
            raise ValueError('Destination is not a known requirement-only project export')
    files = {p.name:p.read_bytes() for p in source.iterdir() if p.is_file() and p.name != 'suite-origin.json'}
    ignored = sorted(p for p in files if p.startswith('INTEGRATION-') and p.endswith('.spec.ts'))
    for path in ignored: del files[path]
    def encode(value): return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode()
    review = json.loads(files['review.json'])
    review['cases'] = [row for row in review['cases'] if row['file'] in files]
    files['review.json'] = encode(review)
    files['case-plan.json'] = encode([row for row in json.loads(files['case-plan.json']) if row['file'] in files])
    manifest.update(source_manifest_sha256=hashlib.sha256((source/'suite-origin.json').read_bytes()).hexdigest(),
                    source_case_count=manifest['case_count'], source_spec_count=manifest['spec_count'],
                    case_count=len(review['cases']), spec_count=sum(p.endswith('.spec.ts') for p in files),
                    integration_case_count=0, integration_spec_count=0,
                    export_policy=PROJECT_EXPORT_POLICY, ignored_specs=ignored,
                    files={p:hashlib.sha256(data).hexdigest() for p,data in sorted(files.items())})
    files['suite-origin.json'] = encode(manifest)
    destination.mkdir(parents=True, exist_ok=True)
    # The previous directory was hash-verified above; no untracked files are removed.
    for old in destination.iterdir():
        if old.name not in files: old.unlink()
    for path,data in files.items():
        temporary=destination/(path+'.tmp');temporary.write_bytes(data);temporary.replace(destination/path)
    return verify_directory(destination, tree, name)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args=parser.parse_args()
    manifest=export(args.source,args.destination)
    print(f"{manifest['name']}: {manifest['case_count']} cases / {manifest['spec_count']} requirement files")
