"""Single-response code generation for one-node tasks (A5).

With tools stripped at the proxy, the model answers ONE request with the
whole application as delimited file blocks; the harness writes them, then
the normal acceptance loop runs. Two tool-protocol round trips (write, then
final answer) become one request, and no tool schemas travel with it.

Formats (chosen so they never collide with code or markdown fences):

    <<<FILE backend/server.js>>>
    ...file contents...
    <<<END FILE>>>

An existing file quoted in the prompt can instead receive one or more exact,
unique search/replace edits. This keeps a small change to a large page from
re-emitting the whole page in the completion.

When a requirement is already satisfied, the model may return exactly
``<<<NO CHANGE>>>``. The caller still runs acceptance; the marker only avoids
spending output tokens on a redundant rewrite.
"""

from __future__ import annotations

import re
from pathlib import Path

_END_FILE = r"(?:<<<END FILE>>>|<END FILE>|END FILE)"
_END_EDIT = r"(?:<<<END EDIT>>>|<END EDIT>|END EDIT)"
# Do not consume a later block when a preceding delimiter is malformed. Literal
# protocol examples can be emitted in a FILE body, not nested inside an EDIT.
_EDIT_BODY = r"(?:(?!^[ \t]*<<<(?:FILE|EDIT)\s).)*?"
_REPLACEMENT_BODY = r"(?:(?!^[ \t]*<<<(?:FILE|EDIT|END EDIT|SEARCH|REPLACE)\b).)*?"
FILE_BLOCK = re.compile(r"<<<FILE\s+(?P<path>[^\n>]+?)\s*>>>\r?\n(?P<body>.*?)(?:\r?\n)?"
                        rf"^{_END_FILE}[ \t]*(?=\r?\n|\Z)", re.S | re.M)
EDIT_BLOCK = re.compile(
    r"<<<EDIT\s+(?P<path>[^\n>]+?)\s*>>>\r?\n"
    rf"<<<SEARCH>>>\r?\n(?P<search>{_EDIT_BODY})(?:\r?\n)?^"
    rf"<<<REPLACE>>>\r?\n(?P<replacement>{_REPLACEMENT_BODY})(?:\r?\n)?^{_END_EDIT}[ \t]*(?=\r?\n|\Z)", re.S | re.M)


def iter_blocks(text: str):
    """Outermost complete envelopes only; quoted examples are not operations."""
    end = 0
    for match in sorted([*EDIT_BLOCK.finditer(text or ""), *FILE_BLOCK.finditer(text or "")],
                        key=lambda item: (item.start(), -item.end())):
        if match.start() >= end:
            yield match
            end = match.end()

FORMAT_INSTRUCTIONS = """\
Only blocks, or exactly <<<NO CHANGE>>> if already met. Start with a block marker, not prose.
FILE (new file or short rewrite):
<<<FILE relative/path>>>
contents
<<<END FILE>>>
EDIT (small change to quoted file; multiple allowed):
<<<EDIT relative/path>>>
<<<SEARCH>>>
exact unique old text
<<<REPLACE>>>
new text
<<<END EDIT>>>
Do not mix formats for one path or re-emit large existing files.
"""


def safe_relative_path(raw: str) -> str | None:
    raw = raw.strip().strip("`'\"")
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or raw.startswith("/"):
        return None
    return "/".join(parts)


def parse_file_blocks(text: str) -> dict[str, str]:
    """Extract path -> contents; a later block for the same path wins.
    Paths are normalised and confined to the project (no absolute, no `..`)."""
    files: dict[str, str] = {}
    for m in iter_blocks(text):
        if m.re is not FILE_BLOCK:
            continue
        path = safe_relative_path(m.group("path"))
        if path is None:
            continue
        body = m.group("body")
        # tolerate a stray fence the model wrapped around the body
        stripped = body.strip("\n")
        if stripped.startswith("```") and stripped.rstrip().endswith("```"):
            inner = stripped.split("\n", 1)[1] if "\n" in stripped else ""
            body = inner.rsplit("```", 1)[0]
        files[path] = body.rstrip("\n") + "\n"
    return files


def normalize_bare_file_reply(text: str) -> str | None:
    """Compatibility for a completed reply consisting solely of FILE sections.

    Some models omit ALL angle markers/terminators and separate whole files by
    `FILE frontend/...` headings. Accept only this unambiguous alternative
    envelope, never prose/fences, mixed EDIT syntax, duplicate/unsafe paths or
    empty sections. The caller must check successful (not truncated) completion.
    Normal write guards and application verification still apply afterward.
    """
    text = text.strip()
    if not text.startswith("FILE ") or "<<<" in text or re.search(r"(?m)^(?:```|EDIT\b|END FILE\b)", text):
        return None
    headers = list(re.finditer(r"(?m)^FILE ([^\n]+)\r?$", text))
    if not headers or headers[0].start() != 0:
        return None
    paths = set()
    output = []
    for index, header in enumerate(headers):
        raw = header[1].strip()
        path = safe_relative_path(raw)
        if (not path or path != raw or path in paths
                or not re.fullmatch(r"(?:frontend|backend)/[\w./-]+", path)):
            return None
        body = text[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)].strip("\r\n")
        if not body.strip():
            return None
        paths.add(path)
        output.append(f"<<<FILE {path}>>>\n{body}\n<<<END FILE>>>")
    return "\n".join(output)


def parse_edit_blocks(text: str) -> list[tuple[str, str, str]]:
    """Parse exact edits in response order; only project-relative paths qualify."""
    edits = []
    for match in iter_blocks(text):
        if match.re is not EDIT_BLOCK:
            continue
        path = safe_relative_path(match.group("path"))
        if path is not None:
            edits.append((path, match.group("search"), match.group("replacement")))
    return edits


def incomplete_blocks(text: str) -> bool:
    """Find unconsumed block headers, ignoring marker strings inside valid bodies."""
    spans = [match.span() for match in iter_blocks(text)]
    end = 0
    outside = []
    for start, stop in spans:
        if start >= end:
            outside.append(text[end:start])
        end = max(end, stop)
    outside.append(text[end:])
    return any(re.search(r"(?m)^[ \t]*<<<(?:FILE|EDIT)\b", part) for part in outside)


def prepare_edit_files(root: Path, edits: list[tuple[str, str, str]]) -> tuple[dict[str, str], list[str]]:
    """Stage every edit in memory; a missing or ambiguous anchor changes nothing.

    Multiple blocks for one file are applied in response order. Callers write
    the returned files only when the error list is empty.
    """
    staged: dict[str, str] = {}
    errors: list[str] = []
    for rel, search, replacement in edits:
        if not search:
            errors.append(f"{rel}: empty SEARCH")
            continue
        if rel not in staged:
            try:
                staged[rel] = (root / rel).read_text(encoding="utf-8")
            except OSError:
                errors.append(f"{rel}: file does not exist or cannot be read; use FILE")
                continue
        count = staged[rel].count(search)
        if count != 1:
            errors.append(f"{rel}: SEARCH matched {count} times; use a longer unique anchor")
            continue
        staged[rel] = staged[rel].replace(search, replacement, 1)
    return (staged, []) if not errors else ({}, errors)


CHARSET_META = '<meta charset="utf-8">'


def ensure_charset(text: str) -> str:
    """Pages without a charset declaration were decoded as Latin-1 by Chromium
    (the servers send `text/html` without charset), so every Chinese string the
    specs look for turned into mojibake (local s5/s10: 0/6). Inject the meta tag."""
    if re.search(r"<meta[^>]+charset", text, re.IGNORECASE):
        return text
    m = re.search(r"<head[^>]*>", text, re.IGNORECASE)
    if m:
        return text[:m.end()] + CHARSET_META + text[m.end():]
    m = re.search(r"<html[^>]*>", text, re.IGNORECASE)
    if m:
        return text[:m.end()] + "<head>" + CHARSET_META + "</head>" + text[m.end():]
    return CHARSET_META + "\n" + text


def unescape_flattened(text: str) -> str:
    """A file block occasionally arrives with its newlines JSON-escaped (one long
    line full of literal \\n; local s12: server.js failed to parse at startup).
    Restore it when the block is clearly flattened; leave normal files alone."""
    real = text.count("\n")
    literal = text.count("\\n")
    if literal >= 10 and literal > 5 * max(real, 1):
        return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return text


def js_parses(path: Path) -> bool | None:
    """`node --check`; None when node is unavailable."""
    import shutil, subprocess
    node = shutil.which("node")
    if not node:
        return None
    try:
        return subprocess.run([node, "--check", str(path)], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def repair_flattened_js(path: Path) -> bool:
    """Partially flattened blocks (some lines carry literal \\n between statements;
    local s12 crashed at startup) are only rewritten when the unescaped version
    parses and the original does not."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if "\\n" not in text or js_parses(path) is not False:
        return False
    fixed = "\n".join(line.replace("\\n", "\n") if line.count("\\n") >= 2 and not line.lstrip().startswith(("res.", "return"))
                      else line for line in text.split("\n"))
    if fixed == text:
        return False
    backup = path.read_bytes()
    path.write_text(fixed, encoding="utf-8")
    if js_parses(path):
        return True
    path.write_bytes(backup)
    return False


def dedupe_nav_links(root: Path) -> list[str]:
    """Compatibility hook: source-level href matching cannot prove redundancy.

    Repeated destinations may be required navigation, calls to action, or
    conditional content. Let acceptance failures drive explicit app repairs.
    """
    return []


def write_files(root: Path, files: dict[str, str]) -> list[str]:
    written = []
    for rel, body in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.suffix.lower() in (".html", ".htm"):
            body = ensure_charset(body)
        before = dest.read_text(encoding="utf-8") if dest.exists() else None
        if body == before:
            continue
        dest.write_text(body, encoding="utf-8")
        if dest.suffix.lower() in (".js", ".cjs", ".mjs"):
            repair_flattened_js(dest)
        if dest.read_text(encoding="utf-8") != before:
            written.append(rel)
    return written
