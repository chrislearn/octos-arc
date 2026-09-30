"""Select and verify source-reviewed suites materialized by the Rust binary.

This module contains names, never spec bytes. Unknown tasks use the existing
requirement-derived pipeline. Known suites must match the ORIGINAL tree.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path

NAMES = {
    'GitHub Collaboration Platform Core Requirements': 'hackathon--github',
    'Core Requirements for an Online Spreadsheet Data Workspace': 'hackathon--sheet',
}

def requirements_digest(tree: dict) -> str:
    return hashlib.sha256(json.dumps(tree, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf8')).hexdigest()

def requested_name(tree: dict, explicit: str | None = None) -> str | None:
    return explicit or NAMES.get(str(tree.get('name', '')).strip())

def verify_directory(directory: Path, tree: dict, name: str, expected_manifest: dict | None = None) -> dict:
    if directory.is_symlink() or (directory / 'suite-origin.json').is_symlink():
        raise ValueError('Symlink in suite')
    manifest = json.loads((directory / 'suite-origin.json').read_text(encoding='utf8'))
    if expected_manifest is not None and manifest != expected_manifest:
        raise ValueError('Frozen suite manifest changed after extraction')
    if (manifest.get('name') != name or manifest.get('requirements_sha256') != requirements_digest(tree)
            or manifest.get('official') is not False or manifest.get('frozen') is not True
            or manifest.get('review_status') != 'reviewed'):
        raise ValueError('Embedded frozen suite identity/review mismatch')
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
            raise ValueError(f'Frozen suite file changed: {rel}')
    review = json.loads((directory / 'review.json').read_text(encoding='utf8'))
    cases = review.get('cases') or []
    if len(cases) != manifest.get('case_count') or not cases:
        raise ValueError('Frozen suite review case count mismatch')
    if any(row.get('status') != 'reviewed' or row.get('frozen') is not True
           or row.get('file_sha256') != files.get(row.get('file')) for row in cases):
        raise ValueError('Frozen suite contains unreviewed/modified cases')
    business = json.loads((directory / 'business-review.json').read_text(encoding='utf8'))
    if (business.get('review_status') != 'reviewed' or business.get('frozen') is not True
            or business.get('official') is not False
            or business.get('requirements_sha256') != manifest['requirements_sha256']
            or any(business.get('files', {}).get(rel) != files.get(rel) or rel not in files
                   for rel in ['app-design.json', 'domain-contracts.json', 'requirement-contracts.json', 'test-obligations.json'])):
        raise ValueError('Frozen suite business model review/hash mismatch')
    return manifest

def materialize(binary: str, tree: dict, output_dir: Path, explicit: str | None = None,
                log=lambda message: None) -> tuple[Path, dict] | None:
    name = requested_name(tree, explicit)
    if not name:
        return None
    listing = subprocess.run([binary, 'arc', 'tests', '--list'], capture_output=True, text=True, timeout=30)
    if listing.returncode:
        if explicit:
            raise RuntimeError('This octos binary cannot list embedded suites; build the worktree binary')
        log('[tests] binary has no embedded-suite command; using existing spec generation')
        return None
    catalogue = json.loads(listing.stdout)
    entry = (catalogue.get('suites') or {}).get(name)
    if not entry:
        log(f'[tests] no embedded suite named {name}; using existing spec generation')
        return None
    fingerprint = requirements_digest(tree)
    if entry.get('requirements_sha256') != fingerprint:
        if explicit:
            raise ValueError(f'Requirements do not match frozen suite {name}')
        log(f'[tests] requirements differ from embedded {name}; using existing spec generation')
        return None
    if '/' in name or '\\' in name or name in {'.', '..'}:
        raise ValueError('Unsafe suite name')
    destination = output_dir.resolve() / '.arc' / 'frozen-tests' / name
    result = subprocess.run([binary, 'arc', 'tests', '--name', name, '--output-dir', str(destination),
                             '--requirements-sha256', fingerprint], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'Failed to materialize frozen suite {name}: {result.stderr.strip()[-2000:]}')
    receipt = json.loads(result.stdout)
    if receipt.get('name') != name or Path(receipt.get('directory', '')).resolve() != destination:
        raise ValueError('Embedded suite extraction receipt mismatch')
    if hashlib.sha256((destination / 'suite-origin.json').read_bytes()).hexdigest() != receipt.get('manifest_sha256'):
        raise ValueError('Frozen suite manifest differs from the embedded extraction receipt')
    manifest = verify_directory(destination, tree, name)
    log(f'[tests] embedded {name}: {manifest["spec_count"]} specs / {manifest["case_count"]} cases, source-reviewed and frozen')
    return destination, manifest


def generation_note(directory: Path) -> str:
    return (f'SOURCE-REVIEWED FROZEN INTERNAL TEST SUITE at {directory}. '
            'All cases were reviewed against the original requirements before this run; do not regenerate or edit them. '
            'Source review is not a measured test pass and these are not official benchmark tests. '
            'requirements.yaml remains the behavior authority; report a conflict rather than weakening the product. '
            f'Read {directory / "fixtures.json"} and {directory / "README.md"} before generation: '
            'they describe public UI seeds, role accounts and independent records. No reset/private API is required. '
            f'Use the reviewed shared business model in {directory / "app-design.json"}, '
            f'{directory / "domain-contracts.json"}, {directory / "requirement-contracts.json"} and '
            f'{directory / "test-obligations.json"} directly; do not regenerate or edit those frozen contracts. '
            'The model is a source-grounded design proposal; original requirements control behavior and implementation paths remain choices.\n')


def load_business(directory: Path) -> tuple[dict, dict, dict]:
    documents = [json.loads((directory / name).read_text(encoding='utf8'))
                 for name in ['app-design.json', 'requirement-contracts.json', 'test-obligations.json']]
    if any(doc.get('review_status') != 'reviewed' or doc.get('frozen') is not True
           or doc.get('official') is not False for doc in documents):
        raise ValueError('Frozen business model is not source-reviewed')
    return tuple(documents)
