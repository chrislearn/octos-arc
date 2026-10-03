"""Validate an isolated codegen worker's reply before coordinator integration.

Workers have no write access.  This parser stages complete source replacements
against their frozen snapshot and returns only a candidate or a shared-file
request; the coordinator owns all filesystem writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import PurePosixPath
import re

from codegen import EDIT_BLOCK, FILE_BLOCK, iter_blocks, safe_relative_path, source_protocol_errors


_SOURCE_SUFFIXES = {".html", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
                    ".mts", ".cts", ".vue", ".css", ".scss", ".json", ".svg"}
_SHARED_REQUEST = re.compile(
    r"\A<<<SHARED_CHANGE_REQUEST>>>\s*([\s\S]*?)\s*<<<END SHARED_CHANGE_REQUEST>>>\Z"
)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class CandidateResult:
    kind: str
    files: dict[str, str] = field(default_factory=dict)
    request: dict | None = None
    reason: str = ""


def _rejected(reason: str) -> CandidateResult:
    return CandidateResult("rejected", reason=reason)


def _source_path(path: str) -> bool:
    """Accept only canonical application source paths, never aliases or tests."""
    if not isinstance(path, str) or safe_relative_path(path) != path:
        return False
    if not re.fullmatch(r"(?:frontend|backend)/[A-Za-z0-9_./-]+", path):
        return False
    parts = PurePosixPath(path).parts
    forbidden = {"test", "tests", "__tests__", "spec", "specs", "fixture", "fixtures",
                 "data", "datasets", "public", "dist", "build", "node_modules",
                 "coverage", ".git"}
    return (len(parts) > 1 and all(part.casefold() not in forbidden for part in parts)
            and PurePosixPath(path).suffix in _SOURCE_SUFFIXES)


def _shared_request(text: str, shared_paths: set[str], snapshot: dict[str, str]) -> CandidateResult:
    match = _SHARED_REQUEST.fullmatch(text.strip())
    if not match or len(match[1]) > 16000:
        return _rejected("malformed_shared_request")
    try:
        request = json.loads(match[1])
    except (ValueError, TypeError):
        return _rejected("malformed_shared_request")
    if not isinstance(request, dict) or set(request) != {
            "path", "reason", "desired_change", "requirement_ids", "base_hash"}:
        return _rejected("malformed_shared_request")
    path = request["path"]
    if not _source_path(path) or path not in shared_paths or path not in snapshot:
        return _rejected("undeclared_shared_path")
    if (not isinstance(request["reason"], str) or not request["reason"].strip()
            or len(request["reason"]) > 2000
            or not isinstance(request["desired_change"], str)
            or not request["desired_change"].strip()
            or len(request["desired_change"]) > 10000
            or not isinstance(request["requirement_ids"], list)
            or not request["requirement_ids"]
            or len(request["requirement_ids"]) > 100
            or any(not isinstance(item, str) or not item.strip() or len(item) > 200
                   for item in request["requirement_ids"])):
        return _rejected("malformed_shared_request")
    digest = request["base_hash"]
    if (not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest)
            or digest != hashlib.sha256(snapshot[path].encode("utf-8")).hexdigest()):
        return _rejected("stale_shared_base")
    return CandidateResult("shared_request", request={
        "path": path, "reason": request["reason"].strip(),
        "desired_change": request["desired_change"].strip(),
        "requirement_ids": list(dict.fromkeys(request["requirement_ids"])),
        "base_hash": digest,
    })


def parse_candidate(reply: str, *, allowed_paths: set[str], shared_paths: set[str],
                    snapshot: dict[str, str], shown_paths: set[str]) -> CandidateResult:
    """Parse a complete, authorized reply using only the frozen source snapshot.

    FILE on an existing file requires that the whole file was shown to the
    worker. EDIT requires both an existing file and a quoted whole file.
    Multiple EDIT blocks on one path are applied in response order. FILE and
    EDIT on the same path, duplicate FILE blocks, prose, and partial envelopes
    reject the entire candidate.
    """
    if not isinstance(reply, str) or not reply.strip():
        return _rejected("empty_reply")
    text = reply.strip()
    if text == "<<<NO CHANGE>>>":
        return CandidateResult("no_change")
    if "SHARED_CHANGE_REQUEST" in text:
        return _shared_request(text, shared_paths, snapshot)

    matches = list(iter_blocks(text))
    if not matches:
        return _rejected("no_blocks")
    cursor = 0
    staged: dict[str, str] = {}
    modes: dict[str, str] = {}
    for match in matches:
        if text[cursor:match.start()].strip():
            return _rejected("protocol_junk")
        cursor = match.end()
        path = match.group("path")
        if not _source_path(path):
            return _rejected("unsafe_path")
        if path in shared_paths:
            return _rejected("shared_path_write")
        if path not in allowed_paths:
            return _rejected("unowned_path")
        if match.re is FILE_BLOCK:
            if path in modes:
                return _rejected("duplicate_or_mixed_path")
            if path in snapshot and path not in shown_paths:
                return _rejected("blind_file_rewrite")
            body = match.group("body")
            if not body.strip():
                return _rejected("empty_file")
            staged[path] = body.rstrip("\n") + "\n"
            modes[path] = "FILE"
        elif match.re is EDIT_BLOCK:
            if modes.get(path) == "FILE":
                return _rejected("duplicate_or_mixed_path")
            if path not in snapshot or path not in shown_paths:
                return _rejected("unshown_edit_path")
            search = match.group("search")
            if not search:
                return _rejected("empty_search")
            current = staged.get(path, snapshot[path])
            count = current.count(search)
            if count != 1:
                return _rejected("ambiguous_search")
            staged[path] = current.replace(search, match.group("replacement"), 1)
            modes[path] = "EDIT"
        else:
            return _rejected("unknown_block")
    if text[cursor:].strip():
        return _rejected("protocol_junk")
    if source_protocol_errors(staged):
        return _rejected("source_protocol_marker")
    return CandidateResult("candidate", files=staged)
