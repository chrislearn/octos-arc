"""Select and verify source-reviewed suites materialized by the Rust binary.

This module contains names, never spec bytes. Unknown tasks use the existing
requirement-derived pipeline. GitHub tasks always reuse the existing GitHub suite;
other known suites must match the ORIGINAL tree.
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
from pathlib import Path

NAMES = {
    'GitHub Collaboration Platform Core Requirements': 'hackathon--github',
    'Core Requirements for an Online Spreadsheet Data Workspace': 'hackathon--sheet',
}
PROJECT_EXPORT_POLICY = 'node_specs_only_integration_temporarily_ignored'

def project_destination(output_dir: Path, tree: dict, name: str | None) -> Path:
    """Share the derived-tests namespace without overwriting an existing user's files."""
    for index in range(100):
        destination = output_dir.resolve() / ('derived-tests' if index == 0 else f'derived-tests-{index + 1}')
        if not destination.exists() and not destination.is_symlink():
            return destination
        marker = destination / 'suite-origin.json'
        if destination.is_symlink() or marker.is_symlink() or not marker.is_file():
            continue
        try:
            origin = json.loads(marker.read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        if (origin.get('name') == name
                and (name == 'hackathon--github' or origin.get('requirements_sha256') == requirements_digest(tree))
                and origin.get('export_policy') == PROJECT_EXPORT_POLICY):
            return destination
    raise ValueError('No unused derived-tests directory available for embedded tests')

def requirements_digest(tree: dict) -> str:
    return hashlib.sha256(json.dumps(tree, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf8')).hexdigest()

def requested_name(tree: dict, explicit: str | None = None) -> str | None:
    task = explicit or str(tree.get('name') or tree.get('id') or '').strip()
    identities = [explicit] if explicit else [tree.get('name', ''), tree.get('id', '')]
    if any('github' in str(identity).casefold() for identity in identities):
        return 'hackathon--github'
    return explicit or NAMES.get(task)

def prefer_embedded(args) -> bool:
    return bool(getattr(args, 'trusted_tests', False)) or os.environ.get('OCTOS_ARC_TRUSTED_TESTS') == '1'

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

def materialize(binary: str, tree: dict, output_dir: Path, explicit: str | None = None,
                log=lambda message: None, *, requirements_path: Path | None = None) -> tuple[Path, dict] | None:
    name = requested_name(tree, explicit)
    task = name or explicit or str(tree.get('name') or tree.get('id') or 'unknown task')
    source = requirements_path or output_dir / 'requirements' / 'requirements.yaml'
    prompt = (f'Read the requirements in {json.dumps(str(source), ensure_ascii=False)}. '
              f'For task {json.dumps(task, ensure_ascii=False)}, generate the complete Playwright test suite spec, '
              'shared business model, domain contracts, requirement constraints and test obligations. '
              'Return whether all generated tests and contracts are trusted.')
    destination = project_destination(output_dir, tree, name)
    result = subprocess.run([binary, 'arc', 'generate-test-suite', '--prompt', prompt,
                             '--output-dir', str(destination), '--requirements-sha256', requirements_digest(tree),
                             '--exclude-integration'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        log(f'[tests] octos generate-test-suite failed; using mechanical spec generation: {result.stdout.strip()[:500]}')
        return None
    receipt = json.loads(result.stdout)
    if receipt.get('trusted') is not True:
        log('[tests] octos did not return trusted=true; using mechanical spec generation')
        return None
    actual_name = receipt.get('name')
    if actual_name not in NAMES.values() or (name and actual_name != name) or Path(receipt.get('directory', '')).resolve() != destination:
        raise ValueError('Embedded suite extraction receipt mismatch')
    if hashlib.sha256((destination / 'suite-origin.json').read_bytes()).hexdigest() != receipt.get('manifest_sha256'):
        raise ValueError('Derived test suite manifest differs from the embedded extraction receipt')
    manifest = verify_directory(destination, tree, actual_name)
    if (manifest.get('export_policy') != PROJECT_EXPORT_POLICY
            or receipt.get('export_policy') != PROJECT_EXPORT_POLICY
            or any(Path(path).name.startswith('INTEGRATION-') for path in manifest['files'])):
        raise ValueError('Embedded binary exported temporarily disabled integration specs')
    log(f'[tests] octos generated trusted derived-tests for {actual_name}: {manifest["spec_count"]} specs / {manifest["case_count"]} cases; integration specs temporarily omitted')
    return destination, manifest


def generation_note(directory: Path) -> str:
    return (f'SOURCE-REVIEWED INTERNAL DERIVED TEST SUITE at {directory}. '
            'All cases were reviewed against the suite source requirements before this run; do not regenerate or edit them. '
            'Integration specs are retained internally but temporarily excluded from this project export; use only the exported node specs. '
            'Octos attested trusted=true for these tests and business contracts; skip online spec generation, review, audit and waiting queues. '
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
