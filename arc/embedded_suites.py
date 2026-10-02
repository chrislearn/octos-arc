"""Development-only catalogue and audit helpers for test source files.

This module is not shipped in the submission bundle.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

NAMES = {
    'GitHub Collaboration Platform Core Requirements': 'hackathon--github',
    'Core Requirements for an Online Spreadsheet Data Workspace': 'hackathon--sheet',
}
PROJECT_EXPORT_POLICY = 'node_specs_only_integration_temporarily_ignored'

def requirements_digest(tree: dict) -> str:
    return hashlib.sha256(json.dumps(tree, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf8')).hexdigest()

def verify_directory(directory: Path, tree: dict, name: str, expected_manifest: dict | None = None) -> dict:
    if directory.is_symlink() or (directory / 'suite-origin.json').is_symlink():
        raise ValueError('Symlink in suite')
    manifest = json.loads((directory / 'suite-origin.json').read_text(encoding='utf8'))
    if expected_manifest is not None and manifest != expected_manifest:
        raise ValueError('Derived test suite manifest changed after extraction')
    if (manifest.get('name') != name
            or (name != 'hackathon--github' and manifest.get('requirements_sha256') != requirements_digest(tree))
            or manifest.get('official') is not False or manifest.get('frozen') is not True
            or manifest.get('review_status') != 'reviewed' or manifest.get('trusted') is not True):
        raise ValueError('Embedded derived test suite identity/review mismatch')
    files = manifest.get('files') or {}
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(files) | {'suite-origin.json'}:
        raise ValueError('Embedded suite has missing or unexpected files')
    for rel, digest in files.items():
        target = Path(rel)
        if target.is_absolute() or '..' in target.parts or '\\' in rel:
            raise ValueError('Unsafe suite path')
        source = directory / target
        if source.is_symlink() or any(p.is_symlink() for p in source.parents):
            raise ValueError('Symlink in suite')
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Derived test suite file changed: {rel}')
    review = json.loads((directory / 'review.json').read_text(encoding='utf8'))
    cases = review.get('cases') or []
    if len(cases) != manifest.get('case_count') or not cases:
        raise ValueError('Derived test suite review case count mismatch')
    if any(row.get('status') != 'reviewed' or row.get('frozen') is not True
           or row.get('file_sha256') != files.get(row.get('file')) for row in cases):
        raise ValueError('Derived test suite contains unreviewed/modified cases')
    business = json.loads((directory / 'business-review.json').read_text(encoding='utf8'))
    if (business.get('review_status') != 'reviewed' or business.get('frozen') is not True
            or business.get('official') is not False
            or business.get('requirements_sha256') != manifest['requirements_sha256']
            or any(business.get('files', {}).get(rel) != files.get(rel) or rel not in files
                   for rel in ['app-design.json', 'domain-contracts.json', 'requirement-contracts.json', 'test-obligations.json'])):
        raise ValueError('Derived test suite business model review/hash mismatch')
    return manifest
