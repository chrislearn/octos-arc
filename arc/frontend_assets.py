"""Reject browser runtime assets that depend on an external CDN or host.

External navigation and API requests are not assets. Packages may be fetched by
npm during the build, but the resulting page must load scripts, styles, fonts,
and media from its own served files.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re


_REMOTE = re.compile(r"^(?:https?:)?//", re.I)
_CSS_ASSET = re.compile(r"@import\s+(?:url\(\s*)?[\"']?((?:https?:)?//[^\s\"')]+)|"
                        r"url\(\s*[\"']?((?:https?:)?//[^\s\"')]+)", re.I)
_JS_IMPORT = re.compile(r"\b(?:from\s*|import\s*(?:\(|)|importScripts\s*\(|"
                        r"new\s+(?:SharedWorker|Worker)\s*\()\s*[\"']((?:https?:)?//[^\"']+)", re.I)
_RESOURCE_TAGS = {"script", "img", "source", "audio", "video", "embed", "object", "image"}
_LINK_RELS = {"stylesheet", "preload", "modulepreload", "icon", "manifest", "apple-touch-icon"}


class _Assets(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        attrs = dict(attributes)
        values: list[str] = []
        if tag == "link" and set((attrs.get("rel") or "").lower().split()) & _LINK_RELS:
            values.append(attrs.get("href") or "")
        if tag in _RESOURCE_TAGS:
            values.extend(attrs.get(key) or "" for key in ("src", "href", "data", "poster"))
            values.extend(part.strip().split()[0] for part in (attrs.get("srcset") or "").split(",") if part.strip())
        for value in values:
            if _REMOTE.match(value.strip()):
                self.hits.append((self.getpos()[0], value.strip()))

    handle_startendtag = handle_starttag


def external_browser_assets(frontend: Path, *, built: bool = False) -> list[str]:
    """Return file:line evidence for remote browser asset references."""
    if built:
        base = frontend / "dist"
        files = sorted(base.rglob("*")) if base.is_dir() else []
    else:
        files = sorted(frontend.glob("*"))
        for directory in (frontend / "src", frontend / "public"):
            if directory.is_dir():
                files.extend(sorted(directory.rglob("*")))
    hits: list[str] = []
    for file in files:
        if not file.is_file() or file.suffix.lower() not in {".html", ".css", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".svg"}:
            continue
        try:
            body = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found: list[tuple[int, str]] = []
        if file.suffix.lower() in {".html", ".svg"}:
            parser = _Assets()
            parser.feed(body)
            found.extend(parser.hits)
        if file.suffix.lower() in {".html", ".css", ".svg"}:
            found.extend((body.count("\n", 0, match.start()) + 1, match.group(1) or match.group(2))
                         for match in _CSS_ASSET.finditer(body))
        if file.suffix.lower() in {".js", ".mjs", ".jsx", ".ts", ".tsx"}:
            found.extend((body.count("\n", 0, match.start()) + 1, match.group(1))
                         for match in _JS_IMPORT.finditer(body))
        hits.extend(f"{file.relative_to(frontend)}:{line} -> {url[:120]}" for line, url in found)
    return hits
