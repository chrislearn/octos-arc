"""Conservative file ownership planner for a parallel code-generation batch.

The application design is an input to this planner, never a write grant by
itself.  Only source modules with explicit requirement owners can be assigned
to workers.  The coordinator remains the sole writer of composition files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


_SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss"})
_FORBIDDEN_PARTS = frozenset({
    "test", "tests", "__tests__", "spec", "specs", "fixture", "fixtures",
    "data", "datasets", "public", "dist", "build", "node_modules", ".git",
})
_SHARED_NAMES = frozenset({
    "app.jsx", "app.tsx", "app.js", "app.ts", "router.js", "router.ts",
    "main.jsx", "main.tsx", "main.js", "main.ts", "index.jsx", "index.tsx",
    "server.js", "server.ts", "index.js", "index.ts", "index.html",
    "data.js", "data.ts", "repositories.js", "repositories.ts",
    "package.json", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "npm-shrinkwrap.json", "vite.config.js",
    "vite.config.ts", "style.css", "styles.css", "index.css",
    "build.mjs", "vite.config.mjs",
})
_SHARED_PATHS = frozenset({
    "backend/lib/arc.js", "backend/lib/query.js", "backend/lib/store.js",
    "backend/lib/collection.js", "backend/lib/errors.js",
})


@dataclass(frozen=True)
class TaskPacket:
    task_id: str
    node_ids: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    shared_paths: tuple[str, ...]
    dependencies: tuple[str, ...]


def _path(value: object) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if ("\\" in value or "//" in value or len(value) > 500
            or any(char.isspace() or ord(char) < 32 for char in value)):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in {".", ".."} for part in value.split("/")):
        return None
    if len(path.parts) < 2 or path.parts[0] not in {"frontend", "backend"}:
        return None
    if any(part.casefold() in _FORBIDDEN_PARTS for part in path.parts):
        return None
    return value


def _shared(path: str) -> bool:
    rel = PurePosixPath(path)
    return (path in _SHARED_PATHS or "shared" in (part.casefold() for part in rel.parts)
            or rel.name.casefold() in _SHARED_NAMES
            or rel.name.casefold().endswith((".config.js", ".config.ts")))


def _assignable(path: str) -> bool:
    rel = PurePosixPath(path)
    lowered = {part.casefold() for part in rel.parts}
    return (not _shared(path) and rel.suffix.casefold() in _SOURCE_SUFFIXES
            and not lowered.intersection(_FORBIDDEN_PARTS)
            and not rel.stem.casefold().endswith((".test", ".spec")))


def _owners(module: dict) -> tuple[str, ...] | None:
    fields = [module[key] for key in ("requirements", "requirement_ids") if key in module]
    if not fields or any(not isinstance(field, list) or not field
                         or any(not isinstance(value, str) or not value.strip() for value in field)
                         for field in fields):
        return None
    normalized = [tuple(sorted(set(field))) for field in fields]
    if len(set(normalized)) != 1:
        return None
    return normalized[0]


def plan_parallel_tasks(
    ordered: list[dict], design: dict, existing_paths: set[str], *, max_workers: int = 3,
) -> list[TaskPacket]:
    """Plan up to ``max_workers`` independent, exact-file worker assignments.

    Unknown ownership, unsafe paths, overlapping assignments, and unresolved
    dependencies never grant write permission.  An empty result means the
    caller should retain the serial generation path.
    """
    if max_workers < 2 or not isinstance(design, dict) or not isinstance(ordered, list):
        return []
    ids = [node.get("id") if isinstance(node, dict) else None for node in ordered]
    if any(not isinstance(node_id, str) or not node_id.strip() for node_id in ids):
        return []
    if len(ids) != len(set(ids)):
        return []
    nodes = {node_id: node for node_id, node in zip(ids, ordered)}
    modules = design.get("modules")
    if not isinstance(modules, list):
        return []

    shared = set()
    for raw in existing_paths:
        path = _path(raw)
        if path and _shared(path):
            shared.add(path)

    paths_to_owners: dict[str, tuple[str, ...]] = {}
    seen_casefold: dict[str, str] = {}
    for module in modules:
        if not isinstance(module, dict):
            return []
        path = _path(module.get("path"))
        if path is None:
            return []
        prior = seen_casefold.setdefault(path.casefold(), path)
        if prior != path:
            return []
        if _shared(path):
            shared.add(path)
            continue
        owners = _owners(module)
        if owners is None or not _assignable(path) or any(owner not in nodes for owner in owners):
            return []
        if path in paths_to_owners and paths_to_owners[path] != owners:
            return []
        paths_to_owners[path] = owners

    all_paths = sorted(set(paths_to_owners) | shared)
    for index, left in enumerate(all_paths):
        if any(right.startswith(left + "/") for right in all_paths[index + 1:]):
            return []

    # Every path has a single owner group.  Modules owned by the same node
    # merge naturally; a module jointly owned by several nodes merges them.
    parent = {node_id: node_id for node_id in ids}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    for owners in paths_to_owners.values():
        for owner in owners[1:]:
            parent[find(owner)] = find(owners[0])

    grouped: dict[str, dict[str, set[str]]] = {}
    for path, owners in paths_to_owners.items():
        group = grouped.setdefault(find(owners[0]), {"ids": set(), "paths": set()})
        group["ids"].update(owners)
        group["paths"].add(path)

    positions = {node_id: index for index, node_id in enumerate(ids)}
    selected: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = []
    for group in grouped.values():
        members = tuple(sorted(group["ids"], key=positions.__getitem__))
        member_set = set(members)
        dependencies = set()
        invalid = False
        for node_id in members:
            values = nodes[node_id].get("dependencies") or []
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                invalid = True
                break
            dependencies.update(values)
        if invalid or any(dep not in member_set for dep in dependencies):
            continue
        selected.append((members, tuple(sorted(group["paths"])),
                         tuple(sorted(dependencies, key=positions.__getitem__))))

    selected.sort(key=lambda item: positions[item[0][0]])
    selected = selected[:max_workers]
    if len(selected) < 2:
        return []
    shared_paths = tuple(sorted(shared))
    return [TaskPacket(f"parallel-{index + 1}", members, paths, shared_paths, dependencies)
            for index, (members, paths, dependencies) in enumerate(selected)]
