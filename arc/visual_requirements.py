"""Untrusted reference-image evidence for design and test navigation only."""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
OBSERVATION_KINDS = {'visible_text', 'control', 'layout', 'state', 'uncertainty'}
CERTAINTIES = {'clear', 'uncertain'}
INSTRUCTION = re.compile(
    r'ignore (?:all |the )?(?:previous|prior|system) instructions|'
    r'(?:system|developer) (?:prompt|message)|'
    r'(?:assistant|agent) (?:must|should|shall) (?:ignore|execute|send|change)|'
    r'override (?:the )?(?:rules|policy|instructions)', re.I)


def references(contracts: dict, tree: dict | None = None) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for row in contracts.get('nodes', []):
        node_id = str(row.get('id') or '')
        for value in row.get('reference_images') or []:
            found.setdefault(str(value), set()).add(node_id)
    if isinstance(tree, dict):
        from requirement_contracts import compile_contract
        def visit(node: dict, inherited: list[str]) -> None:
            local = list(compile_contract(node).get('reference_images') or [])
            paths = list(dict.fromkeys(inherited + local))
            children = [child for child in node.get('children') or [] if isinstance(child, dict)]
            if children:
                for child in children:
                    visit(child, paths)
            else:
                for value in paths:
                    found.setdefault(str(value), set()).add(str(node.get('id') or ''))
        visit(tree, [])
    return {path: sorted(ids) for path, ids in found.items()}


def read_reference(root: Path, name: str, *, max_bytes: int = 2_000_000,
                   max_pixels: int = 16_000_000) -> tuple[bytes | None, str, str]:
    """Return decoded image bytes, MIME type and status without path escape."""
    if not name or '://' in name or name.startswith(('/', '\\')) or re.match(r'^[A-Za-z]:', name):
        return None, '', 'rejected_path'
    relative = Path(name)
    if '..' in relative.parts or relative.suffix.lower() not in IMAGE_EXTENSIONS:
        return None, '', 'rejected_path' if '..' in relative.parts else 'unsupported'
    try:
        base = root.resolve(strict=True)
        path = (base / relative).resolve(strict=True)
        if not path.is_relative_to(base) or not path.is_file():
            return None, '', 'rejected_path'
        if path.stat().st_size > max_bytes:
            return None, '', 'unsupported'
        data = path.read_bytes()
    except FileNotFoundError:
        return None, '', 'missing'
    except (OSError, RuntimeError):
        return None, '', 'rejected_path'
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > max_pixels:
                return None, '', 'unsupported'
            fmt = image.format
    except ImportError:
        return None, '', 'unsupported'
    except Exception:
        return None, '', 'unsupported'
    mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp', 'GIF': 'image/gif'}.get(fmt)
    return (data, mime, 'ready') if mime else (None, '', 'unsupported')


def parse_observations(reply: str, *, max_items: int = 24) -> list[dict]:
    """Reject agent-directed instructions; keep only bounded visible facts."""
    if not isinstance(reply, str) or len(reply) > 16000:
        raise ValueError('invalid_visual_reply')
    try:
        value = json.loads(reply)
    except ValueError as exc:
        raise ValueError('invalid_visual_json') from exc
    rows = value.get('observations') if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) > max_items:
        raise ValueError('invalid_visual_schema')
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'kind', 'text', 'region', 'certainty'}:
            raise ValueError('invalid_visual_schema')
        kind, statement, certainty = row.get('kind'), row.get('text'), row.get('certainty')
        region = row.get('region')
        if (kind not in OBSERVATION_KINDS or certainty not in CERTAINTIES
                or not isinstance(statement, str) or not statement.strip() or len(statement) > 400
                or region is not None and (not isinstance(region, str) or len(region) > 100)):
            raise ValueError('invalid_visual_schema')
        if INSTRUCTION.search(statement):
            raise ValueError('instruction_in_visual_reply')
        result.append({'kind': kind, 'text': statement.strip(), 'region': region, 'certainty': certainty})
    return result


def cache_key(image_sha: str, model: str, context_sha: str, prompt_version: str = 'v1') -> str:
    return hashlib.sha256(json.dumps([image_sha, model, context_sha, prompt_version],
                                     ensure_ascii=False).encode()).hexdigest()


def summary_for_nodes(evidence: list[dict], node_ids: set[str], max_chars: int = 1600) -> str:
    lines = []
    for row in evidence:
        if row.get('status') != 'inspected' or not node_ids.intersection(row.get('requirement_ids', [])):
            continue
        for observation in row.get('observations', []):
            if observation.get('kind') == 'uncertainty':
                continue
            lines.append(f"[{row['image']} sha256:{row['sha256'][:12]}] " + observation['text'])
    return ('Visible reference-image observations only; do not infer interaction, persistence, permissions or '
            'test outcomes:\n' + '\n'.join(lines))[:max_chars] if lines else ''
