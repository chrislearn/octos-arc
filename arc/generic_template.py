"""Install only task-neutral web infrastructure for fresh codegen builds.

No domain schema, fixture, page, authentication policy or acceptance outcome is
embedded here. Existing application files are never overwritten.
"""
from __future__ import annotations

import json
from pathlib import Path
from web_stack import react_manifest


def generic_template_active(output_dir: Path) -> bool:
    server = output_dir / "backend" / "server.js"
    try:
        return "Generic web entry" in server.read_text(encoding="utf-8", errors="replace")[:200]
    except OSError:
        return False


def install_generic_template(output_dir: Path, bundle_dir: Path, default_port: int,
                             extra_ports: list[int], *, react: bool = False,
                             capabilities: list[str] | None = None) -> list[str]:
    assets = {"backend/server.js": "server.js", "backend/lib/store.js": "store.js",
              "backend/lib/collection.js": "collection.js",
              "frontend/build.mjs": "frontend-build.mjs",
              "frontend/vite.config.mjs": "vite.config.mjs",
              "frontend/src/index.html": "frontend-index.html",
              "frontend/src/app.js": "frontend-app.js",
              "frontend/src/style.css": "frontend-style.css",
              "frontend/src/shared/dom.js": "frontend-dom.js",
              "frontend/src/shared/request.js": "frontend-request.js",
              "frontend/src/shared/router.js": "frontend-router.js"}
    written: list[str] = []
    if react:
        # Call only for a fresh app, before the fallback manifests are created.
        # Never replace a user/evolution application's manifest or entry point.
        source = output_dir / "frontend/src"
        existing_code = any(path.is_file() and path.suffix in {
            ".html", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".css", ".scss"
        } for path in source.rglob("*")) if source.is_dir() else False
        if (output_dir / "frontend/package.json").exists() or existing_code:
            raise ValueError("React scaffold requires an empty frontend")
        for rel in ("frontend/src/app.js", "frontend/src/shared/dom.js", "frontend/src/shared/router.js"):
            assets.pop(rel)
        assets["frontend/src/index.html"] = "react-index.html"
        assets["frontend/package-lock.json"] = "react-deps/package-lock.json"
        assets.update({"frontend/src/main.jsx": "react-main.jsx", "frontend/src/App.jsx": "react-app.jsx"})
        manifest = output_dir / "frontend/package.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(react_manifest(capabilities or []), indent=2) + "\n", encoding="utf-8")
        written.append("frontend/package.json")
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
