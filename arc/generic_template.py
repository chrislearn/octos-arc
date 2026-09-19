"""Install only task-neutral web infrastructure for fresh codegen builds.

No domain schema, fixture, page, authentication policy or acceptance outcome is
embedded here. Existing application files are never overwritten.
"""
from __future__ import annotations

import json
from pathlib import Path


def generic_template_active(output_dir: Path) -> bool:
    server = output_dir / "backend" / "server.js"
    try:
        return "Generic web entry" in server.read_text(encoding="utf-8", errors="replace")[:200]
    except OSError:
        return False


def install_generic_template(output_dir: Path, bundle_dir: Path, default_port: int,
                             extra_ports: list[int]) -> list[str]:
    assets = {"backend/server.js": "server.js", "backend/lib/store.js": "store.js",
              "backend/lib/collection.js": "collection.js"}
    written: list[str] = []
    for target, asset in assets.items():
        destination = output_dir / target
        if destination.exists():
            continue
        source = bundle_dir / "blueprints" / asset
        body = source.read_text(encoding="utf-8")
        if asset == "server.js":
            body = body.replace("__ARC_DEFAULT_PORT__", str(int(default_port)))
            body = body.replace("__ARC_EXTRA_PORTS__", json.dumps(sorted(set(extra_ports))))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")
        written.append(target)
    return written
