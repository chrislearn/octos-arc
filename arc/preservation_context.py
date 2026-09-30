"""Previously measured contracts relevant to an edit, before it can regress them."""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re


HEADER = 'Previously verified requirements to preserve or restore (original authority):'
INHERITED_HEADER = 'Active ancestor requirements (original authority; apply within the active node):'
_START = '<OCTOS_PRESERVATION_CONTEXT>'
_END = '</OCTOS_PRESERVATION_CONTEXT>'
_HUBS = {'App.jsx', 'App.tsx', 'app.js', 'router.js', 'main.jsx', 'main.tsx', 'server.js'}


@dataclass
class PreservationContext:
    text: str = ''
    owners: tuple[str, ...] = ()
    omitted: tuple[str, ...] = ()
    inherited: tuple[str, ...] = ()


def strip_context(text):
    """Replace framework-framed context after rebuilding source ownership."""
    for start, end in ((_START, _END), ('<OCTOS_ANCESTOR_CONTEXT>', '</OCTOS_ANCESTOR_CONTEXT>')):
        text = re.sub(r'(?ms)^' + re.escape(start) + r'\n.*?^' + re.escape(end) + r'\n?', '', text)
    return text


def ancestor_nodes(tree, active_ids):
    """Quote ancestor descriptions only, without expanding sibling feature work."""
    if not isinstance(tree, dict):
        return {}
    active, selected, visited = set(active_ids), {}, set()
    def visit(node, parents):
        if not isinstance(node, dict) or id(node) in visited:
            return
        visited.add(id(node))
        if str(node.get('id')) in active:
            for parent in parents:
                if parent.get('description'):
                    selected.setdefault(str(parent.get('id') or 'root'), parent)
        for child in node.get('children') or []:
            visit(child, parents + [node])
    visit(tree, [])
    return selected


def select_owners(nodes, active_ids, proven_ids, targets, edit_paths, index, folders=None):
    """Dependencies first, then owners affected by concrete shared source paths.

    A previously red owner remains relevant if it was ever measured green.
    Composition roots cannot make every feature relevant; ambiguous ownership
    still belongs to regression execution, not an unbounded generation prompt.
    """
    active = set(active_ids)
    proven = (set(proven_ids) & nodes.keys()) - active
    dependencies, visited, pending = set(), set(), list(active)
    folders = folders or {}
    while pending:
        owner = pending.pop()
        if owner in visited:
            continue
        visited.add(owner)
        pending.extend(folders.get(owner, ()))
        pending.extend(str(dep) for dep in nodes.get(owner, {}).get('dependencies', ()))
        if owner in proven:
            dependencies.add(owner)
    paths = {str(path) for path in edit_paths
             if PurePosixPath(str(path)).name not in _HUBS}
    affected = index.affected(paths) if paths else set()
    related = {owner for owner in proven if affected & set(targets.get(owner, ()))}
    return tuple(sorted(dependencies) + sorted(related - dependencies))


def render_context(nodes, owners, requirements_path, limit=24000, *, inherited=False):
    """Quote whole descriptions; explicitly defer oversized contracts to tools.

    Text-only generation must not proceed when omitted is nonempty. Tool turns
    can read the named original nodes rather than treating a clipped clause or
    the current implementation as authoritative.
    """
    if not owners:
        return PreservationContext()
    prefix = (HEADER + '\nThese owners passed before; this does not claim they still pass now. '
              'A shared-file edit must preserve their required messages, labels, routes, '
              'validation and state transitions. Extend the active behavior without rewriting '
              'unrelated handlers. Requirements override existing defects; restore known regressions.\n')
    if inherited:
        prefix = (INHERITED_HEADER + '\nThese shared constraints come from the active node\'s parents, '
                  'not future sibling work or measured pass claims. Implement the active behavior under them; '
                  'do not move required entry points to another page merely to satisfy a test sequence.\n')
    blocks, omitted, used = [], [], len(prefix)
    for owner in owners:
        node = nodes[owner]
        description = str(node.get('description') or '').strip()
        if not description:
            omitted.append(owner)
            continue
        block = f"\nID: {owner}\nName: {node.get('name', '')}\nDescription: {description}\n"
        if used + len(block) <= max(0, limit):
            blocks.append(block)
            used += len(block)
        else:
            omitted.append(owner)
    suffix = ''
    if omitted:
        suffix = ('\nContracts not quoted whole: ' + ', '.join(omitted) + '. Before editing shared code, '
                  'read these original node descriptions in ' + str(requirements_path) +
                  '; never infer their contract from current code or truncate a requirement.\n')
    start, end = ('<OCTOS_ANCESTOR_CONTEXT>', '</OCTOS_ANCESTOR_CONTEXT>') if inherited else (_START, _END)
    return PreservationContext(start + '\n' + prefix + ''.join(blocks) + suffix + end + '\n',
                               () if inherited else tuple(owners), tuple(omitted),
                               tuple(owners) if inherited else ())
