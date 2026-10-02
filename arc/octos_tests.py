"""Request tests and business documents through the octos command."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


def project_destination(output_dir: Path) -> Path:
    """Choose a new output directory without inspecting or replacing user files."""
    for index in range(100):
        destination = output_dir.resolve() / ('derived-tests' if index == 0 else f'derived-tests-{index + 1}')
        if not destination.exists() and not destination.is_symlink():
            return destination
    raise ValueError('No unused derived-tests directory available')


def generate_test_suite(binary: str, tree: dict, output_dir: Path, explicit: str | None = None,
                        log=lambda message: None, *, requirements_path: Path | None = None) -> tuple[Path, dict] | None:
    task = explicit or ' '.join(dict.fromkeys(str(tree[key]) for key in ('name', 'id') if tree.get(key))) or 'unknown task'
    source = requirements_path or output_dir / 'requirements' / 'requirements.yaml'
    prompt = (f'Read the requirements in {json.dumps(str(source), ensure_ascii=False)}. '
              f'For task {json.dumps(task, ensure_ascii=False)}, generate the complete Playwright test suite spec, '
              'shared business model, domain contracts, requirement constraints and test obligations. '
              'Return whether all generated tests and contracts are trusted.')
    destination = project_destination(output_dir)
    # This identifies the input to the command; test contents are owned by octos.
    fingerprint = hashlib.sha256(json.dumps(tree, ensure_ascii=False, sort_keys=True,
                                            separators=(',', ':')).encode('utf8')).hexdigest()
    try:
        result = subprocess.run([binary, 'arc', 'generate-test-suite', '--prompt', prompt,
                                 '--output-dir', str(destination), '--requirements-sha256', fingerprint,
                                 '--exclude-integration'], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f'[tests] octos test generation unavailable ({type(exc).__name__}); using existing test planning')
        return None
    if result.returncode:
        log(f'[tests] octos test generation exited {result.returncode}; using existing test planning')
        return None
    try:
        receipt = json.loads(result.stdout)
    except ValueError:
        log('[tests] octos returned no usable test response; using existing test planning')
        return None
    if not isinstance(receipt, dict) or receipt.get('trusted') is not True:
        log('[tests] octos did not return trusted=true; using existing test planning')
        return None
    log(f'[tests] octos supplied tests and business documents at {destination}')
    return destination, receipt


def load_business(directory: Path) -> tuple[dict, dict, dict]:
    return tuple(json.loads((directory / name).read_text(encoding='utf8'))
                 for name in ['app-design.json', 'requirement-contracts.json', 'test-obligations.json'])


def generation_note(directory: Path) -> str:
    return (f'OCTOS TEST SUITE at {directory}. '
            'Octos returned trusted=true for these tests and business documents; use them directly '
            'and skip spec generation, review, audit and waiting queues. Do not regenerate or edit them. '
            'Trust in the tests is not a measured product pass or an official benchmark score. '
            'requirements.yaml remains the behavior authority; report any conflict. '
            f'Read {directory / "fixtures.json"} and {directory / "README.md"} for public UI prerequisites. '
            f'Use {directory / "app-design.json"}, {directory / "domain-contracts.json"}, '
            f'{directory / "requirement-contracts.json"} and {directory / "test-obligations.json"} '
            'as the shared business documents. Implementation paths remain choices.\n')
