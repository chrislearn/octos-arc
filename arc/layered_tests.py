"""Frozen authoritative basic gates and a final, streaming business queue.

The coordinator owns publication. Workers only return read-only review replies;
application authors never create or modify these tests or their decisions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

from acceptance import RunSummary
from derived_pipeline import DerivedSpecPipeline
from scenario_review import ancestor_context
from scenario_tests import (HELPERS, _compile_scenario, _node_text, _start, _ts,
                            spec_header, suite_fixtures)
from requirement_contracts import _ui_bindings
from test_policy import test_block


def digest(value) -> str:
    raw = value if isinstance(value, bytes) else (value.encode() if isinstance(value, str)
           else json.dumps(value, sort_keys=True, ensure_ascii=False).encode())
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def dependency_files(directory: Path, relative: str) -> dict[str, bytes]:
    """Hash and copy the actual local import closure, rejecting escaping imports."""
    pending, files = [relative], {}
    while pending:
        rel = pending.pop()
        path = directory / rel
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f'unsafe or missing test dependency: {rel}')
        key = path.relative_to(directory).as_posix()
        if key in files:
            continue
        files[key] = path.read_bytes()
        text = files[key].decode()
        for imported in re.findall(r'(?:from\s+|require\(\s*|import\(\s*|import\s+)[\'\"](\.[^\'\"]+)', text):
            base = path.parent / imported
            candidates = [base] + [base.with_suffix(ext) for ext in ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')]
            candidates += [base / ('index' + ext) for ext in ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')]
            resolved = next((p for p in candidates if p.is_file()), None)
            if resolved is None or not resolved.resolve().is_relative_to(directory.resolve()):
                raise ValueError(f'unresolved test import: {imported}')
            pending.append(resolved.relative_to(directory).as_posix())
    return files


def helper_excerpt(source: str, case: str) -> str:
    """Keep exact function closure plus every module-scope declaration.

    The bundled helper uses column-zero top-level declarations. Preserve all
    globals/types/imports and conservatively follow function references, not
    just calls; an unknown helper operation falls back to the complete source.
    """
    matches = list(re.finditer(r'(?m)^(?:export )?(?:async )?(function|const|let|class|type|interface) (\w+)\b', source))
    if not matches:
        return source
    parts = {m[2]: source[m.start():matches[i + 1].start() if i + 1 < len(matches) else len(source)]
             for i, m in enumerate(matches)}
    functions = {m[2] for m in matches if m[1] == 'function'}
    needed = set(re.findall(r'\bh\.(\w+)\(', case))
    if not needed <= functions:
        return source
    needed.update(m[2] for m in matches if m[1] != 'function')
    pending = list(needed)
    while pending:
        name = pending.pop()
        for called in set(re.findall(r'\b\w+\b', parts[name])) & functions:
            if called not in needed:
                needed.add(called)
                pending.append(called)
    return source[:matches[0].start()] + '\n'.join(parts[m[2]] for m in matches if m[2] in needed)


def compile_basic(node: dict, fixtures, context: str) -> tuple[str, str]:
    """One minimal entry contract, with no business data writes or result oracle."""
    node_id = str(node['id'])
    bindings = _ui_bindings(_node_text(node))
    visible_roles = {'button', 'link', 'textbox', 'grid', 'table', 'toolbar', 'tab', 'heading', 'navigation'}
    bindings = [row for row in bindings if row['role'] in visible_roles and row.get('name')]
    endpoint = re.search(r'\bGET\s+[`\"\']?(/[^\s`\"\']+)[`\"\']?.{0,80}?\b(?:returns?|status)\s+(\d{3})\b',
                         str(node.get('description') or ''), re.I)
    if endpoint and not re.search(r'[:*{}?]', endpoint[1]):
        title = f'{node_id}: basic entry'
        header = spec_header(node_id).replace("import { test }", "import { test, expect }")
        return (header + f'\ntest({_ts(title)}, async ({{ page }}) => {{\n'
                + f'  const response = await page.request.get({_ts(endpoint[1])});\n'
                + f'  expect(response.status()).toBe({int(endpoint[2])});\n}});\n', '')
    if re.fullmatch(r'\s*Open the (?:application|website) and display the home page[.!]?\s*',
                    str(node.get('description') or ''), re.I):
        header = spec_header(node_id).replace("import { test }", "import { test, expect }")
        return (header + f'\ntest({_ts(node_id + ": basic entry")}, async ({{ page }}) => {{\n'
                + "  await h.openHome(page);\n  await expect(page.locator('body')).toBeVisible();\n});\n", '')
    scenarios = node.get('scenarios') or []
    for scenario in scenarios or [{'name': 'declared entry', 'steps': []}]:
        parsed = _compile_scenario(scenario, fixtures, _node_text(node))
        if parsed.setup_cells:
            continue  # setup writes belong to business tests, not an entry shortcut
        lines = []
        if not _start(lines, parsed):
            continue
        # A seeded entry is opened only when its literal is explicitly a WHEN target.
        when = ' '.join(str(s.get('content') or '') for s in scenario.get('steps') or []
                        if str(s.get('keyword') or '').upper() == 'WHEN')
        entry = next((value for _, value in parsed.seed_kinds if value in when), None)
        if bindings:
            # A declared control and a scenario's navigation target may live on
            # different pages. Never navigate away before checking that control.
            # The independent audit (or contract completion) proves its location.
            item = bindings[0]
            lines.append(f'  await h.expectRole(page, {_ts(item["role"])}, {_ts(item["name"])});')
        elif parsed.entry:
            if entry:
                lines.append(f'  await h.clickNamed(page, {_ts(entry)});')
            lines.append(f'  await h.expectReachable(page, {_ts(parsed.entry)});')
        else:
            continue
        title = f'{node_id}: basic entry'
        source = spec_header(node_id) + f'\ntest({_ts(title)}, async ({{ page }}) => {{\n' + '\n'.join(lines) + '\n});\n'
        return source, ''
    return '', 'no mechanically grounded minimal entry; complete its entry/fixture contract before implementation'


class GateBlocked(RuntimeError):
    pass


def compile_entry_contract(node_id: str, contract, sources: dict) -> str:
    """A bounded, source-grounded entry DSL, never arbitrary model code."""
    text = '\n'.join(sources.values())
    if not isinstance(contract, dict):
        raise ValueError('entry contract must be an object')
    def grounded(item):
        if not isinstance(item, dict):
            raise ValueError('entry step must be an object')
        quote = item.get('quote')
        if not isinstance(quote, str) or len(quote.strip()) < 12 or quote not in text:
            raise ValueError('entry step needs an exact requirement quote')
        return quote
    def literal(item, key, quote):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip() or value not in quote:
            raise ValueError('entry literal is not grounded in its quote')
        return value
    steps = contract.get('navigation', [])
    if not isinstance(steps, list) or len(steps) > 4:
        raise ValueError('entry navigation must have at most four steps')
    lines = ['  await h.openHome(page);']
    for item in steps:
        quote = grounded(item)
        name = literal(item, 'name', quote)
        if item.get('kind') != 'click':
            raise ValueError('only entry navigation clicks are allowed')
        lines.append(f'  await h.clickNamed(page, {_ts(name)});')
    assertion = contract.get('assertion')
    quote = grounded(assertion)
    kind = assertion.get('kind')
    header = spec_header(node_id).replace('Derived mechanically', 'Compiled from a source-grounded entry contract')
    if kind == 'role':
        role = assertion.get('role')
        if role not in {'button', 'link', 'textbox', 'grid', 'table', 'toolbar', 'tab', 'heading', 'navigation'}:
            raise ValueError('unsupported entry role')
        name = literal(assertion, 'name', quote)
        lines.append(f'  await h.expectRole(page, {_ts(role)}, {_ts(name)});')
    elif kind == 'reachable':
        name = literal(assertion, 'name', quote)
        lines.append(f'  await h.expectReachable(page, {_ts(name)});')
    elif (kind == 'home' and quote in sources.get(node_id, '') and re.fullmatch(
            r'\s*Open the (?:application|website) and display the home page[.!]?\s*', quote, re.I)):
        header = header.replace('import { test }', 'import { test, expect }')
        lines.append("  await expect(page.locator('body')).toBeVisible();")
    else:
        raise ValueError('unsupported or ungrounded entry assertion')
    return header + f'\ntest({_ts(node_id + ": basic entry")}, async ({{ page }}) => {{\n' + '\n'.join(lines) + '\n});\n'


class LayeredState:
    """Stable task/source identities survive helper edits, renames and app rollback."""
    def __init__(self, root: Path, tree: dict, node_ids: list[str]):
        self.requirements_hash = digest(tree)
        self.path = root / '.arc/test-control' / f'layered-{self.requirements_hash[:16]}.json'
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if not isinstance(self.data, dict) or self.data.get('requirements_hash') != self.requirements_hash:
                raise ValueError('layered control source mismatch')
        else:
            self.data = {'version': 1, 'requirements_hash': self.requirements_hash, 'phase': 'initial',
                         'nodes': {key: {'code_done': False, 'basic': 'pending'} for key in node_ids},
                         'cases': {}, 'stops': {}, 'business_tasks': {key: 'pending' for key in node_ids}}
        if (not isinstance(self.data, dict) or self.data.get('version') != 1
                or self.data.get('phase') not in {'initial', 'code', 'business', 'closed'}
                or not all(isinstance(self.data.get(key), dict) for key in ('nodes', 'cases', 'stops', 'business_tasks'))
                or set(self.data['nodes']) != set(node_ids)
                or set(self.data['business_tasks']) != set(node_ids)
                or any(not isinstance(row, dict) or type(row.get('code_done')) is not bool
                       or not isinstance(row.get('basic'), str) for row in self.data['nodes'].values())
                or any(not isinstance(row, dict) for row in self.data['cases'].values())
                or any(not isinstance(row, dict) or type(row.get('attempts')) is not int
                       or not 0 <= row['attempts'] <= 2 or row.get('state') not in {'active', 'disputed', 'repair_exhausted'}
                       for row in self.data['stops'].values())):
            raise ValueError('invalid layered control state; repair limits cannot be recovered safely')
        self.save()

    def save(self):
        fingerprint = digest(self.data)
        if fingerprint == getattr(self, '_saved_digest', None):
            return
        write_json(self.path, self.data)
        self._saved_digest = fingerprint
        callback = getattr(self, 'on_save', None)
        if callback:
            callback()

    def identity(self, node: str, scenario: str) -> str:
        return digest([self.requirements_hash, node, scenario])[:24]

    def begin_repair(self, identities: list[str]) -> bool:
        if any(self.data['stops'].get(key, {}).get('state') == 'disputed'
               or self.data['stops'].get(key, {}).get('attempts', 0) >= 2 for key in identities):
            return False
        for key in identities:
            row = self.data['stops'].setdefault(key, {'attempts': 0, 'state': 'active'})
            row['attempts'] += 1
        self.save()  # charge before dispatch; a crash or no-op does not grant another attempt
        return True

    def dispute(self, key: str, reason: str):
        row = self.data['stops'].setdefault(key, {'attempts': 0})
        row.update(state='disputed', reason=reason)
        self.save()


class ApplicationSnapshot:
    """Application/config/data preimage, excluding all authority/control artifacts."""
    def __init__(self, flow):
        self.flow = flow
        self.files = self.capture(flow)

    @staticmethod
    def capture(flow, *, include_symlinks=False):
        root_excluded = {'.git', '.arc', 'design', 'requirements'}
        generated = {'node_modules', 'dist', 'test-results', 'playwright-report'}
        authority = [getattr(flow, name, None) for name in ('tests_dir', 'derived_tests_dir', 'basic_tests_dir')]
        authority += list(getattr(getattr(flow, 'layered', None), 'authority_directories', []))
        authority = [Path(directory) for directory in authority if directory and Path(directory).is_relative_to(flow.output_dir)]
        files = {}
        def visit(directory):
            for path in directory.iterdir():
                if (path.name in generated or directory == flow.output_dir and path.name in root_excluded
                        or any(path == protected or path.is_relative_to(protected) for protected in authority)):
                    continue
                rel = path.relative_to(flow.output_dir).as_posix()
                if path.is_symlink():
                    if include_symlinks:
                        files[rel] = None
                        continue
                    raise ValueError(f'application symlink is not snapshot-safe: {rel}')
                if path.is_dir():
                    visit(path)
                elif path.is_file():
                    files[rel] = path.read_bytes()
        visit(flow.output_dir)
        return files

    def restore(self):
        current = self.capture(self.flow, include_symlinks=True)
        for rel, content in current.items():
            if rel not in self.files or content is None:
                (self.flow.output_dir / rel).unlink()
        for rel, content in self.files.items():
            path = self.flow.output_dir / rel
            if path.is_dir():
                shutil.rmtree(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def publish_initial(flow, tree: dict, ordered: list[dict]) -> Path:
    from quality_control import export_contracts
    design = getattr(flow, 'app_design_doc', None)
    from main import app_design_errors, requirement_index, app_design_coverage
    if (not design or app_design_errors(design, requirement_index(tree)) or getattr(flow, '_design_blocked', set())
            or {str(node['id']) for node in ordered} - app_design_coverage(design)):
        raise GateBlocked('initial requirement/model/contracts are incomplete')
    export_contracts(flow.output_dir, tree, design, 'ready_for_implementation')
    key = digest(tree)
    destination = flow.output_dir / 'design/initial' / key[:16]
    if destination.exists():
        if destination.is_symlink() or (destination / 'manifest.json').is_symlink():
            raise GateBlocked('initial snapshot contains a symlink')
        manifest = json.loads((destination / 'manifest.json').read_text())
        actual = {p.relative_to(destination).as_posix() for p in destination.rglob('*')
                  if p.is_file() and p.relative_to(destination).as_posix() != 'manifest.json'}
        if (manifest.get('requirements_hash') != key or manifest.get('status') != 'complete'
                or not manifest.get('files') or set(manifest['files']) != actual
                or any(p.is_symlink() for p in destination.rglob('*')) or any(
                    not (destination / rel).resolve().is_relative_to(destination.resolve()) or
                    digest((destination / rel).read_bytes()) != value for rel, value in manifest['files'].items())):
            raise GateBlocked('initial snapshot is corrupt or belongs to another source')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.initial-', dir=destination.parent))
    try:
        source_versions = {}
        def copy_file(source, target):
            raw = source.read_bytes()
            source_versions[source] = digest(raw)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        for path in (flow.output_dir / 'design').glob('*.json'):
            copy_file(path, temporary / path.name)
        for name in ('app.json', 'phases.json', 'app.meta.json', 'domain-review.json', 'domain-contracts.json'):
            path = flow.output_dir / '.arc/design' / name
            if path.is_file():
                copy_file(path, temporary / name)
        originals = temporary / 'original-requirements'
        originals.mkdir()
        for path in flow.req_dir.iterdir():
            if flow.req_dir == flow.output_dir and path.name not in {'requirements.yaml', 'requirements.yml', 'reference', 'references'}:
                continue
            if path.is_symlink():
                raise GateBlocked('original requirement source contains a symlink')
            if path.is_dir():
                for child in path.rglob('*'):
                    if child.is_symlink():
                        raise GateBlocked('original requirement source contains a symlink')
                    if child.is_file():
                        copy_file(child, originals / child.relative_to(flow.req_dir))
            elif path.is_file():
                copy_file(path, originals / path.name)
        write_json(temporary / 'resolved-requirements.json', tree)
        from obligation_planning import source_scope
        sources, ancestry = source_scope(tree, [str(n['id']) for n in ordered])
        source_units = []
        for owner, text in sources.items():
            for ordinal, match in enumerate(re.finditer(r'[^\n]+', text)):
                quote = match[0]
                source_units.append({'id': digest([key, owner, ordinal, quote])[:24],
                    'requirement_id': owner, 'quote': quote, 'offset': match.start(),
                    'applies_to': [leaf for leaf, chain in ancestry.items() if owner in chain]})
        write_json(temporary / 'test-planning-index.json', {
            'requirements_hash': key, 'obligations': design.get('obligations', []),
            'sources': source_units, 'ancestry': ancestry,
            'contracts': {kind: design.get(kind, []) for kind in ('data_model', 'commands', 'routes', 'contracts', 'pages')},
            'gaps': ['Each source unit still requires independent business case coverage validation.'],
            'nodes': {str(n['id']): {'description': n.get('description', ''), 'scenarios': n.get('scenarios', []),
                                     'dependencies': n.get('dependencies', [])} for n in ordered}})
        files = {p.relative_to(temporary).as_posix(): digest(p.read_bytes())
                 for p in temporary.rglob('*') if p.is_file()}
        write_json(temporary / 'manifest.json', {'version': 1, 'status': 'complete', 'requirements_hash': key,
                                               'created': time.time(), 'files': files})
        if any(not path.is_file() or digest(path.read_bytes()) != value for path, value in source_versions.items()):
            raise GateBlocked('initial source changed during snapshot publication')
        temporary.replace(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


class LayeredTests:
    def __init__(self, flow, ordered: list[dict]):
        self.flow, self.ordered = flow, ordered
        self.authority_directories = {Path(directory) for name in ('tests_dir', 'derived_tests_dir', 'basic_tests_dir')
                                      if (directory := getattr(flow, name, None)) is not None}
        self.state = LayeredState(flow.output_dir, flow.requirement_tree, [str(n['id']) for n in ordered])
        self.state.on_save = flow.refresh_protected_control
        self.basic_pipeline = None
        self.safe = None
        self.cancelled = False
        self.business_started = False
        self.basic_candidates = {}
        self.private_review_root = flow.output_dir / '.arc/test-staging' / ('basic-' + self.state.requirements_hash[:16])
        self.private_review_root.mkdir(parents=True, exist_ok=True)
        self.static_cache = {}
        self.active_case_ids = None
        self.case_inclusions = {}
        self.final_signature = None
        self.verified_basic_source = None
        self.business_producer_done = False
        self.business_reviews_version = None
        self.business_publication_retry_at = 0
        self.business_discovery_cache = {}
        self.repair_preimages = {}
        self.state.data['publication_gaps'] = {}
        self.state.data['phase'] = 'initial'
        for key in ('termination', 'termination_reason'):
            self.state.data.pop(key, None)  # a resumed run has its own completion/termination outcome
        # Source/manifest evidence is remeasured on resume; stop counters remain.
        for row in self.state.data['nodes'].values():
            row['basic'] = 'pending'
            row['code_done'] = False
        for key, row in self.state.data['cases'].items():
            if self.state.data['stops'].get(key, {}).get('state') != 'disputed':
                row['status'] = 'pending'
        self.state.data['business_tasks'] = {str(n['id']): 'pending' for n in ordered}
        self.state.save()

    def prepare(self):
        flow = self.flow
        self.authority_directories.update(Path(directory) for name in ('tests_dir', 'derived_tests_dir')
                                          if (directory := getattr(flow, name, None)) is not None)
        initial = publish_initial(flow, flow.requirement_tree, self.ordered)
        flow.initial_test_planning_index = json.loads((initial / 'test-planning-index.json').read_text())
        directory = flow.output_dir / '.arc/basic-tests'
        directory.mkdir(parents=True, exist_ok=True)
        flow.basic_tests_dir = directory
        self.authority_directories.add(directory)
        if getattr(flow, 'runner', None) is None:
            flow.runner = flow.playwright_runner(directory)
        (directory / 'helpers.ts').write_bytes(HELPERS.read_bytes())
        fixtures = suite_fixtures(self.ordered)
        context = ancestor_context(flow.requirement_tree)
        from main import source_contracts_for_tests
        sources = source_contracts_for_tests(flow.requirement_tree, {str(n['id']) for n in self.ordered})
        for node in self.ordered:
            node_id = str(node['id'])
            source, error = compile_basic(node, fixtures, context.get(node_id, ''))
            rel = f'{node_id}.spec.ts'
            if source:
                (directory / rel).write_text(source)
            self.basic_candidates[node_id] = {'node_id': node_id, 'file': rel, 'source': source,
                'gap': error,
                'sources': sources[node_id], 'fixtures': str(fixtures),
                'helper': helper_excerpt(HELPERS.read_text(), source),
                'helper_hash': digest(HELPERS.read_bytes()),
                'input_hash': digest([source, sources[node_id], str(fixtures), HELPERS.read_bytes().hex(),
                                      digest(Path(__file__).read_bytes())])}
        flow.snapshot_protected()
        self.state.data['phase'] = 'code'
        self.state.save()
        import queue
        flow._background_spec_metrics = queue.Queue()
        # Only an isolated tool-free executor can run in a worker. Otherwise
        # the main thread audits the current node before its mandatory gate.
        from main import OctosDriver, LlmProxy
        driver = getattr(flow, 'driver', None)
        config = Path(driver.env.get('OCTOS_CONFIG_DIR', '')) / 'config.json' if isinstance(driver, OctosDriver) else None
        for key, candidate in self.basic_candidates.items():
            path = self.private_review_root / f'{key}.json'
            if path.is_file():
                try:
                    result = json.loads(path.read_text())
                    if result.get('input_hash') == candidate['input_hash']:
                        self.install_basic(result)
                except (ValueError, OSError, TypeError):
                    pass  # incomplete reply is never admitted
        pending = [key for key in self.basic_candidates if self.state.data['nodes'][key]['basic'] == 'pending']
        if pending and config is not None and config.is_file() and isinstance(getattr(flow, 'llm_proxy', None), LlmProxy):
            self.basic_pipeline = DerivedSpecPipeline(
                [[{'id': key}] for key in pending],
                lambda batch: self.review_basic(str(batch[0]['id']), isolated=True))

    def entry_text(self, prompt, label, *, isolated=False):
        flow = self.flow
        timeout = min(300, max(0, flow.remaining() - flow.final_measurement_reserve()))
        if timeout < 30 or flow.wound_down() or self.cancelled:
            return False, 'insufficient basic preparation budget'
        system = 'You prepare independent authoritative entry tests. Return JSON only. No tools or application evidence.'
        if not isolated:
            return flow.text_turn(prompt, timeout, label, system=system, spec_chars=len(prompt))
        from spec_parallel import SpecRequest
        from main import reservation_tokens
        pool = flow.isolated_spec_requests(1, force_single=True, defer_metrics=True,
                                           allowed=lambda job: not self.cancelled and not flow.time_up())
        if pool is None:
            return False, 'isolated entry executor unavailable'
        job = SpecRequest(prompt, int(timeout), label, system, reservation_tokens(prompt, output_cap=2048),
                          time.monotonic() + timeout)
        replies = pool.ordered([job])
        try:
            answer = next(replies, None)
            return (answer.ok, answer.text) if answer is not None else (False, '')
        finally:
            replies.close()

    def complete_entry(self, row, *, isolated=False):
        """One private proposal for a missing/rejected entry, before authoring its node."""
        flow = self.flow
        index = getattr(flow, 'initial_test_planning_index', {})
        contracts = {kind: [item for item in index.get('contracts', {}).get(kind, [])
                            if isinstance(item, dict) and row['node_id'] in item.get('requirements', [])]
                     for kind in ('pages', 'routes', 'contracts')}
        prompt = ('Complete ONLY a minimal entry contract from these original requirements. '
                  'Design is routing context, not an authority for invented expectations. No application code/results. '
                  'Return {navigation:[{kind:"click",name,quote}],assertion:{kind:"role"|"reachable"|"home",'
                  'role?,name?,quote}}. At most four navigation clicks, only to reach the declared entry; '
                  'no creation, deletion, edit, submission, persistence, or business-result assertions. '
                  'Use exact source quotes (at least 12 characters) for every step; names must occur in their quote. '
                  'home is allowed only for an explicit home-page requirement. If no executable source-grounded '
                  'entry exists return {gap:"reason"}; do not replace a missing contract by a generic body check.\n'
                  + json.dumps({'sources': row['sources'], 'contracts': contracts, 'fixtures': row['fixtures'],
                                'gap': row.get('gap', ''), 'prior_candidate': row['source']}, ensure_ascii=False))
        key = digest([row['input_hash'], prompt])
        path = self.private_review_root / (row['node_id'] + '.entry.json')
        saved = None
        if path.exists():
            try:
                saved = json.loads(path.read_text())
            except (ValueError, OSError):
                pass
        if not isinstance(saved, dict) or saved.get('input_hash') != key:
            # Persist dispatch before the call. An interrupted request remains
            # an explicit gap rather than being charged again on resume.
            write_json(path, {'input_hash': key, 'contract': {}, 'status': 'dispatched'})
            ok, reply = self.entry_text(prompt, 'basic entry contract completion', isolated=isolated)
            try:
                contract = json.loads(reply) if ok else {}
            except (ValueError, TypeError):
                contract = {}
            saved = {'input_hash': key, 'contract': contract, 'reply': str(reply)}
            write_json(path, saved)
        contract = saved['contract']
        source = compile_entry_contract(row['node_id'], contract, row['sources'])
        return {**row, 'source': source, 'entry_contract': contract,
                'helper': helper_excerpt(HELPERS.read_text(), source)}

    def review_basic(self, node_id: str, *, isolated=False, completed=None):
        flow = self.flow
        original = self.basic_candidates[node_id]
        row = completed or original
        if self.cancelled:
            return {'node_id': node_id, 'status': 'cancelled'}
        if not row['source']:
            try:
                row = self.complete_entry(row, isolated=isolated)
            except ValueError as exc:
                result = {'node_id': node_id, 'status': 'rejected', 'input_hash': row['input_hash'],
                          'decision': {}, 'reply': str(exc)}
                write_json(self.private_review_root / f'{node_id}.json', result)
                return result
        title = f'{node_id}: basic entry'
        block = test_block(row['source'], title)
        prompt = ('Independently audit this minimal authoritative entry test. No application implementation or results '
                  'are evidence. Check exact source grounding, GIVEN/fixture setup, navigation, helper semantics and '
                  'observable assertion. This is only a basic entry contract; do not require full business outcomes. '
                  'Reject invented constraints, unavailable actors or setup that requires later unimplemented nodes. '
                  'Return one JSON object {status:"approved_basic"|"rejected",requirement_quote,test_quote,reason}. '
                  'The helper evidence retains exact referenced functions and all module globals; it is not a summary. '
                  'Both quotes must be exact supplied substrings; test_quote must contain the asserted check.\n'
                  + json.dumps({k: row[k] for k in ('sources', 'fixtures', 'source', 'helper')}, ensure_ascii=False))
        audit_key = digest([row['input_hash'], row['source'], row.get('entry_contract')])
        audit_path = self.private_review_root / (node_id + '.audit-' + audit_key[:16] + '.json')
        audited = None
        if audit_path.is_file():
            try:
                audited = json.loads(audit_path.read_text())
            except (ValueError, OSError):
                pass
        if not isinstance(audited, dict) or audited.get('input_hash') != audit_key:
            write_json(audit_path, {'input_hash': audit_key, 'ok': False, 'reply': 'interrupted audit dispatch'})
            ok, reply = self.entry_text(prompt, 'basic independent review', isolated=isolated)
            write_json(audit_path, {'input_hash': audit_key, 'ok': ok, 'reply': str(reply)})
        else:
            ok, reply = audited.get('ok') is True, audited.get('reply', '')
        try:
            decision = json.loads(str(reply).strip()) if ok else {}
        except ValueError:
            decision = {}
        quotes = '\n'.join(row['sources'].values())
        decision = decision if isinstance(decision, dict) else {}
        requirement_quote, test_quote = decision.get('requirement_quote', ''), decision.get('test_quote', '')
        approved = (decision.get('status') == 'approved_basic' and isinstance(requirement_quote, str)
                    and len(requirement_quote.strip()) >= 12 and requirement_quote in quotes
                    and isinstance(test_quote, str) and len(test_quote.strip()) >= 12
                    and test_quote in (block or '') and 'expect' in test_quote
                    and isinstance(decision.get('reason'), str) and bool(decision['reason'].strip()))
        if not approved and 'entry_contract' not in row:
            try:
                replacement = self.complete_entry({**row, 'gap': str(decision.get('reason') or reply)}, isolated=isolated)
            except ValueError:
                pass
            else:
                return self.review_basic(node_id, isolated=isolated, completed=replacement)
        result = {'node_id': node_id, 'status': 'approved_basic' if approved else 'rejected',
                  'input_hash': row['input_hash'], 'decision': decision, 'reply': str(reply)}
        if 'entry_contract' in row:
            result['entry_contract'] = row['entry_contract']
            result['completed_source_hash'] = digest([row['source'], row['entry_contract']])
        write_json(self.private_review_root / f'{node_id}.json', result)
        return result

    def install_basic(self, result):
        key = result.get('node_id')
        candidate = self.basic_candidates.get(key)
        if self.cancelled or not candidate or result.get('input_hash') != candidate['input_hash']:
            return
        flow = self.flow
        node = self.state.data['nodes'][key]
        if result['status'] == 'approved_basic' and 'entry_contract' in result:
            try:
                source = compile_entry_contract(key, result['entry_contract'], candidate['sources'])
            except ValueError:
                node.update(basic='blocked', reason='invalid completed entry contract')
                self.state.save()
                return
            if result.get('completed_source_hash') != digest([source, result['entry_contract']]):
                node.update(basic='blocked', reason='completed entry changed after independent audit')
                self.state.save()
                return
            candidate = {**candidate, 'source': source}
            self.basic_candidates[key] = candidate
            (flow.basic_tests_dir / candidate['file']).write_text(source)
        write_json(flow.basic_tests_dir / 'review' / f'{key}.json', result)
        if result['status'] != 'approved_basic':
            node.update(basic='rejected', reason='independent basic review did not approve')
        else:
            runner = self.basic_runner()
            try:
                deps = dependency_files(flow.basic_tests_dir, candidate['file'])
                intact = (deps[candidate['file']].decode() == candidate['source']
                          and digest(deps.get('helpers.ts', b'')) == candidate['helper_hash'])
                discovered, detail = runner.discover_cases([candidate['file']]) if runner and intact else (
                    [], 'approved basic candidate or dependency changed')
                valid = (len(discovered) == 1 and discovered[0]['title'] == f'{key}: basic entry'
                         and dependency_files(flow.basic_tests_dir, candidate['file']) == deps)
            except (OSError, ValueError) as exc:
                valid, detail = False, str(exc)
            if valid:
                node.update(basic='frozen', file=candidate['file'],
                            dependency_hashes={rel: digest(raw) for rel, raw in deps.items()},
                            cases=discovered, review=result['decision'], input_hash=candidate['input_hash'],
                            frozen_at=time.time())
            else:
                node.update(basic='blocked', reason=str(detail))
        self.state.save()
        flow.snapshot_protected()
        flow.metric('basic_spec_publication', node_id=key, status=node['basic'])

    def basic_runner(self):
        runner = getattr(self.flow, 'runner', None)
        if runner is None:
            return None
        clone = copy.copy(runner)
        clone.tests_dir = self.flow.basic_tests_dir
        clone.derived_policy = None
        clone.case_exclusions = {}
        clone.case_inclusions = {}
        return clone

    def poll_basic(self):
        if self.basic_pipeline:
            for result in self.basic_pipeline.poll_ready():
                if 'error' in result:
                    for key in result.get('node_ids', []):
                        self.state.data['nodes'][key].update(basic='blocked', reason=result['error'])
                    self.state.save()
                else:
                    self.install_basic(result)
            if self.basic_pipeline.wait(0):
                self.basic_pipeline.close(0)
                self.basic_pipeline = None
        if self.basic_pipeline is None and all(row['basic'] in {'frozen', 'passed'} for row in self.state.data['nodes'].values()):
            if not self.business_started and not self.cancelled:
                self.business_started = True
                self.flow.start_background_specs(self.ordered)

    def wait_basic(self, node_id):
        if self.basic_pipeline is None and self.state.data['nodes'][node_id]['basic'] == 'pending':
            self.install_basic(self.review_basic(node_id))
        while self.state.data['nodes'][node_id]['basic'] == 'pending':
            self.poll_basic()
            if self.flow.time_up() or self.flow.wound_down() or self.flow.remaining() <= self.flow.final_measurement_reserve():
                raise GateBlocked(f'{node_id}: waiting for frozen basic spec exceeded task budget')
            time.sleep(.1)
        if self.state.data['nodes'][node_id]['basic'] not in {'frozen', 'passed'}:
            raise GateBlocked(f'{node_id}: basic spec not frozen: {self.state.data["nodes"][node_id].get("reason", "rejected")}')

    def basic_specs(self, current=None):
        keys = [key for key, row in self.state.data['nodes'].items() if row['code_done'] or key == current]
        specs = []
        for key in keys:
            row = self.state.data['nodes'][key]
            if row['basic'] not in {'frozen', 'passed'}:
                raise GateBlocked(f'{key}: frozen basic manifest missing')
            if any(not (self.flow.basic_tests_dir / rel).is_file()
                   or not (self.flow.basic_tests_dir / rel).resolve().is_relative_to(self.flow.basic_tests_dir.resolve())
                   or (self.flow.basic_tests_dir / rel).is_symlink()
                   or digest((self.flow.basic_tests_dir / rel).read_bytes()) != value
                   for rel, value in row['dependency_hashes'].items()):
                raise GateBlocked(f'{key}: frozen basic dependency changed')
            specs.append(row['file'])
        return specs

    def run_basic(self, current=None):
        self.authority_directories.update(Path(directory) for name in ('tests_dir', 'derived_tests_dir')
                                          if (directory := getattr(self.flow, name, None)) is not None)
        specs = self.basic_specs(current)
        if not specs:
            return RunSummary(error='empty basic protection set')
        check = self.static_check()
        if check:
            return RunSummary(error=check)
        flow = self.flow
        saved = flow.tests_dir, flow.runner, getattr(flow, '_layered_execution_level', None), getattr(flow, '_layered_current_node', None)
        flow.tests_dir, flow.runner, flow._layered_execution_level = flow.basic_tests_dir, self.basic_runner(), 'basic'
        flow._layered_current_node = current
        try:
            summary = flow.run_specs(specs, workers=1)
            summary._layered_basic = True
            if (current is None and all(row['code_done'] for row in self.state.data['nodes'].values())
                    and self.complete(summary, specs) and summary.all_passed):
                self.verified_basic_source = flow.app_source_digest()
            return summary
        finally:
            flow.tests_dir, flow.runner, flow._layered_execution_level, flow._layered_current_node = saved

    def implement(self, tree, ordered, unchanged):
        flow = self.flow
        flow._dependency_tree = tree
        for index, node in enumerate(ordered, 1):
            node_id = str(node['id'])
            flow._layered_current_node = node_id
            if not flow.node_start_budget_available(node_id, measurement_only=node_id in unchanged) or not flow.admit_node(node):
                raise GateBlocked(f'{node_id}: node could not be admitted; later nodes remain pending')
            self.poll_basic()
            candidate = self.basic_candidates.get(node_id)
            if candidate is not None and not candidate['source']:
                self.wait_basic(node_id)  # complete and audit a missing entry before writing its code
            if node_id in unchanged:
                flow.regression_cycle(node)
            else:
                flow.node_cycle(node, ordered, index, len(ordered))
            evidence = getattr(flow, 'implementation_evidence', {}).get(node_id, {})
            if (node_id not in unchanged and evidence.get('status') not in {'implemented_unverified', 'behavior_verified'}
                    or node_id in getattr(flow, 'impl_failed', [])):
                if self.safe:
                    self.safe.restore()
                raise GateBlocked(f'{node_id}: implementation is incomplete')
            self.gate(node_id)
            flow.poll_background_specs()
            if flow.driver:
                flow.driver.end_scope('node')

    @staticmethod
    def matches(outcome, row, specs):
        path = str(getattr(outcome, 'spec_path', '') or outcome.file).replace('\\', '/')
        file = row['file']
        exact = path == file or path.endswith('/' + file)
        unique_fallback = '/' not in path and sum(Path(p).name == path for p in specs) == 1
        return ((exact or unique_fallback and Path(file).name == path)
                and outcome.title == row['title'] and
                (row.get('line') is None or getattr(outcome, 'spec_line', None) == row['line']))

    def complete(self, summary, specs):
        observed = [row for row in summary.results if row.status != 'quarantined']
        basic = [case for node in self.state.data['nodes'].values() for case in node.get('cases', [])
                 if case['file'] in specs]
        expected = basic if getattr(summary, '_layered_basic', False) else [row for row in self.state.data['cases'].values() if row['file'] in specs
                             and self.state.data['stops'].get(row['id'], {}).get('state') != 'disputed'
                             and (self.active_case_ids is None or row['id'] in self.active_case_ids)]
        return (not summary.error and not summary.killed and not summary.load_errors and not summary.runtime_uncertain
                and summary.total == len(summary.results) and summary.passed == sum(r.ok for r in summary.results)
                and bool(expected) and len(observed) == len(expected)
                and all(r.status in {'passed', 'failed', 'timedOut'} for r in observed)
                and all(sum(self.matches(r, row, specs) for r in observed) == 1 for row in expected))

    def static_check(self):
        """Check every changed application file before runtime/retention."""
        self.static_incomplete = False
        from generation_checks import check_batch
        try:
            files = ApplicationSnapshot.capture(self.flow)
        except (OSError, ValueError) as exc:
            return f'application static inspection failed: {exc}'
        key = digest({rel: digest(raw) for rel, raw in files.items() if not rel.startswith('backend/data/')})
        if key in self.static_cache:
            return self.static_cache[key]
        baseline = self.safe.files if self.safe else {}
        changed = {rel for rel in files.keys() | baseline.keys() if files.get(rel) != baseline.get(rel)}
        sources = {rel: raw.decode(errors='replace') for rel, raw in files.items()
                   if rel.endswith(('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx'))}
        result = check_batch(self.flow.output_dir, changed, budget=min(30, max(1, self.flow.remaining())), sources=sources)
        while any('Babel parser unavailable' in item for item in result['deferred']):
            allowance = self.flow.remaining() - self.flow.final_measurement_reserve()
            if allowance >= 30 and getattr(self, '_static_tools_attempts', 0) < 2:
                from runtime_diagnostics import ensure_binding_tools
                if getattr(self, '_static_tools_attempts', 0):
                    time.sleep(1)
                self._static_tools_attempts = getattr(self, '_static_tools_attempts', 0) + 1
                prepared = ensure_binding_tools(self.flow.output_dir, timeout=min(60, int(allowance)))
                self.flow.metric('static_tools_readiness', **prepared)
                if prepared['status'] == 'ready':
                    result = check_batch(self.flow.output_dir, changed, budget=30, sources=sources)
                    break
            else:
                break
        # Manifest syntax also matters at the project root, outside both ends.
        for rel in changed:
            if rel in files and rel.endswith('.json'):
                try:
                    json.loads(files[rel])
                except (ValueError, UnicodeError) as exc:
                    result['errors'].append(f'{rel}: invalid JSON: {exc}')
        unresolved = [item for item in result['deferred'] if not item.startswith('frontend build:')]
        self.static_incomplete = bool(unresolved)
        error = ('application static checks failed or incomplete:\n' + '\n'.join(result['errors'] + unresolved)
                 if result['errors'] or unresolved else '')
        self.flow.metric('layered_static_gate', source=key, **result)
        if not unresolved:  # a timed-out/unavailable check must be retried
            self.static_cache[key] = error
        return error

    def gate(self, node_id):
        flow = self.flow
        try:
            self.wait_basic(node_id)
            specs = self.basic_specs(node_id)
        except GateBlocked:
            if self.safe:
                self.safe.restore()
                restored = self.run_basic()
                if not self.complete(restored, self.basic_specs()) or not restored.all_passed:
                    raise GateBlocked(f'{node_id}: blocked basic publication rollback was not verified')
            raise
        for attempt in range(flow.repair_rounds + 1):
            measured = self.run_basic(node_id)
            if self.complete(measured, specs) and measured.all_passed:
                flow.commit(f'{node_id}: frozen basic gate passed')
                self.state.data['nodes'][node_id].update(code_done=True, basic='passed', source=flow.app_source_digest())
                self.state.save()
                self.safe = ApplicationSnapshot(flow)
                flow.metric('basic_gate', node_id=node_id, status='passed')
                return
            self.state.data['nodes'][node_id]['last_basic_failure'] = {
                'source': flow.app_source_digest(), 'error': measured.error,
                'results': [{'title': row.title, 'status': row.status, 'message': row.message}
                            for row in measured.results]}
            self.state.save()
            if (getattr(self, 'static_incomplete', False) or measured.runtime_uncertain
                    or attempt >= flow.repair_rounds or flow.remaining() <= flow.final_measurement_reserve() + 30 or flow.wound_down()):
                if self.safe:
                    self.safe.restore()
                    flow.commit('restore application after blocked basic gate')
                    restored = self.run_basic()
                    if not self.complete(restored, self.basic_specs()) or not restored.all_passed:
                        raise GateBlocked(f'{node_id}: basic rollback could not be verified')
                raise GateBlocked(f'{node_id}: basic tests or application health did not pass: {measured.error or "failing assertions"}')
            self.repair(node_id, measured, [], basic=True)

    def repair(self, node_id, summary, identities, *, basic=False):
        flow = self.flow
        before = ApplicationSnapshot(flow)
        from main import failure_summaries
        evidence = failure_summaries(summary) or summary.error or 'incomplete test/health measurement'
        cases = [{k: self.state.data['cases'][key][k] for k in ('node_id', 'title', 'scenario')}
                 | {'case_id': key, 'repair_attempt': self.state.data['stops'][key]['attempts']} for key in identities]
        directory = flow.basic_tests_dir if basic else flow.tests_dir
        files = self.basic_specs(node_id) if basic else sorted({self.state.data['cases'][key]['file'] for key in identities})
        frozen_evidence = {file: {rel: raw.decode() for rel, raw in dependency_files(directory, file).items()}
                           for file in files}
        rule = ('' if basic else '\nIf a test is wrong, return <<<TEST_DISPUTE>>> '
                '{"case_ids":[supplied IDs],"reason":"specific wrong action or expectation"} '
                '<<<END TEST_DISPUTE>>>. It immediately terminates those tests without another review. '
                'A separate read-only KEEP/ROLLBACK decision follows two measured failed repairs. '
                'Retained source must preserve all frozen basic tests and application health.')
        prompt = (f'Fix the application for node {node_id} using only the frozen authoritative failure below. '
                  'Do not create, run or modify tests. Preserve prior working behavior.\n'
                  + flow.repair_requirements(node_id if node_id in self.state.data['nodes'] else None)
                  + '\n' + evidence + '\nCASES: '
                  + json.dumps(cases, ensure_ascii=False) + '\nFROZEN TEST EVIDENCE:\n'
                  + json.dumps(frozen_evidence, ensure_ascii=False) + rule + '\n' + flow.sources_text())
        if flow.remaining() <= flow.final_measurement_reserve() + 30 or flow.wound_down():
            raise GateBlocked('insufficient protected repair/rollback budget')
        timeout = min(flow.node_timeout, max(1, flow.remaining() - flow.final_measurement_reserve()))
        flow.last_programmer_reply = ''
        try:
            if flow.codegen_mode():
                flow.codegen_turn(prompt, timeout, 'basic repair' if basic else 'business repair', request_budget=1)
                reply = flow.last_programmer_reply
            else:
                _, reply = flow.turn(prompt, timeout, 'basic repair' if basic else 'business repair', request_budget=1)
        except Exception:
            before.restore()
            if not basic:
                restored = self.run_basic()
                if not self.complete(restored, self.basic_specs()) or not restored.all_passed:
                    raise GateBlocked('interrupted repair rollback did not pass basic protection')
            raise
        if not basic:
            for match in re.finditer(r'<<<TEST_DISPUTE>>>\s*(.*?)\s*<<<END TEST_DISPUTE>>>', str(reply), re.S):
                try:
                    dispute = json.loads(match[1])
                except ValueError:
                    continue
                if (not isinstance(dispute, dict) or not isinstance(dispute.get('reason'), str)
                        or not dispute['reason'].strip() or not isinstance(dispute.get('case_ids'), list)
                        or not all(isinstance(key, str) and key in identities for key in dispute['case_ids'])
                        or not dispute['case_ids']):
                    flow.metric('business_dispute', status='invalid_record')
                    continue
                for key in dispute['case_ids']:
                    self.state.dispute(key, dispute['reason'])
            protected = self.run_basic()
            rollback = ('<<<ROLLBACK CODE>>>' in str(reply) or not self.complete(protected, self.basic_specs())
                        or not protected.all_passed)
            if rollback:
                before.restore()
                flow.commit('restore application after unsafe business repair')
                protected = self.run_basic()
                if not self.complete(protected, self.basic_specs()) or not protected.all_passed:
                    raise GateBlocked('rollback did not restore basic tests and application health')
            else:
                flow.commit('retain business repair with basic and health protection')
            self.safe = ApplicationSnapshot(flow)
            for key in identities:
                self.state.data['cases'][key]['retention'] = 'rollback' if rollback else 'retain_checked_application'
                self.repair_preimages[key] = before
            self.state.save()
        return reply

    def publish_business(self):
        flow = self.flow
        if not getattr(flow, 'derived_as_specs', False):
            return
        directory = flow.derived_tests_dir
        reviews = getattr(flow, 'derived_case_reviews', {})
        review_version = digest([[list(key), value] for key, value in reviews.items()])
        if review_version == self.business_reviews_version and time.monotonic() < self.business_publication_retry_at:
            return
        self.business_reviews_version = review_version
        self.business_publication_retry_at = float('inf')
        changed = False
        for (node_id, title), review in reviews.items():
            if review.get('status') != 'approved_behavior' or not flow.trusted_derived_case(node_id, title):
                continue
            scenario = str(review.get('scenario_id') or title)
            if (node_id, scenario) in flow.terminal_derived_scenarios():
                continue  # a late producer reply cannot replace a stopped case
            ordinal = re.search(r'\[case (\d+)\]', title)
            kind = 'script' if '[script]' in title else 'model'
            stable_case = f'{scenario}:{kind}:{ordinal[1] if ordinal else "0"}'
            identity = self.state.identity(node_id, stable_case)
            if identity in self.state.data['cases']:
                continue
            gap_key = digest([node_id, title])[:24]
            rel = review.get('file')
            if (not isinstance(rel, str) or not rel or Path(rel).is_absolute() or '..' in Path(rel).parts
                    or str(node_id) not in self.state.data['nodes']):
                self.state.data['publication_gaps'][gap_key] = {'node_id': node_id, 'reason': 'explicit reviewed file/owner missing'}
                changed = True
                continue  # ownership and file must be supplied by the reviewed manifest
            files = dependency_files(directory, rel)
            version = digest({key: digest(raw) for key, raw in files.items()})[:16]
            publication = directory / 'published' / version
            if not publication.exists():
                temporary = Path(tempfile.mkdtemp(prefix='.publish-', dir=directory))
                try:
                    for name, raw in files.items():
                        path = temporary / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                    publication.parent.mkdir(exist_ok=True)
                    temporary.replace(publication)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            path = f'published/{version}/{rel}'
            self.state.data['cases'][identity] = {'id': identity, 'node_id': node_id, 'title': title,
                'scenario': scenario, 'level': 'business', 'file': path, 'status': 'pending',
                'dependencies': {f'published/{version}/{key}': digest(raw) for key, raw in files.items()},
                'review': copy.deepcopy(review)}
            if not self.dependencies_intact(self.state.data['cases'][identity]):
                del self.state.data['cases'][identity]
                raise GateBlocked('published business dependency changed before manifest commit')
            if path not in self.business_discovery_cache:
                discovered, detail = flow.runner.discover_cases([path]) if flow.runner else ([], 'runner unavailable')
                if discovered and not detail:
                    self.business_discovery_cache[path] = (discovered, detail)
            else:
                discovered, detail = self.business_discovery_cache[path]
            selected = [row for row in discovered if row['title'] == title]
            if len(selected) != 1:
                del self.state.data['cases'][identity]
                flow.metric('business_publication', node_id=node_id, status='load_blocked', reason=str(detail))
                self.state.data['publication_gaps'][gap_key] = {'node_id': node_id, 'reason': str(detail) or 'case discovery mismatch'}
                changed = True
                self.business_publication_retry_at = time.monotonic() + 5
                continue
            self.state.data['cases'][identity].update(line=selected[0].get('line'), frozen_at=time.time())
            self.state.data['publication_gaps'].pop(gap_key, None)
            changed = True
            if not self.dependencies_intact(self.state.data['cases'][identity]):
                del self.state.data['cases'][identity]
                raise GateBlocked('business dependency changed during discovery')
        if changed:
            self.state.save()
            flow.snapshot_protected()

    def dependencies_intact(self, row):
        return all((self.flow.tests_dir / key).is_file() and not (self.flow.tests_dir / key).is_symlink()
                   and (self.flow.tests_dir / key).resolve().is_relative_to(self.flow.tests_dir.resolve())
                   and digest((self.flow.tests_dir / key).read_bytes()) == value
                   for key, value in row['dependencies'].items())

    def selected(self, specs):
        self.case_inclusions = {}
        if getattr(self.flow, '_layered_execution_level', None) == 'basic':
            allowed = set(self.basic_specs(getattr(self.flow, '_layered_current_node', None)))
            return len(specs) if set(specs) <= allowed else 0, {}
        if self.state.data['phase'] != 'business' or not all(r['code_done'] for r in self.state.data['nodes'].values()):
            return 0, {}
        if self.verified_basic_source != self.flow.app_source_digest():
            return 0, {}  # all-node admission flags cannot substitute for current-source protection
        rows = [row for row in self.state.data['cases'].values() if row['file'] in specs
                and (self.active_case_ids is None or row['id'] in self.active_case_ids)]
        excluded, active = {}, 0
        for spec in specs:
            allowed = []
            for row in rows:
                if row['file'] != spec or self.state.data['stops'].get(row['id'], {}).get('state') == 'disputed':
                    continue
                if not self.dependencies_intact(row):
                    return 0, {}
                allowed.append({'title': row['title'], 'line': row.get('line')})
            if not allowed:
                return 0, {}
            self.case_inclusions[spec] = allowed
            active += len(allowed)
        return active, excluded

    def decide_exhausted(self, row, summary):
        """An observed second failure permits a decision, never a third edit."""
        key, flow = row['id'], self.flow
        stop = self.state.data['stops'][key]
        if stop.get('decision_attempted'):
            return
        stop['decision_attempted'] = True
        self.state.save()  # crashes/resume cannot dispatch a second decision
        decision, reason = 'KEEP', 'retain the already checked version; decision budget unavailable'
        before = ApplicationSnapshot(flow)
        if flow.remaining() > flow.final_measurement_reserve() + 30 and not flow.wound_down():
            prompt = ('Both application repair attempts have finished and this authoritative business test '
                      'still fails. Choose KEEP for the current version or ROLLBACK for the pre-second-repair '
                      'version. This is a read-only decision; no code, tools, new tests, review or third repair. '
                      'Return JSON {decision:"KEEP"|"ROLLBACK",reason:"specific reason"}. '
                      'Both choices must preserve all basic tests and health.\n'
                      + json.dumps({'case': {k: row[k] for k in ('id', 'node_id', 'title', 'scenario')},
                                    'failure': row.get('failure'), 'attempts': stop['attempts'],
                                    'current_source': flow.app_source_digest(),
                                    'rollback_available': key in self.repair_preimages}, ensure_ascii=False))
            try:
                ok, reply = flow.text_turn(prompt, min(120, flow.remaining() - flow.final_measurement_reserve()),
                                          'business exhausted retention decision',
                                          system='Return a read-only JSON decision. No tools or code.', request_budget=1)
                answer = json.loads(reply) if ok else {}
            except Exception as exc:
                flow.metric('business_retention_decision', case_id=key, status='request_unavailable', reason=str(exc))
                answer = {}
            if (isinstance(answer, dict) and answer.get('decision') in {'KEEP', 'ROLLBACK'}
                    and isinstance(answer.get('reason'), str) and answer['reason'].strip()):
                decision, reason = answer['decision'], answer['reason']
        if ApplicationSnapshot.capture(flow) != before.files:
            before.restore()
            reason += '; decision request attempted an edit, which was discarded'
        if decision == 'ROLLBACK' and key in self.repair_preimages:
            self.repair_preimages[key].restore()
            protected = self.run_basic()
            if not self.complete(protected, self.basic_specs()) or not protected.all_passed:
                before.restore()
                protected = self.run_basic()
                if not self.complete(protected, self.basic_specs()) or not protected.all_passed:
                    raise GateBlocked('retention decision rollback failed basic/health protection')
                decision, reason = 'KEEP', reason + '; rollback unavailable after protection failure'
            else:
                flow.commit('author chose checked rollback after two failed business repairs')
        elif decision == 'ROLLBACK':
            decision, reason = 'KEEP', reason + '; pre-second-repair version unavailable after resume'
        self.safe = ApplicationSnapshot(flow)
        row['retention'] = 'rollback' if decision == 'ROLLBACK' else 'retain_checked_application'
        stop.update(decision=decision, decision_reason=reason, state='repair_exhausted')
        self.state.save()
        flow.metric('business_retention_decision', case_id=key, decision=decision, reason=reason)

    def deliver_blocked(self, reason):
        """Preserve a measured partial application without releasing later nodes."""
        self.state.data['termination'] = 'basic_gate_blocked'
        self.state.data['termination_reason'] = str(reason)
        self.state.save()
        if self.safe is None or not any(row['code_done'] for row in self.state.data['nodes'].values()):
            return False
        self.safe.restore()
        self.flow._layered_current_node = None
        measured = self.run_basic()
        if not self.complete(measured, self.basic_specs()) or not measured.all_passed:
            return False
        ready = self.flow.rehearsal(repair_on_failure=False, restore_on_failure=False)
        self.flow.metric('blocked_delivery', status='partial_ready' if ready else 'not_ready',
                         completed_nodes=[key for key, row in self.state.data['nodes'].items() if row['code_done']])
        return ready

    def execute_business(self):
        if self.state.data['phase'] != 'business' or not all(n['code_done'] for n in self.state.data['nodes'].values()):
            raise GateBlocked('business execution requires every node basic gate')
        pending = [row for row in self.state.data['cases'].values() if row['status'] == 'pending']
        initial, initial_source = {}, self.flow.app_source_digest()
        if pending and self.flow.remaining() > self.flow.final_measurement_reserve() and not self.flow.wound_down():
            # One build/start/health cycle for this immutable source and frozen
            # queue. Browser cases remain sequential with normal fixture reset.
            specs = sorted({row['file'] for row in pending})
            self.active_case_ids = {row['id'] for row in pending}
            measured = self.flow.run_specs(specs)
            if self.complete(measured, specs):
                from runtime_diagnostics import application_failures
                unhealthy = bool(application_failures(measured))
                for row in pending:
                    results = [r for r in measured.results if self.matches(r, row, specs)]
                    subset = RunSummary(total=len(results), passed=sum(r.ok for r in results), results=results)
                    initial[row['id']] = subset
                    if results and all(r.ok for r in results) and not unhealthy:
                        row.update(status='passed', source=initial_source)
            else:
                for row in pending:
                    row.update(status='unmeasured', failure=measured.error or 'incomplete batched measurement')
        for row in pending:
            if row['status'] != 'pending':
                continue
            key, specs = row['id'], [row['file']]
            self.active_case_ids = {key}
            while True:
                if self.state.data['stops'].get(key, {}).get('state') == 'disputed':
                    row['status'] = 'disputed'
                    break
                if self.flow.time_up() or self.flow.wound_down() or self.flow.remaining() <= self.flow.final_measurement_reserve():
                    row['status'] = 'unmeasured'
                    break
                summary = initial.pop(key, None) if self.flow.app_source_digest() == initial_source else None
                if summary is None:
                    summary = self.flow.run_specs(specs)
                outcomes = [r for r in summary.results if self.matches(r, row, specs)]
                from runtime_diagnostics import application_failures
                if self.complete(summary, specs) and outcomes and all(r.ok for r in outcomes) and not application_failures(summary):
                    row.update(status='passed', source=self.flow.app_source_digest())
                    break
                row['failure'] = summary.error or '\n'.join(r.message or r.status for r in outcomes)
                if not outcomes or not self.complete(summary, specs):
                    row['status'] = 'unmeasured'
                    break  # infrastructure gaps never request a behavior implementation
                if self.flow.remaining() <= self.flow.final_measurement_reserve() + 30:
                    row['status'] = 'unmeasured'
                    break
                if not self.state.begin_repair([key]):
                    row['status'] = 'repair_exhausted'
                    self.state.data['stops'].setdefault(key, {})['state'] = 'repair_exhausted'
                    self.decide_exhausted(row, summary)
                    break
                self.repair(row['node_id'], summary, [key])
                if self.flow.time_up() or self.flow.wound_down():
                    row['status'] = 'unmeasured'
                    break
            self.state.save()
        self.active_case_ids = None
        self.state.save()

    def business(self):
        flow = self.flow
        if not all(row['code_done'] for row in self.state.data['nodes'].values()):
            raise GateBlocked('business execution requires every node basic gate')
        protection = self.run_basic()
        if not self.complete(protection, self.basic_specs()) or not protection.all_passed:
            if self.safe:
                self.safe.restore()
                protection = self.run_basic()
            if not self.complete(protection, self.basic_specs()) or not protection.all_passed:
                raise GateBlocked('final basic protection set did not pass')
        self.state.data['phase'] = 'business'
        self.state.save()
        self.poll_basic()
        pipeline = getattr(flow, '_derived_background_pipeline', None)
        if pipeline:
            pipeline.resume()
        if not getattr(flow, 'derived_as_specs', False):
            # Supplied official tests are immutable and execute only now.
            for node_id, paths in flow.spec_map.items():
                for rel in paths:
                    files = dependency_files(flow.tests_dir, rel)
                    discovered, error = flow.runner.discover_cases([rel]) if flow.runner else ([], 'official runner unavailable')
                    if not discovered:
                        raise GateBlocked(f'official spec discovery failed: {rel}: {error}')
                    owners = [str(node_id)] if node_id is not None else list(self.state.data['nodes'])
                    for case in discovered:
                        title, line = case['title'], case.get('line')
                        key = self.state.identity(str(node_id), rel + ':' + title + ':' + str(line))
                        self.state.data['cases'].setdefault(key, {'id': key, 'node_id': str(node_id), 'title': title,
                            'scenario': rel + ':' + title, 'level': 'business', 'file': rel, 'status': 'pending',
                            'line': line, 'owners': owners, 'frozen_at': time.time(),
                            'dependencies': {name: digest(raw) for name, raw in files.items()}})
                        if not self.dependencies_intact(self.state.data['cases'][key]):
                            raise GateBlocked('official frozen dependency changed')
            self.state.data['business_tasks'] = {key: 'finished' for key in self.state.data['nodes']}
        while True:
            flow.poll_background_specs()
            self.publish_business()
            self.execute_business()
            pipeline = getattr(flow, '_derived_background_pipeline', None)
            if pipeline is None or pipeline.wait(0):
                # Drain the last publication after the producer has stopped.
                # A queue observed empty just before completion is insufficient.
                flow.poll_background_specs()
                self.publish_business()
                self.execute_business()
                for node in self.ordered:
                    node_id = str(node['id'])
                    if self.state.data['business_tasks'][node_id] != 'pending':
                        continue
                    completed = getattr(flow, '_derived_spec_batch_completed_ids', set())
                    if node_id not in completed and node_id not in getattr(flow, '_background_spec_scheduled_ids', set()):
                        if flow.time_up() or flow.wound_down() or flow.remaining() <= flow.final_measurement_reserve():
                            self.state.data['business_tasks'][node_id] = 'not_started_budget'
                            continue
                        flow.prepare_derived_spec_batch([node])
                        self.publish_business()
                        self.execute_business()
                    self.state.data['business_tasks'][node_id] = ('finished_with_gap' if flow.derived_review_needed(node_id)
                                                                 else 'finished')
                self.business_producer_done = all(value.startswith('finished') for value in self.state.data['business_tasks'].values())
                if pipeline:
                    pipeline.close(0)
                    flow.poll_background_specs()
                break
            if flow.remaining() <= flow.final_measurement_reserve() or flow.time_up() or flow.wound_down():
                self.cancelled = True
                pipeline.close(0)
                self.state.data['termination'] = 'budget_exhausted'
                break
            time.sleep(.5)
        self.state.save()
        self.final_verify()

    def final_verify(self):
        flow = self.flow
        if self.state.data['phase'] != 'business':
            return
        self.active_case_ids = None
        self.basic_specs()  # cached execution never excuses changed frozen dependencies
        if any(not self.dependencies_intact(row) for row in self.state.data['cases'].values()
               if self.state.data['stops'].get(row['id'], {}).get('state') != 'disputed'):
            raise GateBlocked('final frozen business dependency changed')
        signature = digest([flow.app_source_digest(), self.state.data['cases'], self.state.data['stops'],
                            self.state.data['business_tasks'], self.business_producer_done, self.state.data['publication_gaps']])
        if self.final_signature == signature:
            return  # the exact source/manifest was fully rechecked; no redundant run
        basic = self.run_basic()
        if not self.complete(basic, self.basic_specs()) or not basic.all_passed:
            if self.safe:
                self.safe.restore()
                basic = self.run_basic()
            if not self.complete(basic, self.basic_specs()) or not basic.all_passed:
                raise GateBlocked('delivery basic/health verification failed')
        # Recheck exact final source without reopening any repair budget.
        specs = sorted({row['file'] for row in self.state.data['cases'].values()
                        if self.state.data['stops'].get(row['id'], {}).get('state') != 'disputed'})
        if specs:
            summary = flow.run_specs(specs, grader_like=True)
            from runtime_diagnostics import application_failures
            measured = self.complete(summary, specs) and not application_failures(summary)
            for row in self.state.data['cases'].values():
                if self.state.data['stops'].get(row['id'], {}).get('state') == 'disputed':
                    row['status'] = 'disputed'
                    continue
                outcomes = [r for r in summary.results if self.matches(r, row, specs)]
                row['status'] = ('passed' if measured and outcomes and all(r.ok for r in outcomes)
                                 else 'repair_exhausted' if self.state.data['stops'].get(row['id'], {}).get('attempts', 0) >= 2
                                 else 'failed' if outcomes else 'unmeasured')
                row['source'] = flow.app_source_digest()
        for node_id in self.state.data['nodes']:
            rows = [row for row in self.state.data['cases'].values() if row['node_id'] == node_id or node_id in row.get('owners', [])]
            flow.test_verdict[node_id] = (bool(rows) and all(row['status'] == 'passed' for row in rows)
                and self.business_producer_done and not flow.derived_review_needed(node_id)
                and not any(gap['node_id'] == node_id for gap in self.state.data['publication_gaps'].values()))
        self.state.save()
        self.final_signature = digest([flow.app_source_digest(), self.state.data['cases'], self.state.data['stops'],
                                       self.state.data['business_tasks'], self.business_producer_done, self.state.data['publication_gaps']])
        self.safe = ApplicationSnapshot(flow)

    def close(self):
        self.cancelled = True
        if self.basic_pipeline:
            self.basic_pipeline.close(0)
        pipeline = getattr(self.flow, '_derived_background_pipeline', None)
        if pipeline:
            pipeline.close(0)
        self.state.save()
