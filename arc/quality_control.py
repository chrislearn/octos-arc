"""Task-neutral quality evidence and bounded recovery. No provider calls."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from contextlib import contextmanager


def preserves_design(accepted: dict, candidate: dict) -> bool:
    """Category recovery may add contracts, but cannot silently overwrite accepted ones."""
    for key, value in accepted.items():
        if key == 'notes':
            continue
        proposed = candidate.get(key, {} if isinstance(value, dict) else [])
        if isinstance(value, dict) and (not isinstance(proposed, dict) or any(proposed.get(k) != v for k, v in value.items())):
            return False
        if isinstance(value, list) and any(item not in proposed for item in value):
            return False
    return True


def blocked_design_owners(tree: dict, design: dict, wanted: set[str], reviewed: bool) -> set[str]:
    """Unresolved shared entities block their owners; unnamed ownership blocks the shared dependency."""
    from domain_contracts import contract_manifest
    manifest = contract_manifest(tree, design)
    blocked = set()
    for entity in manifest['entities']:
        incomplete = any(not entity.get(key) or entity[key] == 'unresolved'
                         for key in ('identity', 'storage', 'producers', 'consumers'))
        if incomplete or not reviewed:
            blocked.update(set(entity.get('requirements') or wanted) & wanted)
    if design.get('commands') and not reviewed:
        for command in design['commands']:
            blocked.update(set(command.get('requirements') or wanted) & wanted)
    return blocked


@contextmanager
def recovery_budget(flow):
    """One extra stage allowance, still bounded by global time/tokens and configured caps.

    Preserve cumulative usage after recovery. Explicit zero caps remain zero.
    Restoring stage state in finally prevents the final measurement inheriting a stale deadline.
    """
    counters = ('derived_obligation_seconds', 'derived_review_requests', 'derived_llm_seconds', 'derived_case_review_requests',
                'derived_case_review_seconds', 'derived_case_correction_requests', 'review_turn_count')
    saved = {key: getattr(flow, key, 0) for key in counters}
    temporary = ('derived_preflight_deadline', 'derived_preflight_start_tokens', '_in_final_repair',
                 '_completeness_active', 'derived_model_phase_requests', 'derived_case_review_phase_requests')
    prior = {key: getattr(flow, key) for key in temporary if hasattr(flow, key)}
    for key in counters:
        setattr(flow, key, 0)
    flow._in_final_repair = flow._completeness_active = True
    flow.derived_model_phase_requests = {}
    flow.derived_case_review_phase_requests = {}
    used = getattr(getattr(flow, 'llm_proxy', None), 'total_tokens', 0)
    flow.derived_preflight_start_tokens = used if isinstance(used, int) else 0
    try:
        yield
    finally:
        extra = {key: getattr(flow, key, 0) for key in counters}
        for key, value in saved.items():
            setattr(flow, key, value + extra[key])
        for key in temporary:
            if key in prior:
                setattr(flow, key, prior[key])
            elif hasattr(flow, key):
                delattr(flow, key)
        flow.metric('recovery_budget', stage_usage=extra, cumulative={key: getattr(flow, key) for key in counters})


def helper_evidence_hash(directory: Path) -> str:
    helper = directory / 'helpers.ts'
    if not helper.is_file():
        return ''
    source = helper.read_text(encoding='utf-8')
    # Preserve compatibility for self-contained helpers; include all local dependencies otherwise.
    if re.search(r'(?:from\s+|require\(\s*)[\'\"]\.', source):
        source = review_evidence(directory)
    return hashlib.sha256(source.encode()).hexdigest()


def repair_allowance(initial: int, maximum: int, progress: bool) -> int:
    return max(0, maximum if progress else min(initial, maximum))


def valid_json_schema(schema, depth=0) -> bool:
    """Exactly the subset supported by the generated browser helper, never silently ignore keywords."""
    if not isinstance(schema, dict) or not schema or depth > 8 or set(schema) - {
            'type', 'enum', 'required', 'properties', 'items', 'additionalProperties'}:
        return False
    if 'type' in schema and schema['type'] not in ('object', 'array', 'string', 'number', 'integer', 'boolean', 'null'):
        return False
    if 'enum' in schema and (not isinstance(schema['enum'], list) or not schema['enum']):
        return False
    if 'required' in schema and (not isinstance(schema['required'], list) or
                               not all(isinstance(k, str) for k in schema['required'])):
        return False
    if 'additionalProperties' in schema and type(schema['additionalProperties']) is not bool:
        return False
    if 'properties' in schema and (not isinstance(schema['properties'], dict) or
                                  not all(valid_json_schema(s, depth + 1) for s in schema['properties'].values())):
        return False
    return 'items' not in schema or valid_json_schema(schema['items'], depth + 1)


def context_evidence(root: Path, request: dict, available: set[str], seen: dict) -> tuple[str, dict]:
    """Read only source snapshots; symlinks/data and duplicate requests fail closed."""
    versions, blocks = {}, []
    for name in request['paths']:
        path = root / name
        if name not in available or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('unavailable or non-source context path: ' + name)
        content = path.read_text(encoding='utf-8')
        version = hashlib.sha256(content.encode()).hexdigest()
        versions[name] = version
        if seen.get(name) != version:
            blocks.append(f'--- {name} ---\n{content}\n')
    if not blocks:
        raise ValueError('context request repeats unchanged evidence; use the supplied source')
    return '\n'.join(blocks), versions


def review_evidence(directory: Path) -> str:
    """Include the entire transitive local helper set, never a truncated function."""
    directory = directory.resolve()
    found, pending = {}, [directory / 'helpers.ts']
    while pending:
        try:
            path = pending.pop().resolve()
        except (OSError, RuntimeError):
            continue
        if path in found or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
            continue
        source = path.read_text(encoding='utf-8')
        found[path] = source
        for name in re.findall(r'(?:from\s+|require\(\s*)[\'\"](\.[^\'\"]+)', source):
            base = path.parent / name
            pending.extend([base, base.with_suffix('.ts'), base.with_suffix('.js'), base / 'index.ts'])
    return '\n'.join(f'--- {p.relative_to(directory)} ---\n{s}' for p, s in sorted(found.items()))


def export_contracts(root: Path, tree: dict, design: dict | None, status: str) -> dict:
    """Preserve the full source obligations even when model design is unavailable."""
    from domain_contracts import contract_manifest, requirement_index
    manifest = contract_manifest(tree, design)
    manifest['design_status'] = status
    destination = root / 'design'
    destination.mkdir(parents=True, exist_ok=True)
    obligations = []
    def visit(node):
        if not isinstance(node, dict):
            return
        owner = str(node.get('id') or '')
        if owner:
            if node.get('description'):
                obligations.append({'id': owner + ':description', 'requirement_id': owner,
                    'source': 'official', 'location': 'description', 'quote': node['description'],
                    'status': 'awaiting_behavior_evidence'})
            for index, scenario in enumerate(node.get('scenarios') or []):
                obligations.append({'id': f'{owner}:scenario:{index}', 'requirement_id': owner,
                    'source': 'official', 'location': f'scenarios/{index}', 'quote': scenario,
                    'status': 'awaiting_behavior_evidence'})
        for child in node.get('children') or []:
            visit(child)
    visit(tree)
    # Model-proposed atomic obligations supplement, never remove, original source units.
    for obligation in (design or {}).get('obligations', []):
        obligations.append({**obligation, 'source': 'official_quote', 'status': 'awaiting_behavior_evidence'})
    docs = {
        'domain-model': manifest,
        'commands': (design or {}).get('commands', []),
        'routes': {k: (design or {}).get(k, []) for k in ('routes', 'pages')},
        'shared-contracts': (design or {}).get('domain_contracts', []),
        'obligations': [{'id': key, 'source': 'official', 'text': text,
                         'status': 'awaiting_behavior_evidence'} for key, text in requirement_index(tree).items()],
    }
    for name, content in docs.items():
        (destination / (name + '.json')).write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
    requirement_dir = root / 'requirements'
    requirement_dir.mkdir(exist_ok=True)
    (requirement_dir / 'obligations.json').write_text(json.dumps(obligations, ensure_ascii=False, indent=2) + '\n')
    (requirement_dir / 'original.json').write_text(json.dumps(tree, ensure_ascii=False, indent=2) + '\n')
    (destination / 'traceability.json').write_text(json.dumps([
        {'obligation_id': row['id'], 'requirement_id': row['requirement_id'],
         'commands': [c['name'] for c in (design or {}).get('commands', [])
                      if row['requirement_id'] in c.get('requirements', [])],
         'tests': [], 'status': 'awaiting_behavior_evidence'} for row in obligations
    ], ensure_ascii=False, indent=2) + '\n')
    return manifest


def concrete_health_paths(design: dict | None) -> list[str]:
    """Only literal declared pages; never invent values for dynamic parameters."""
    paths = ['/']
    for page in (design or {}).get('pages', []):
        route = page.get('path', '')
        if (isinstance(route, str) and route.startswith('/') and not route.startswith('//')
                and not re.search(r'[:*{}?]', route) and route not in paths):
            paths.append(route)
    return paths


def dynamic_health_patterns(design: dict | None) -> list[str]:
    """Declared detail pages can be resolved from visible links, never guessed IDs."""
    patterns = []
    for page in (design or {}).get('pages', []):
        if not isinstance(page, dict):
            continue
        route = page.get('path', '')
        if (isinstance(route, str) and route.startswith('/') and not route.startswith('//')
                and re.search(r'(?<=/):[A-Za-z_][A-Za-z0-9_]*', route)
                and not re.search(r'[?*{}]', route) and route not in patterns):
            patterns.append(route)
    return patterns[:3]


BUSINESS_QUALITY_GUIDANCE = '''
Extract obligations [{id, requirement_id, quote, branch, outcome}] from exact original requirement quotes.
Each independent hard outcome/format/error/state rule needs its own obligation; branch is success/rejection/mixed.
'''

TEST_QUALITY_GUIDANCE = '''
Include every applicable successful branch and preserve the original requirements when duplicate flows are merged.
For each applicable business category, generate a complete SUCCESS workflow as well as rejection cases.
Use real signed-in browser credentials across protected modules; a visible username alone proves no access.
Assert state after each decisive action and after reload. Negative-only checks never prove the successful branch.
Use one credential resolver and one requirement-derived effective authorization policy across list/detail/search/write.
Keep credential tokens distinct from session and account IDs. Do not catch failed loads as successful empty lists.
Check root and child API paths, route parameters, nested page mounting, direct navigation and refresh.
Reduce event/review histories by identity AND current object version according to requirements, not any past success.
Reread authoritative versions before commit; multi-object failure must leave all business objects unchanged.
Check every enabled condition independently. Never hardcode eligibility/conflicts to true/false.
Tests must exercise these properties through applicable UI/API contracts, without inventing product features.
Official schemas, enums, field names and error wording are binding; inferred choices must be identified as such.
'''

BUSINESS_QUALITY_GUIDANCE += TEST_QUALITY_GUIDANCE
